"""Top-down field view of one representative TE chip play (snap -> throw).

Output: outputs/figs/0_chip_play_field.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs" / "figs"
OUT.mkdir(parents=True, exist_ok=True)

GAME, PLAY = 2021101707, 306  # KC vs WAS: Kelce chips, Mahomes deep to Hill

SURFACE, LINES = "#fcfcfb", "#e4e3df"
INK, INK2 = "#0b0b0b", "#52514e"
ORANGE, VIOLET, BLUE = "#eb6834", "#6250d6", "#2a78d6"
GRAY, FAINT = "#b5b3ad", "#dcdad5"

SNAP = {"ball_snap", "autoevent_ballsnap"}
THROW = {"pass_forward", "autoevent_passforward"}


def load():
    trk = pd.read_csv(DATA / "tracking" / f"tracking_{GAME}.csv")
    trk = trk[trk.playId == PLAY].copy()
    left = trk.playDirection == "left"
    trk.loc[left, "x"] = 120 - trk.loc[left, "x"]
    trk.loc[left, "y"] = 53.3 - trk.loc[left, "y"]
    pff = pd.read_csv(DATA / "pffScoutingData.csv")
    pff = pff[(pff.gameId == GAME) & (pff.playId == PLAY)]
    players = pd.read_csv(DATA / "players.csv")[["nflId", "officialPosition", "displayName"]]
    play = pd.read_csv(DATA / "plays.csv").query("gameId == @GAME and playId == @PLAY").iloc[0]
    routes = pd.read_parquet(ROOT / "outputs" / "chip_routes.parquet")
    route = routes[(routes.gameId == GAME) & (routes.playId == PLAY) & routes.chip].iloc[0]
    return trk, pff, players, play, route


def main():
    trk, pff, players, play, route = load()
    print(f"Chosen play: gameId={GAME} playId={PLAY}")
    print(play.playDescription)

    ev = trk.drop_duplicates("frameId").set_index("frameId").event
    f_snap = ev[ev.isin(SNAP)].index.min()
    f_throw = ev[ev.isin(THROW)].index.min()
    win = trk[(trk.frameId >= f_snap) & (trk.frameId <= f_throw)]
    ball0 = trk[(trk.team == "football") & (trk.frameId == f_snap)].iloc[0]
    los = ball0.x

    pff = pff.merge(players, on="nflId", how="left")
    chipper = pff[pff.pff_blockType == "CH"].iloc[0]
    rusher_id = int(chipper.pff_nflIdBlockedPlayer)
    qb_id = pff[pff.pff_role == "Pass"].nflId.iloc[0]
    route_ids = set(pff[pff.pff_role == "Pass Route"].nflId) - {chipper.nflId}
    block_ids = set(pff[pff.pff_role == "Pass Block"].nflId)
    rush_ids = set(pff[pff.pff_role == "Pass Rush"].nflId) - {rusher_id}
    cov_ids = set(pff[pff.pff_role == "Coverage"].nflId)

    # Target = receiver closest to the ball when it arrives
    post = trk[trk.frameId > f_throw]
    arr = post[post.event.isin(["pass_arrived", "pass_outcome_caught"])].frameId.min()
    arr = arr if pd.notna(arr) else post.frameId.max()
    bf = post[(post.team == "football") & (post.frameId == arr)].iloc[0]
    cand = post[(post.frameId == arr) & post.nflId.isin(route_ids)]
    target_id = cand.loc[np.hypot(cand.x - bf.x, cand.y - bf.y).idxmin(), "nflId"]

    name = dict(zip(pff.nflId, pff.displayName))
    pos = dict(zip(pff.nflId, pff.officialPosition))

    def path(nid):
        return win[win.nflId == nid].sort_values("frameId")

    fig, ax = plt.subplots(figsize=(14, 7), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    x0, x1 = los - 14, los + 32
    # Crop y to the key actors, then widen x so the equal-aspect field fills the frame
    key = win[win.nflId.isin(route_ids | {qb_id, rusher_id, chipper.nflId, target_id})]
    y0, y1 = key.y.min() - 4, key.y.max() + 4
    xspan = x1 - x0
    x1 = x0 + xspan
    for xl in range(0, 121, 5):
        if x0 <= xl <= x1:
            ax.axvline(xl, color=INK2 if xl in (10, 110) else LINES, lw=1, zorder=0)
            if xl % 10 == 0 and 10 < xl < 110:
                yd = xl - 10 if xl <= 60 else 110 - xl
                ax.text(xl, y0 + 0.6, f"{yd}", ha="center", va="bottom", color=GRAY, fontsize=9, zorder=0)
    ax.axvline(los, color=INK, lw=1.6, zorder=1)
    ax.text(los + 0.4, y0 + 0.6, "Line of scrimmage", ha="left", va="bottom", color=INK2, fontsize=9)

    def trail(nid, color, lw, z, dot=6, alpha=1.0):
        p = path(nid)
        ax.plot(p.x, p.y, color=color, lw=lw, zorder=z, alpha=alpha, solid_capstyle="round")
        ax.scatter(p.x.iloc[-1], p.y.iloc[-1], s=dot ** 2, color=color, zorder=z + 0.5,
                   edgecolor=SURFACE, linewidth=1, alpha=alpha)
        return p

    for nid in block_ids | rush_ids:
        trail(nid, FAINT, 1.2, 2, dot=4)
    for nid in cov_ids:
        trail(nid, GRAY, 1.3, 3, dot=5)

    # Other route runners with depth labels
    for nid in route_ids:
        p = trail(nid, BLUE, 2.0, 5, dot=7)
        end = p.iloc[-1]
        depth = end.x - los
        tag = f"{pos[nid]} {name[nid].split()[-1]}: {depth:.0f} yd"
        if nid == target_id:
            tag += " (target)"
        ax.annotate(tag, (end.x, end.y), xytext=(8, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=10, color=BLUE, zorder=8)

    # QB
    qb = trail(qb_id, INK, 2.2, 6, dot=8)
    qe = qb.iloc[-1]
    ax.annotate(f"QB {name[qb_id].split()[-1]}", (qe.x, qe.y), xytext=(-10, 0),
                textcoords="offset points", ha="right", va="center", fontsize=10, color=INK)

    # Pass: QB -> target position at arrival
    tgt_arr = post[(post.nflId == target_id) & (post.frameId == arr)].iloc[0]
    ax.plot([qe.x, tgt_arr.x], [qe.y, tgt_arr.y], ls=(0, (4, 3)), color=INK, lw=1.2, zorder=4)
    ax.scatter(tgt_arr.x, tgt_arr.y, s=40, facecolor=SURFACE, edgecolor=INK, lw=1.2, zorder=4.5)

    # Chipped rusher
    rp = trail(rusher_id, VIOLET, 3.0, 7, dot=9)
    re_ = rp.iloc[-1]
    dq = np.hypot(re_.x - qe.x, re_.y - qe.y)

    # Chipper
    cp = trail(chipper.nflId, ORANGE, 3.6, 9, dot=10)
    ce = cp.iloc[-1]
    f_chip = f_snap + int(round(route.chip_start * 10))
    cc = cp[cp.frameId == f_chip].iloc[0]
    ax.scatter(cc.x, cc.y, s=170, marker="X", color=ORANGE, edgecolor=INK, lw=0.8, zorder=10)
    chip_depth = ce.x - los
    t_throw = (f_throw - f_snap) / 10

    RUSH_OFF = (-25, 45)
    CHIP_OFF = (35, 30)
    ax.annotate(f"Edge rusher {name[rusher_id].split()[-1]}: delayed,\nnever reaches QB "
                f"({dq:.1f} yd away at throw)",
                (re_.x, re_.y), xytext=RUSH_OFF, textcoords="offset points",
                ha="right", va="bottom", fontsize=10.5, color=VIOLET, fontweight="bold", zorder=11,
                arrowprops=dict(arrowstyle="-", color=VIOLET, lw=0.8))
    ax.annotate(f"TE {name[chipper.nflId].split()[-1]} chips ({route.chip_len:.1f}s) then releases:\n"
                f"{chip_depth:.1f} yd past the line at throw ({t_throw:.1f}s)",
                (ce.x, ce.y), xytext=CHIP_OFF, textcoords="offset points",
                ha="left", va="bottom", fontsize=10.5, color=ORANGE, fontweight="bold", zorder=11,
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=0.8))
    ax.annotate("chip contact", (cc.x, cc.y), xytext=(0, -16), textcoords="offset points",
                ha="center", va="top", fontsize=9, color=INK2, zorder=11)

    # Crop y to the action
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    fig.text(0.04, 0.955, "Anatomy of a chip", fontsize=20, fontweight="bold", color=INK, ha="left")
    desc = play.playDescription.split(") ", 1)[-1] if ") " in play.playDescription else play.playDescription
    fig.text(0.04, 0.915,
             f"{play.possessionTeam} vs {play.defensiveTeam}, {play.down}&{play.yardsToGo}, snap to throw "
             f"({t_throw:.1f}s). {desc}",
             fontsize=11, color=INK2, ha="left")
    fig.text(0.04, 0.03,
             "Across all plays: a chip costs the chipper ~3 yd of route depth at 2s and 0.8s of release, "
             "halves the chipped rusher's pressure rate (13% -> 6%), and chip plays throw 15+ yd targets more often.",
             fontsize=9.5, color=INK2, ha="left")
    fig.subplots_adjust(left=0.03, right=0.97, top=0.89, bottom=0.07)
    out = OUT / "0_chip_play_field.png"
    fig.savefig(out, facecolor=SURFACE)
    print("saved", out)


if __name__ == "__main__":
    main()
