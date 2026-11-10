"""NGS-style animated GIF of one chip play -> outputs/figs/0_chip_play.gif
Same play as chip_play_frames.py (KC vs WAS, 2021 Wk 6): real time at 10 Hz, offense moving up the page."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GAME, PLAY = 2021101707, 306          # KC vs WAS: Kelce chips, Mahomes hits Hill deep for 19
TURF, LINE, INK, INK2, SURFACE = "#2e6b3a", "#ffffff", "#0b0b0b", "#52514e", "#fcfcfb"
ORANGE, VIOLET, BLUE, GOLD, NAVY = "#ff8a3d", "#b9a8ff", "#7fb8ff", "#ffd166", "#16263f"
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward"}
FPS, PRE, POST, HOLD, TRAIL, CAP = 10, 5, 10, 15, 10, 12   # frames: pre-snap, post-throw, final hold, trail, caption life


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
    return t, pff


def main():
    t, pff = load()
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
    kdepth, hdepth = P["x"][kelce][throw] - los, P["x"][hill][throw] - los

    key = {kelce: ("Kelce", ORANGE), rusher: (rname, VIOLET), qb: ("Mahomes", GOLD), hill: ("Hill", BLUE), robinson: ("Robinson", BLUE)}
    first, last = max(P["x"].index.min(), snap - PRE), min(P["x"].index.max(), throw + POST)
    seq = list(range(first, last + 1)) + [last] * HOLD
    events = [(snap, "SNAP"), (contact, f"Kelce chips {rname}"),
              (throw, f"THROW: Kelce {kdepth:.1f} yds past the line, Hill {hdepth:.0f} yds deep"),
              (throw + 4, "Caught, +19")]

    ys = P["y"].loc[first:last].stack()
    ylo, yhi = max(0, ys.min() - 3), min(160 / 3, ys.max() + 4)
    others = [p for p in P["x"].columns if p not in key]
    others_col = ["white" if team.get(p) == off_team else NAVY for p in others]

    fig, ax = plt.subplots(figsize=(8, 8.5), facecolor=SURFACE)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.90, bottom=0.115)

    def draw(f):
        ax.clear()
        ax.set_facecolor(TURF)
        for yd in range(-10, 21, 5):
            ax.axhline(yd, color=LINE, lw=0.8, alpha=0.35)
        ax.axhline(0, color="#4da3ff", lw=2.5, alpha=0.9)
        ax.text(ylo + 0.5, 0.4, "line of scrimmage", color="#cfe6ff", fontsize=8.5, va="bottom")
        xs, yv = P["x"].loc[f, others] - los, P["y"].loc[f, others]
        ok = xs.notna().values
        ax.scatter(yv[ok], xs[ok], s=55, c=np.array(others_col)[ok], edgecolor="white", lw=0.8, alpha=0.5, zorder=3)
        for pid, (nm, col) in key.items():
            tr_x = P["x"][pid].loc[max(first, f - TRAIL):f] - los
            tr_y = P["y"][pid].loc[max(first, f - TRAIL):f]
            n = len(tr_x)
            for i in range(1, n):   # fading trail: older segments more transparent
                ax.plot(tr_y.iloc[i - 1:i + 1], tr_x.iloc[i - 1:i + 1], color=col, lw=2.6,
                        alpha=0.9 * i / n, zorder=4, solid_capstyle="round")
            px, py = tr_x.iat[-1], tr_y.iat[-1]
            ax.scatter(py, px, s=300, color=col, edgecolor="white", lw=1.6, zorder=5)
            ax.text(py, px, str(jersey[pid]), ha="center", va="center", fontsize=8, fontweight="bold", color=INK, zorder=6)
            right = py > yhi - 7 or pid == rusher   # rusher label on the left so it never sits on Kelce's
            if pid == qb:   # QB label under the dot: the rusher ends up right next to him
                ax.text(py, px - 1.0, nm, color="white", fontsize=9.5, fontweight="bold", zorder=6, ha="center", va="top")
            else:
                ax.text(py + (-1.1 if right else 1.1), px + 0.6, nm, color="white", fontsize=9.5,
                        fontweight="bold", zorder=6, ha="right" if right else "left")
        if f in ball.index:
            ax.scatter(ball.loc[f, "y"], ball.loc[f, "x"] - los, s=45, color="#8b4513", edgecolor="white", lw=1.2, zorder=4.5)  # under key dots: hidden while in the QB's hands
        clock = "pre-snap" if f < snap else f"t = {(f - snap) / 10:.1f} s after snap"
        ax.text(0.02, 0.975, clock, transform=ax.transAxes, color="white", fontsize=12, fontweight="bold", va="top", zorder=8)
        caps = [txt for ef, txt in events if ef <= f < ef + CAP or (f == last and ef >= throw)]
        for i, txt in enumerate(caps[-2:]):   # captions live below the field so they never cover players
            ax.text(0.5, -0.025 - 0.05 * i, txt, transform=ax.transAxes, ha="center", va="top", color=INK,
                    fontsize=11, fontweight="bold", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.35", fc="#ffe9d6" if "chip" in txt else "#eeeeee", ec="none"))
        ax.set_xlim(ylo, yhi)
        ax.set_ylim(-12, 22)
        ax.set_xticks([])
        ax.set_yticks(range(-10, 21, 5), [f"{v:+d}" if v else "LOS" for v in range(-10, 21, 5)])
        ax.tick_params(colors=INK2, labelsize=9)
        ax.set_ylabel("yards downfield", color=INK2)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title("Anatomy of a chip (KC vs WAS, 2021 Wk 6)", loc="left", fontsize=15, fontweight="bold", color=INK, pad=24)
        ax.text(0, 1.01, "Orange = Kelce (chipper), violet = chipped rusher, gold = Mahomes, blue = WRs",
                transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom")

    out = ROOT / "outputs" / "figs" / "0_chip_play.gif"
    anim = FuncAnimation(fig, draw, frames=seq, interval=1000 / FPS)
    anim.save(out, writer=PillowWriter(fps=FPS), dpi=90, savefig_kwargs={"facecolor": SURFACE})
    print(out, f"{out.stat().st_size / 1e6:.2f} MB", len(seq), "frames",
          "contact", (contact - snap) / 10, "throw", (throw - snap) / 10, "kelce depth", round(kdepth, 2), "hill", round(hdepth, 1))


if __name__ == "__main__":
    main()
