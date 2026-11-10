"""Route-tree small multiples: chip routes (orange) vs normal routes (white), snap to throw."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "figs" / "5_route_trees.png"
TURF, ORANGE, INK, BG = "#2e6b3a", "#ff8a3d", "#0b0b0b", "#fcfcfb"
SNAP = {"ball_snap", "autoevent_ballsnap"}
END = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run"}
# (name, pos, chip tax); left column = cheapest, right column = costliest
LAYOUT = [[("Tyler Higbee", "TE", -3.9), ("Dawson Knox", "TE", -5.6)],
          [("Travis Kelce", "TE", -4.0), ("Hunter Henry", "TE", -5.5)],
          [("Mike Davis", "RB", -0.7), ("Nyheim Hines", "RB", -2.9)]]
NAMES = [p[0] for row in LAYOUT for p in row]


def load_routes():
    cr = pd.read_parquet(ROOT / "outputs" / "chip_routes.parquet",
                         columns=["gameId", "playId", "nflId", "name", "chip"])
    cr = cr[cr.name.isin(NAMES)]
    routes = []
    for gid, g in cr.groupby("gameId"):
        f = ROOT / "data" / "tracking" / f"tracking_{gid}.csv"
        if not f.exists():
            continue
        t = pd.read_csv(f, usecols=["playId", "nflId", "frameId", "team",
                                    "playDirection", "x", "y", "event"])
        t = t[t.playId.isin(g.playId.unique())]
        left = t.playDirection == "left"
        t.loc[left, "x"] = 120 - t.loc[left, "x"]
        t.loc[left, "y"] = 53.3 - t.loc[left, "y"]
        for r in g.itertuples():
            p = t[t.playId == r.playId]
            ev = p.drop_duplicates("frameId").set_index("frameId").event
            snaps = ev[ev.isin(SNAP)].index
            if len(snaps) == 0:
                continue
            sf = snaps.min()
            ends = ev[(ev.index > sf) & ev.isin(END)].index
            ef = min(ends.min() if len(ends) else sf + 30, sf + 30)
            ball = p[(p.team == "football") & (p.frameId == sf)]
            me = p[p.nflId == r.nflId].sort_values("frameId")
            me = me[(me.frameId >= sf) & (me.frameId <= ef)]
            if ball.empty or me.empty or me.frameId.iloc[0] != sf:
                continue
            los, by = ball.x.iloc[0], ball.y.iloc[0]
            y0 = me.y.iloc[0]
            dx = me.x.values - los
            dy = me.y.values - y0
            if y0 > by:
                dy = -dy
            fr = me.frameId.values
            i2 = np.where(fr == sf + 20)[0]
            routes.append(dict(name=r.name, chip=bool(r.chip), dx=dx, dy=dy,
                               d2=(dx[i2[0]], dy[i2[0]]) if len(i2) else None))
    return routes


def draw_field(ax, ylo=-7):
    ax.set_facecolor(TURF)
    for yd in range(-5 * (-ylo // 5), 21, 5):
        ax.axhline(yd, color="white", alpha=0.5, lw=1, zorder=1)
    for yd in range(ylo, 21):  # hash ticks
        for xx in (-12, 18):
            ax.plot([xx, xx + (0.6 if xx < 0 else -0.6)], [yd, yd], color="white", alpha=0.35, lw=0.8)
    ax.axhline(0, color="white", lw=3, zorder=2)
    ax.text(-11.5, 0.4, "LOS", color="white", fontsize=10, fontweight="bold", va="bottom", zorder=6)
    ax.set_xlim(-12, 18); ax.set_ylim(ylo, 20)
    ticks = list(range(-5 * (-ylo // 5), 21, 5))
    ax.set_xticks([]); ax.set_yticks(ticks)
    ax.set_yticklabels([f"{v:+d}" if v else "0" for v in ticks], fontsize=9, color="#444")
    for s in ax.spines.values():
        s.set_visible(False)


def main():
    routes = load_routes()
    fig, axes = plt.subplots(3, 2, figsize=(13, 17.5), dpi=160, facecolor=BG)
    stats = {}
    for i, row in enumerate(LAYOUT):
        for j, (name, pos, tax) in enumerate(row):
            ylo = -10 if pos == "RB" else -7
            ax = axes[i, j]; draw_field(ax, ylo)
            rs = [r for r in routes if r["name"] == name]
            means = {}
            for chip in (False, True):
                sub = [r for r in rs if r["chip"] == chip]
                col = ORANGE if chip else "white"
                for r in sub:
                    ax.plot(r["dy"], r["dx"], color=col, lw=2.2 if chip else 1,
                            alpha=0.9 if chip else 0.25, zorder=4 if chip else 3, solid_capstyle="round")
                pts = np.array([r["d2"] for r in sub if r["d2"] is not None])
                if len(pts):
                    ax.scatter(pts[:, 1], pts[:, 0], s=18 if chip else 9, color=col,
                               edgecolor=TURF if chip else "none", lw=0.5,
                               alpha=1 if chip else 0.6, zorder=5)
                    means[chip] = pts[:, 0].mean()
                    ax.axhline(means[chip], color=col, ls="--", lw=1.8, zorder=5, alpha=0.95)
            stats[name] = (means.get(True, np.nan), means.get(False, np.nan),
                           sum(r["chip"] for r in rs), len(rs))
            ax.text(17.5, 19.3, f"Mean depth at 2.0s:\nnormal {means.get(False, np.nan):.1f} yds",
                    color="white", ha="right", va="top", fontsize=10, fontweight="bold", zorder=7)
            ax.text(17.5, 17.0, f"chip {means.get(True, np.nan):.1f} yds",
                    color=ORANGE, ha="right", va="top", fontsize=10, fontweight="bold", zorder=7)
            gap = means.get(True, np.nan) - means.get(False, np.nan)
            ax.set_title(f"{name}, {pos}: loses {abs(gap):.1f} yds per chip", loc="left",
                         fontsize=13, fontweight="bold", color=INK, pad=20)
            ax.text(0, 1.012, f"{stats[name][2]} chip routes / {stats[name][3]} routes   "
                    f"(dashed lines = mean depth at 2.0 s)", transform=ax.transAxes,
                    fontsize=9.5, color="#555", va="bottom")
            ax.text(17.6, ylo + 0.4, "outside \u2192", color="white", alpha=0.7, fontsize=9, ha="right", va="bottom")
            ax.text(-11.6, 19.3, "\u2191 downfield (yds)", color="white", alpha=0.7, fontsize=9, va="top")
    fig.text(0.04, 0.985, "Same player, chip vs no chip: where his route is when the ball comes out",
             fontsize=18, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.04, 0.965, "Orange = routes after a chip, white = his normal routes, snap to throw (max 3.0 s). "
             "Dot = position at 2.0 s.\nCheapest chippers (left) vs costliest (right). Top two rows TEs, bottom row RBs.",
             fontsize=11.5, color="#333", ha="left", va="top")
    fig.subplots_adjust(left=0.05, right=0.98, top=0.915, bottom=0.02, hspace=0.17, wspace=0.08)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, facecolor=BG)
    for n, (c, nc, k, tot) in stats.items():
        print(f"{n:15s} chip {c:5.2f}  normal {nc:5.2f}  ({k}/{tot})")


if __name__ == "__main__":
    main()
