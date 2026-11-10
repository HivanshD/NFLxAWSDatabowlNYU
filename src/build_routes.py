"""Build a route-level table: for every route run on a pass play, when did the
receiver get open, and when did the pass rush get home?

Output: outputs/routes.parquet (one row per route) and
        outputs/sep_curves.parquet (per-frame separation for every route).
"""
from __future__ import annotations

import re
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"

FPS = 10
SNAP_EVENTS = {"ball_snap", "autoevent_ballsnap"}
END_EVENTS = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"}

OPEN_SEP = 3.0        # yards from nearest coverage defender to count as "open"
OPEN_MIN_DEPTH = 0.0  # must be at/past the line of scrimmage
PRESSURE_DIST = 2.0   # rusher within 2 yds of QB = pocket has collapsed
PRESSURE_MIN_T = 1.0  # ignore DL standing next to an under-center QB at the snap


def load_meta():
    plays = pd.read_csv(DATA / "plays.csv")
    pff = pd.read_csv(DATA / "pffScoutingData.csv",
                      usecols=["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp",
                               "pff_hit", "pff_hurry", "pff_sack"])
    players = pd.read_csv(DATA / "players.csv", usecols=["nflId", "officialPosition", "displayName"])
    return plays, pff, players


def find_target(desc: str, runners: pd.DataFrame):
    """Targeted receiver = route runner whose 'F.Lastname' appears first after 'pass'."""
    if not isinstance(desc, str) or " pass " not in desc:
        return np.nan
    text = desc.split(" pass ", 1)[1]
    best, best_pos = np.nan, 10 ** 9
    for nid, name in zip(runners.nflId, runners.displayName):
        parts = name.replace(" Jr.", "").replace(" III", "").replace(" II", "").split()
        if len(parts) < 2:
            continue
        last = " ".join(parts[1:])
        m = re.search(r"\b" + re.escape(parts[0][0]) + r"[a-z]?\.\s?" + re.escape(last), text)
        if m is None:
            m = re.search(r"\.\s?" + re.escape(last) + r"\b", text)
        if m and m.start() < best_pos:
            best, best_pos = nid, m.start()
    return best


def process_game(game_id: int):
    plays, pff, players = META
    trk = pd.read_csv(DATA / "tracking" / f"tracking_{game_id}.csv",
                      usecols=["gameId", "playId", "nflId", "frameId", "team", "playDirection",
                               "x", "y", "s", "event"])
    # normalise so offence always moves left -> right
    left = trk.playDirection == "left"
    trk.loc[left, "x"] = 120 - trk.loc[left, "x"]
    trk.loc[left, "y"] = 160 / 3 - trk.loc[left, "y"]

    g_pff = pff[pff.gameId == game_id].merge(players, on="nflId", how="left")
    g_plays = plays[plays.gameId == game_id].set_index("playId")

    route_rows, curve_rows = [], []
    for play_id, p in trk.groupby("playId", sort=False):
        if play_id not in g_plays.index:
            continue
        meta = g_plays.loc[play_id]
        ev = p.drop_duplicates("frameId").set_index("frameId").event
        snaps = ev[ev.isin(SNAP_EVENTS)].index
        if len(snaps) == 0:
            continue
        snap = snaps.min()
        ends = ev[(ev.index > snap) & ev.isin(END_EVENTS)].index
        if len(ends) == 0:
            continue
        end = ends.min()
        end_event = ev.loc[end]

        roles = g_pff[g_pff.playId == play_id]
        qb_ids = roles.loc[roles.pff_role == "Pass", "nflId"].values
        rush_ids = roles.loc[roles.pff_role == "Pass Rush", "nflId"].values
        cov_ids = roles.loc[roles.pff_role == "Coverage", "nflId"].values
        runners = roles[roles.pff_role == "Pass Route"]
        if len(qb_ids) == 0 or len(cov_ids) == 0 or runners.empty:
            continue

        w = p[(p.frameId >= snap) & (p.frameId <= end)]
        pos = w.pivot_table(index="frameId", columns="nflId", values=["x", "y"])
        frames = pos.index.values
        t = (frames - snap) / FPS
        X, Y = pos["x"], pos["y"]

        ball = p[(p.team == "football") & (p.frameId == snap)]
        los = ball.x.iloc[0] if len(ball) else X.loc[snap, qb_ids[0]] + 5

        # --- when does the rush get home? ---
        qb = qb_ids[0]
        if qb not in X.columns:
            continue
        rush = [r for r in rush_ids if r in X.columns]
        if rush:
            d_qb = np.sqrt((X[rush].values - X[[qb]].values) ** 2 + (Y[rush].values - Y[[qb]].values) ** 2)
            min_d = np.nanmin(d_qb, axis=1)
            hit = np.where((min_d < PRESSURE_DIST) & (t >= PRESSURE_MIN_T))[0]
            t_pressure = t[hit[0]] if len(hit) else np.nan
        else:
            t_pressure = np.nan
        if end_event in ("qb_sack", "qb_strip_sack") and np.isnan(t_pressure):
            t_pressure = t[-1]
        t_end = t[-1]

        cov = [c for c in cov_ids if c in X.columns]
        target = find_target(meta.playDescription, runners)

        for r in runners.itertuples():
            if r.nflId not in X.columns:
                continue
            rx, ry = X[r.nflId].values, Y[r.nflId].values
            sep = np.nanmin(np.sqrt((X[cov].values - rx[:, None]) ** 2 + (Y[cov].values - ry[:, None]) ** 2), axis=1)
            depth = rx - los
            is_open = (sep >= OPEN_SEP) & (depth >= OPEN_MIN_DEPTH)
            # open = first frame of a sustained (>=0.3s) open window
            run = np.convolve(is_open.astype(int), np.ones(3, int), "valid") == 3
            idx = np.where(run)[0]
            t_open = t[idx[0]] if len(idx) else np.nan

            route_rows.append(dict(
                gameId=game_id, playId=play_id, nflId=r.nflId, name=r.displayName,
                pos=r.officialPosition, aligned=r.pff_positionLinedUp,
                t_open=t_open, t_pressure=t_pressure, t_end=t_end, end_event=end_event,
                sep_at_throw=sep[-1], max_sep=np.nanmax(sep), depth_at_throw=depth[-1],
                open_frac=is_open.mean(), targeted=bool(r.nflId == target),
                target_found=not pd.isna(target),
            ))
            curve_rows.append(pd.DataFrame(dict(gameId=game_id, playId=play_id, nflId=r.nflId,
                                                t=t, sep=sep, depth=depth)))

    curves = pd.concat(curve_rows) if curve_rows else pd.DataFrame()
    return pd.DataFrame(route_rows), curves


def _init(meta):
    global META
    META = meta


def main():
    OUT.mkdir(exist_ok=True)
    meta = load_meta()
    games = pd.read_csv(DATA / "games.csv").gameId.tolist()
    with Pool(8, initializer=_init, initargs=(meta,)) as pool:
        results = pool.map(process_game, games)
    routes = pd.concat([r for r, _ in results], ignore_index=True)
    curves = pd.concat([c for _, c in results if len(c)], ignore_index=True)

    plays = meta[0][["gameId", "playId", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
                     "passResult", "playResult", "pff_passCoverage", "pff_passCoverageType",
                     "dropBackType", "pff_playAction", "offenseFormation"]]
    routes = routes.merge(plays, on=["gameId", "playId"], how="left")
    routes.to_parquet(OUT / "routes.parquet", index=False)
    curves.to_parquet(OUT / "sep_curves.parquet", index=False)
    print(f"{len(routes):,} routes from {routes.playId.nunique() and routes.groupby(['gameId','playId']).ngroups:,} plays")


if __name__ == "__main__":
    main()
