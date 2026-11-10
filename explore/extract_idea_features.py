"""One pass over tracking that extracts the movement features needed to test 10
candidate ideas. Writes explore/feat_*.parquet. Exploration code, not the final product.
"""
from __future__ import annotations

from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "explore"
FPS = 10
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"}


def angdiff(a, b):
    """signed smallest difference a-b in degrees, in (-180, 180]"""
    return (a - b + 180) % 360 - 180


def load():
    plays = pd.read_csv(DATA / "plays.csv")
    pff = pd.read_csv(DATA / "pffScoutingData.csv")
    players = pd.read_csv(DATA / "players.csv", usecols=["nflId", "officialPosition", "displayName"])
    return plays, pff.merge(players, on="nflId", how="left")


def game(gid):
    plays, pff = META
    t = pd.read_csv(DATA / "tracking" / f"tracking_{gid}.csv")
    t = t[t.team != "football"].copy()
    ball = pd.read_csv(DATA / "tracking" / f"tracking_{gid}.csv", usecols=["playId", "frameId", "team", "x", "y", "playDirection"])
    ball = ball[ball.team == "football"]
    for d in (t, ball):
        L = d.playDirection == "left"
        d.loc[L, "x"] = 120 - d.loc[L, "x"]
        d.loc[L, "y"] = 160 / 3 - d.loc[L, "y"]
    L = t.playDirection == "left"
    t.loc[L, "o"] = (t.loc[L, "o"] + 180) % 360
    t.loc[L, "dir"] = (t.loc[L, "dir"] + 180) % 360

    gp = pff[pff.gameId == gid]
    rows = {k: [] for k in ["route", "tell", "chip", "pickup"]}
    for pid, p in t.groupby("playId", sort=False):
        ev = p.drop_duplicates("frameId").set_index("frameId").event
        sn = ev[ev.isin(SNAP)].index
        if not len(sn):
            continue
        snap = sn.min()
        en = ev[(ev.index > snap) & ev.isin(END)].index
        if not len(en):
            continue
        end = en.min()
        roles = gp[gp.playId == pid].set_index("nflId")
        P = {c: p.pivot_table(index="frameId", columns="nflId", values=c) for c in ["x", "y", "s", "o", "dir"]}
        frames = P["x"].index.values
        if snap not in frames:
            continue
        fi = {f: i for i, f in enumerate(frames)}
        i0, i1 = fi[snap], fi.get(end, len(frames) - 1)
        b = ball[(ball.playId == pid) & (ball.frameId == snap)]
        los, bally = (b.x.iat[0], b.y.iat[0]) if len(b) else (np.nan, 26.65)

        def ids(role):
            return [i for i in roles.index[roles.pff_role == role] if i in P["x"].columns]
        cov, rush, qbs = ids("Coverage"), ids("Pass Rush"), ids("Pass")
        if not cov or not qbs:
            continue
        qb = qbs[0]
        X, Y, S, O, D = (P[c].values for c in ["x", "y", "s", "o", "dir"])
        col = {c: j for j, c in enumerate(P["x"].columns)}
        cj = [col[c] for c in cov]

        def dist(a, bcols):
            return np.sqrt((X[:, bcols] - X[:, [a]]) ** 2 + (Y[:, bcols] - Y[:, [a]]) ** 2)

        # ---------------- route runners: A2/A3/A5/B1/B2/B4/B5 + A4 cost ----------------
        for nid in ids("Pass Route"):
            j = col[nid]
            dcov = dist(j, cj)
            near = np.nanargmin(np.nan_to_num(dcov, nan=999), axis=1)
            sep = dcov[np.arange(len(frames)), near]
            f = dict(gameId=gid, playId=pid, nflId=nid, pos=roles.at[nid, "officialPosition"],
                     name=roles.at[nid, "displayName"], blockType=roles.at[nid, "pff_blockType"],
                     t_end=(end - snap) / FPS)
            c0 = sep[i0]
            f["cushion0"] = c0
            k1 = min(i0 + 10, i1)
            f["cushion1"] = sep[k1]
            f["melt"] = (c0 - sep[k1]) / max((k1 - i0) / FPS, 0.1)          # A5
            f["yds_1s"] = X[k1, j] - X[i0, j]                               # B5
            f["depth_2s"] = X[min(i0 + 20, i1), j] - los                   # A4 cost
            f["sep_end"] = sep[i1]
            # leverage vs defender nearest at snap (A2/B4). + = defender inside
            d0 = cj[near[i0]]
            inside = 1 if Y[i0, j] < 160 / 6 else -1
            lev = (Y[:, d0] - Y[:, j]) * inside
            f["lev0"], f["lev_end"] = lev[i0], lev[i1]
            seg = lev[i0:i1 + 1]
            f["lev_flip"] = bool(np.sign(seg[0]) != np.sign(seg[-1]) and abs(seg[-1]) > 0.5 and abs(seg[0]) > 0.5)
            # break detection (A3/B1/B2): first sharp heading change at speed after 0.5s
            br = np.nan
            for k in range(i0 + 5, i1 - 5):
                if S[k, j] >= 2 and abs(angdiff(D[k + 5, j], D[k, j])) >= 35:
                    br = k
                    break
            f["has_break"] = not np.isnan(br)
            if not np.isnan(br):
                k = int(br)
                f["t_break"] = (frames[k] - snap) / FPS
                f["vmax_pre"] = np.nanmax(S[max(i0, k - 5):k + 1, j])
                f["vmin_brk"] = np.nanmin(S[k:k + 4, j])
                f["decel"] = f["vmax_pre"] - f["vmin_brk"]                  # A3
                f["hip"] = np.nanmean(np.abs(angdiff(O[max(i0, k - 5):k, j], D[max(i0, k - 5):k, j])))  # B1
                k2 = min(k + 5, i1)
                f["sep_gain"] = sep[k2] - sep[k]
                # B2 bite: defender velocity along receiver's post-break heading, 0.2s after break
                dd = cj[near[k]]
                h = np.deg2rad(D[min(k + 3, i1), j])
                kd = min(k + 2, i1)
                vdef = S[kd, dd] * (np.sin(np.deg2rad(D[kd, dd])) * np.sin(h) + np.cos(np.deg2rad(D[kd, dd])) * np.cos(h))
                f["def_follow"] = vdef
                f["bite"] = vdef < 0
            rows["route"].append(f)

        # ---------------- A1 tell: TE/RB/FB block-vs-route ----------------
        for nid in roles.index[roles.officialPosition.isin(["TE", "RB", "FB"])
                               & roles.pff_role.isin(["Pass Block", "Pass Route"])]:
            if nid not in col:
                continue
            j = col[nid]
            pre = slice(max(0, i0 - 5), i0 + 1)
            k3 = min(i0 + 3, i1)
            rows["tell"].append(dict(
                gameId=gid, playId=pid, nflId=nid, name=roles.at[nid, "displayName"],
                pos=roles.at[nid, "officialPosition"], aligned=roles.at[nid, "pff_positionLinedUp"],
                route=roles.at[nid, "pff_role"] == "Pass Route",
                depth=los - X[i0, j], wide=abs(Y[i0, j] - bally),
                o_snap=angdiff(O[i0, j], 90), o_abs=abs(angdiff(O[i0, j], 90)),
                s_pre=np.nanmean(S[pre, j]), o_pre_sd=np.nanstd(O[pre, j]),
                s_03=S[k3, j], dx_03=X[k3, j] - X[i0, j], dir_03=abs(angdiff(D[k3, j], 90)),
            ))

        # ---------------- A4 chip value: rushers chipped vs not ----------------
        chippers = roles[(roles.pff_role == "Pass Route") & (roles.pff_blockType == "CH")]
        chipped = set(chippers.pff_nflIdBlockedPlayer.dropna().astype(int))
        for nid in rush:
            r = roles.loc[nid]
            rows["chip"].append(dict(gameId=gid, playId=pid, nflId=nid, aligned=r.pff_positionLinedUp,
                                     chipped=nid in chipped,
                                     pressure=bool((r[["pff_hurry", "pff_hit", "pff_sack"]].fillna(0) > 0).any())))

        # ---------------- B3 pickup: TE/RB pass-pro contact mechanics ----------------
        blk = roles[(roles.pff_role == "Pass Block") & roles.officialPosition.isin(["TE", "RB", "FB"])]
        for nid, r in blk.iterrows():
            if nid not in col or pd.isna(r.pff_nflIdBlockedPlayer) or int(r.pff_nflIdBlockedPlayer) not in col:
                continue
            j, rj = col[nid], col[int(r.pff_nflIdBlockedPlayer)]
            d = np.sqrt((X[i0:i1 + 1, j] - X[i0:i1 + 1, rj]) ** 2 + (Y[i0:i1 + 1, j] - Y[i0:i1 + 1, rj]) ** 2)
            hit = np.where(d < 1.5)[0]
            if not len(hit):
                continue
            k = i0 + hit[0]
            to_r = np.rad2deg(np.arctan2(X[k, rj] - X[k, j], Y[k, rj] - Y[k, j])) % 360
            rows["pickup"].append(dict(
                gameId=gid, playId=pid, nflId=nid, name=r.displayName, pos=r.officialPosition,
                blockType=r.pff_blockType, t_contact=(frames[k] - snap) / FPS,
                s_blk=S[k, j], s_rush=S[k, rj], square=abs(angdiff(O[k, j], to_r)),
                qb_dist=np.hypot(X[k, j] - X[k, col[qb]], Y[k, j] - Y[k, col[qb]]),
                depth_contact=los - X[k, j],
                lost=bool((r[["pff_beatenByDefender", "pff_hurryAllowed", "pff_hitAllowed", "pff_sackAllowed"]].fillna(0) > 0).any()),
            ))
    return {k: pd.DataFrame(v) for k, v in rows.items()}


def _init(m):
    global META
    META = m


if __name__ == "__main__":
    meta = load()
    games = pd.read_csv(DATA / "games.csv").gameId.tolist()
    with Pool(8, initializer=_init, initargs=(meta,)) as pool:
        res = pool.map(game, games)
    plays = meta[0][["gameId", "playId", "possessionTeam", "passResult", "playResult", "pff_passCoverage",
                     "pff_passCoverageType", "offenseFormation", "personnelO", "down", "yardsToGo",
                     "dropBackType", "pff_playAction", "playDescription"]]
    for k in ["route", "tell", "chip", "pickup"]:
        df = pd.concat([r[k] for r in res], ignore_index=True).merge(plays, on=["gameId", "playId"], how="left")
        df.to_parquet(OUT / f"feat_{k}.parquet", index=False)
        print(k, len(df))
