"""Round 2: movement features for 8 new idea candidates (N1-N8), one row per route.
Writes explore/feat_new.parquet."""
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
    return np.abs((a - b + 180) % 360 - 180)


def bearing(x0, y0, x1, y1):
    """NGS angle convention (0 = +y, clockwise): direction from point 0 to point 1."""
    return np.rad2deg(np.arctan2(x1 - x0, y1 - y0)) % 360


def seg_dist(px, py, ax, ay, bx, by):
    """distance from points p to segment a-b"""
    vx, vy = bx - ax, by - ay
    L = vx * vx + vy * vy
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / max(L, 1e-6), 0, 1)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy)), t


def game(gid):
    pff = META
    t = pd.read_csv(DATA / "tracking" / f"tracking_{gid}.csv")
    t = t[t.team != "football"].copy()
    L = t.playDirection == "left"
    t.loc[L, "x"] = 120 - t.loc[L, "x"]
    t.loc[L, "y"] = 160 / 3 - t.loc[L, "y"]
    t.loc[L, "o"] = (t.loc[L, "o"] + 180) % 360
    t.loc[L, "dir"] = (t.loc[L, "dir"] + 180) % 360
    gp = pff[pff.gameId == gid]
    rows = []
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
        if snap not in frames or end not in frames:
            continue
        i0, i1 = list(frames).index(snap), list(frames).index(end)
        if i1 - i0 < 8:
            continue
        col = {c: j for j, c in enumerate(P["x"].columns)}
        X, Y, S, O, D = (P[c].values for c in ["x", "y", "s", "o", "dir"])

        def ids(role):
            return [col[i] for i in roles.index[roles.pff_role == role] if i in col]
        cov, rr, qbs = ids("Coverage"), ids("Pass Route"), ids("Pass")
        if not cov or not rr or not qbs:
            continue
        qb = qbs[0]
        los = X[i0, qb] + 0  # approximate; depth uses snap x of receiver below
        win = list(range(max(i0, i1 - 5), i1 + 1))      # last 0.5 s before the throw
        pre = max(i0, i1 - 2)                           # 0.2 s before the throw
        inv = {v: k for k, v in col.items()}

        # N1 gravity: each defender "attends" the route runner his shoulders point at most (<25 deg, <15 yds)
        grav = {j: 0.0 for j in rr}
        for k in win:
            for d in cov:
                best, ba = None, 25
                for j in rr:
                    dist = np.hypot(X[k, j] - X[k, d], Y[k, j] - Y[k, d])
                    if dist > 15:
                        continue
                    a = angdiff(O[k, d], bearing(X[k, d], Y[k, d], X[k, j], Y[k, j]))
                    if a < ba:
                        best, ba = j, a
                if best is not None:
                    grav[best] += 1 / len(win)

        # QB look series for N3
        for j in rr:
            nid = inv[j]
            f = dict(gameId=gid, playId=pid, nflId=nid, name=roles.at[nid, "displayName"],
                     pos=roles.at[nid, "officialPosition"], t_end=(end - snap) / FPS, gravity=grav[j])
            # N2 eyes off: nearest coverage defender at pre-throw frame
            dd = np.hypot(X[pre, cov] - X[pre, j], Y[pre, cov] - Y[pre, j])
            d = cov[int(np.nanargmin(dd))]
            f["def_look_rec"] = angdiff(O[pre, d], bearing(X[pre, d], Y[pre, d], X[pre, j], Y[pre, j]))
            f["def_look_qb"] = angdiff(O[pre, d], bearing(X[pre, d], Y[pre, d], X[pre, qb], Y[pre, qb]))
            f["eyes_on_qb"] = f["def_look_qb"] < 45
            # N3 read order: share of post-0.5s frames QB shoulders within 20 deg of this receiver; first look time
            ks = range(i0 + 5, i1 + 1)
            look = np.array([angdiff(O[k, qb], bearing(X[k, qb], Y[k, qb], X[k, j], Y[k, j])) < 20 for k in ks])
            f["qb_look_share"] = look.mean() if len(look) else np.nan
            f["qb_first_look"] = (list(ks)[int(np.argmax(look))] - i0) / FPS if look.any() else np.nan
            # N4 conflict: defenders roughly equidistant (<1.5 yd diff) between this receiver and a teammate, both <8 yds
            n_conf = 0
            for dv in cov:
                dj = np.hypot(X[pre, j] - X[pre, dv], Y[pre, j] - Y[pre, dv])
                if dj > 8:
                    continue
                for j2 in rr:
                    if j2 == j:
                        continue
                    d2 = np.hypot(X[pre, j2] - X[pre, dv], Y[pre, j2] - Y[pre, dv])
                    if d2 < 8 and abs(dj - d2) < 1.5:
                        n_conf += 1
                        break
            f["conflict"] = n_conf
            # N5 clean entry: crossing 10 yds past snap position; nearest defender behind receiver?
            depth = X[i0:i1 + 1, j] - X[i0, j]
            cross = np.where(depth >= 10)[0]
            if len(cross):
                k = i0 + cross[0]
                dk = np.hypot(X[k, cov] - X[k, j], Y[k, cov] - Y[k, j])
                dn = cov[int(np.nanargmin(dk))]
                f["entry_t"] = cross[0] / FPS
                f["clean_entry"] = X[k, dn] < X[k, j]
                f["entry_speed"] = S[k, j]
            # N6 work-back: velocity toward QB over the last 0.5 s
            vb = []
            for k in win:
                b = bearing(X[k, j], Y[k, j], X[k, qb], Y[k, qb])
                vb.append(S[k, j] * np.cos(np.deg2rad(D[k, j] - b)))
            f["work_back"] = float(np.nanmean(vb))
            # N7 scramble drill: extended plays only (>=3.5s)
            if (i1 - i0) >= 35:
                k3 = i0 + 30
                f["ext_speed"] = float(np.nanmean(S[k3:i1 + 1, j]))
                f["ext_turn"] = float(angdiff(D[i1, j], D[k3, j]))
                dd3 = np.nanmin(np.hypot(X[k3, cov] - X[k3, j], Y[k3, cov] - Y[k3, j]))
                dd1 = np.nanmin(np.hypot(X[i1, cov] - X[i1, j], Y[i1, cov] - Y[i1, j]))
                f["ext_gain"] = dd1 - dd3
            # N8 lane traffic: defenders within 2 yds of the QB->receiver line (excluding the last yard at the receiver)
            sd, tt = seg_dist(X[pre, cov], Y[pre, cov], X[pre, qb], Y[pre, qb], X[pre, j], Y[pre, j])
            f["lane_traffic"] = int(((sd < 2) & (tt > 0.05)).sum())
            f["throw_dist"] = float(np.hypot(X[pre, j] - X[pre, qb], Y[pre, j] - Y[pre, qb]))
            rows.append(f)
    return pd.DataFrame(rows)


def _init(m):
    global META
    META = m


if __name__ == "__main__":
    pff = pd.read_csv(DATA / "pffScoutingData.csv", usecols=["gameId", "playId", "nflId", "pff_role"])
    pl = pd.read_csv(DATA / "players.csv", usecols=["nflId", "officialPosition", "displayName"])
    pff = pff.merge(pl, on="nflId", how="left")
    games = pd.read_csv(DATA / "games.csv").gameId.tolist()
    with Pool(8, initializer=_init, initargs=(pff,)) as pool:
        df = pd.concat(pool.map(game, games), ignore_index=True)
    plays = pd.read_csv(DATA / "plays.csv")[["gameId", "playId", "possessionTeam", "passResult", "playResult",
                                             "pff_passCoverageType", "down", "yardsToGo"]]
    tg = pd.read_parquet(ROOT / "outputs" / "routes.parquet")[["gameId", "playId", "nflId", "targeted", "target_found"]]
    df = df.merge(plays, on=["gameId", "playId"], how="left").merge(tg, on=["gameId", "playId", "nflId"], how="left")
    df.to_parquet(OUT / "feat_new.parquet", index=False)
    print("rows", len(df))
