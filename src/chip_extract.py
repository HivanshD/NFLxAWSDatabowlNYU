"""Deep dive on chips: per-rusher path to the QB, and per-TE/RB route mechanics
(chip contact timing/duration, release, depth, openness at the throw).
Writes explore/chip_rushers.parquet and explore/chip_routes.parquet."""
from __future__ import annotations

from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
FPS = 10
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"}
CONTACT = 1.5   # yds between chipper and rusher = engaged


def game(gid):
    pff = META
    t = pd.read_csv(DATA / "tracking" / f"tracking_{gid}.csv")
    ball = t[t.team == "football"]
    t = t[t.team != "football"].copy()
    for d in (t, ball):
        pass
    L = t.playDirection == "left"
    t.loc[L, "x"] = 120 - t.loc[L, "x"]
    t.loc[L, "y"] = 160 / 3 - t.loc[L, "y"]
    bl = ball.playDirection == "left"
    ball = ball.copy()
    ball.loc[bl, "x"] = 120 - ball.loc[bl, "x"]
    gp = pff[pff.gameId == gid]
    R, C = [], []
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
        P = {c: p.pivot_table(index="frameId", columns="nflId", values=c) for c in ["x", "y", "s"]}
        frames = list(P["x"].index)
        if snap not in frames or end not in frames:
            continue
        i0, i1 = frames.index(snap), frames.index(end)
        col = {c: j for j, c in enumerate(P["x"].columns)}
        X, Y, S = P["x"].values, P["y"].values, P["s"].values
        qbs = [col[i] for i in roles.index[roles.pff_role == "Pass"] if i in col]
        cov = [col[i] for i in roles.index[roles.pff_role == "Coverage"] if i in col]
        if not qbs or not cov:
            continue
        qb = qbs[0]
        b = ball[(ball.playId == pid) & (ball.frameId == snap)]
        los = b.x.iat[0] if len(b) else X[i0, qb] + 5
        tt = (np.arange(len(frames)) - i0) / FPS

        chips = roles[(roles.pff_role == "Pass Route") & (roles.pff_blockType == "CH")]
        chip_of = {int(r.pff_nflIdBlockedPlayer): nid for nid, r in chips.iterrows() if pd.notna(r.pff_nflIdBlockedPlayer)}

        # ---------- rushers ----------
        for nid in roles.index[roles.pff_role == "Pass Rush"]:
            if nid not in col:
                continue
            j = col[nid]
            dq = np.hypot(X[:, j] - X[:, qb], Y[:, j] - Y[:, qb])
            w = slice(i0, i1 + 1)
            close = np.where((dq[w] < 2.0) & (tt[w] >= 1.0))[0]
            r = roles.loc[nid]
            f = dict(gameId=gid, playId=pid, nflId=nid, aligned=r.pff_positionLinedUp,
                     chipped=nid in chip_of, chipper=chip_of.get(nid, np.nan),
                     pressure=bool((r[["pff_hurry", "pff_hit", "pff_sack"]].fillna(0) > 0).any()),
                     sack=bool(r.pff_sack == 1) if pd.notna(r.pff_sack) else False,
                     t_end=tt[i1], t_home=tt[i0 + close[0]] if len(close) else np.nan,
                     dq0=dq[i0], min_dq=np.nanmin(dq[w]))
            for s in (1.5, 2.0, 2.5):
                k = i0 + int(s * FPS)
                f[f"dq_{s}"] = dq[k] if k <= i1 else np.nan
            if nid in chip_of and chip_of[nid] in col:
                c = col[chip_of[nid]]
                dc = np.hypot(X[w, j] - X[w, c], Y[w, j] - Y[w, c])
                eng = np.where(dc < CONTACT)[0]
                if len(eng):
                    f["chip_start"] = eng[0] / FPS
                    f["chip_frames"] = len(eng) / FPS
                    k0 = i0 + eng[0]
                    f["rush_s_pre"] = np.nanmean(S[max(i0, k0 - 3):k0 + 1, j])
                    f["rush_s_post"] = np.nanmean(S[k0 + 1:min(k0 + 6, i1 + 1), j])
            R.append(f)

        # ---------- TE/RB route runners (chip vs not) ----------
        for nid, r in roles[(roles.pff_role == "Pass Route") & roles.officialPosition.isin(["TE", "RB", "FB"])].iterrows():
            if nid not in col:
                continue
            j = col[nid]
            w = slice(i0, i1 + 1)
            sep = np.nanmin(np.hypot(X[w][:, cov] - X[w, j][:, None], Y[w][:, cov] - Y[w, j][:, None]), axis=1)
            f = dict(gameId=gid, playId=pid, nflId=nid, name=r.displayName, pos=r.officialPosition,
                     aligned=r.pff_positionLinedUp, chip=r.pff_blockType == "CH", t_end=tt[i1],
                     x0=X[i0, j] - los, sep_end=sep[-1], depth_end=X[i1, j] - los)
            for s in (1.5, 2.0, 2.5, 3.0):
                k = i0 + int(s * FPS)
                f[f"depth_{s}"] = X[k, j] - los if k <= i1 else np.nan
            # time the receiver first crosses the line of scrimmage = "into the route"
            past = np.where(X[w, j] - los >= 1.0)[0]
            f["t_release"] = past[0] / FPS if len(past) else np.nan
            if f["chip"] and pd.notna(r.pff_nflIdBlockedPlayer) and int(r.pff_nflIdBlockedPlayer) in col:
                rj = col[int(r.pff_nflIdBlockedPlayer)]
                dc = np.hypot(X[w, j] - X[w, rj], Y[w, j] - Y[w, rj])
                eng = np.where(dc < CONTACT)[0]
                if len(eng):
                    f["chip_start"], f["chip_len"] = eng[0] / FPS, len(eng) / FPS
                    f["chip_end"] = eng[-1] / FPS
            C.append(f)
    return pd.DataFrame(R), pd.DataFrame(C)


def _init(m):
    global META
    META = m


if __name__ == "__main__":
    pff = pd.read_csv(DATA / "pffScoutingData.csv").merge(
        pd.read_csv(DATA / "players.csv", usecols=["nflId", "officialPosition", "displayName"]), on="nflId", how="left")
    games = pd.read_csv(DATA / "games.csv").gameId.tolist()
    with Pool(8, initializer=_init, initargs=(pff,)) as pool:
        res = pool.map(game, games)
    plays = pd.read_csv(DATA / "plays.csv")[["gameId", "playId", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
                                             "passResult", "playResult", "pff_passCoverageType", "pff_playAction",
                                             "dropBackType", "offenseFormation", "personnelO", "defendersInBox"]]
    tg = pd.read_parquet(ROOT / "outputs" / "routes.parquet")[["gameId", "playId", "nflId", "targeted"]]
    rush = pd.concat([r for r, _ in res], ignore_index=True).merge(plays, on=["gameId", "playId"], how="left")
    rts = pd.concat([c for _, c in res], ignore_index=True).merge(plays, on=["gameId", "playId"], how="left") \
        .merge(tg, on=["gameId", "playId", "nflId"], how="left")
    rush.to_parquet(OUT / "chip_rushers.parquet", index=False)
    rts.to_parquet(OUT / "chip_routes.parquet", index=False)
    print("rushers", len(rush), "chipped", int(rush.chipped.sum()), "| TE/RB routes", len(rts), "chips", int(rts.chip.sum()))
