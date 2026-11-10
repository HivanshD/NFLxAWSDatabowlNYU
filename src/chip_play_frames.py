"""NGS-style freeze-frames of one chip play -> outputs/figs/0_chip_play_field.png
Snap -> chip contact -> throw, on a turf field, offense moving up the page."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GAME, PLAY = 2021101707, 306          # KC vs WAS: Kelce chips, Mahomes hits Hill deep for 19
TURF, LINE, INK, INK2, SURFACE = "#2e6b3a", "#ffffff", "#0b0b0b", "#52514e", "#fcfcfb"
ORANGE, VIOLET, BLUE, GOLD = "#ff8a3d", "#b9a8ff", "#7fb8ff", "#ffd166"
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward"}


def load():
    t = pd.read_csv(ROOT / "data" / "tracking" / f"tracking_{GAME}.csv")
    t = t[t.playId == PLAY].copy()
    L = t.playDirection == "left"
    t.loc[L, "x"] = 120 - t.loc[L, "x"]
    t.loc[L, "y"] = 160 / 3 - t.loc[L, "y"]
    pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv")
    pff = pff[(pff.gameId == GAME) & (pff.playId == PLAY)]
    pl = pd.read_csv(ROOT / "data" / "players.csv", usecols=["nflId", "displayName"])
    pff = pff.merge(pl, on="nflId")
    desc = pd.read_csv(ROOT / "data" / "plays.csv").set_index(["gameId", "playId"]).loc[(GAME, PLAY)]
    return t, pff, desc


def main():
    t, pff, desc = load()
    ev = t.drop_duplicates("frameId").set_index("frameId").event
    snap = ev[ev.isin(SNAP)].index.min()
    throw = ev[(ev.index > snap) & ev.isin(END)].index.min()
    who = lambda last: int(pff[pff.displayName.str.endswith(last)].nflId.iat[0])
    kelce, qb, hill, robinson = who("Kelce"), int(pff[pff.pff_role == "Pass"].nflId.iat[0]), who("Hill"), who("Robinson")
    rusher = int(pff[pff.nflId == kelce].pff_nflIdBlockedPlayer.iat[0])
    rname = pff[pff.nflId == rusher].displayName.iat[0].split()[-1]
    P = {c: t.pivot_table(index="frameId", columns="nflId", values=c) for c in ["x", "y"]}
    jersey = t.dropna(subset=["nflId"]).groupby("nflId").jerseyNumber.first().astype(int)
    team = t.dropna(subset=["nflId"]).groupby("nflId").team.first()
    off_team = team[qb]
    ball = t[t.team == "football"].set_index("frameId")
    los = ball.loc[snap, "x"]
    d = np.hypot(P["x"][kelce] - P["x"][rusher], P["y"][kelce] - P["y"][rusher])
    contact = d[(d.index > snap) & (d < 1.5)].index.min()

    key = {kelce: ("Kelce", ORANGE), rusher: (rname, VIOLET), qb: ("Mahomes", GOLD), hill: ("Hill", BLUE), robinson: ("Robinson", BLUE)}
    frames = [(snap, "1 · SNAP", "Kelce lines up next to the tackle,\nacross from the edge rusher"),
              (contact, f"2 · THE CHIP ({(contact - snap) / 10:.1f}s)", f"Kelce bumps {rname} instead of\nreleasing into his route"),
              (throw, f"3 · THE THROW ({(throw - snap) / 10:.1f}s)",
               f"{rname} never reaches Mahomes, but Kelce is only\n{P['x'][kelce][throw] - los:.1f} yds past the line. Hill is {P['x'][hill][throw] - los:.0f} yds deep")]

    ys = pd.concat([P["y"].loc[snap:throw]]).stack()
    ylo, yhi = max(0, ys.min() - 3), min(160 / 3, ys.max() + 7)
    fig, axes = plt.subplots(1, 3, figsize=(18, 8.6), facecolor=SURFACE)
    for ax, (f, title, sub) in zip(axes, frames):
        ax.set_facecolor(TURF)
        for yd in range(int(los) - 15, int(los) + 30, 5):
            ax.axhline(yd - los, color=LINE, lw=0.8, alpha=0.35)
        ax.axhline(0, color="#4da3ff", lw=2.5, alpha=0.9)
        ax.text(ylo + 0.5, 0.4, "line of scrimmage", color="#cfe6ff", fontsize=8.5, va="bottom")
        # everyone else: faint dots
        for pid in P["x"].columns:
            if pid in key or np.isnan(P["x"][pid].get(f, np.nan)):
                continue
            off = team.get(pid) == off_team
            ax.scatter(P["y"][pid][f], P["x"][pid][f] - los, s=55, color="white" if off else "#16263f",
                       edgecolor="white", lw=0.8, alpha=0.45, zorder=3)
        # key players: trail to this frame + numbered dot
        for pid, (nm, col) in key.items():
            tr_x = P["x"][pid].loc[snap:f] - los
            tr_y = P["y"][pid].loc[snap:f]
            ax.plot(tr_y, tr_x, color=col, lw=2.6, alpha=0.9, zorder=4)
            ax.scatter(tr_y.iat[-1], tr_x.iat[-1], s=330, color=col, edgecolor="white", lw=1.6, zorder=5)
            ax.text(tr_y.iat[-1], tr_x.iat[-1], str(jersey[pid]), ha="center", va="center", fontsize=8.5,
                    fontweight="bold", color=INK, zorder=6)
            right = tr_y.iat[-1] > yhi - 6
            ax.text(tr_y.iat[-1] + (-1.1 if right else 1.1), tr_x.iat[-1] + 0.6, nm, color="white", fontsize=10,
                    fontweight="bold", zorder=6, ha="right" if right else "left")
        if f == throw:
            catch = (P["y"][hill].iloc[-1], P["x"][hill].iloc[-1] - los)
            ax.annotate("", xy=catch, xytext=(P["y"][qb][f], P["x"][qb][f] - los),
                        arrowprops=dict(arrowstyle="-|>", color="white", lw=1.6, ls="--"), zorder=4)
            ax.text(catch[0], catch[1] + 1.0, "caught, +19", color="white", fontsize=9.5, ha="center", fontweight="bold")
        ax.set_xlim(ylo, yhi)
        ax.set_ylim(-12, 22)
        ax.set_xticks([])
        ax.set_yticks(range(-10, 21, 5), [f"{v:+d}" if v else "LOS" for v in range(-10, 21, 5)])
        ax.tick_params(colors=INK2, labelsize=9)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=34)
        ax.text(0, 1.01, sub, transform=ax.transAxes, fontsize=10.5, color=INK2, va="bottom")
    axes[0].set_ylabel("yards downfield", color=INK2)
    fig.suptitle("Anatomy of a chip: the rusher never gets home, and neither does Kelce's route",
                 x=0.01, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(0.01, 0.905, f"KC vs WAS, 2021 Week 6. {desc.playDescription.split(') ', 1)[-1]}  "
             f"Orange = chipper, violet = chipped rusher, gold = QB, blue = WRs; offense moves up.",
             fontsize=10, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(ROOT / "outputs" / "figs" / "0_chip_play_field.png", dpi=160, facecolor=SURFACE)
    print("contact", (contact - snap) / 10, "throw", (throw - snap) / 10, "kelce depth", P["x"][kelce][throw] - los)


if __name__ == "__main__":
    main()
