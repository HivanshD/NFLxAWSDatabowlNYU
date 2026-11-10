"""Static figures for the README (outputs/figs/*.png)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIGS = OUT / "figs"

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, RED, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#6250d6"
GRAY = "#b5b3ad"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
})

EXAMPLE = (2021101706, 982)


def fig_example_play(r, curves, plays):
    gid, pid = EXAMPLE
    p = plays.set_index(["gameId", "playId"]).loc[(gid, pid)]
    rp = r[(r.gameId == gid) & (r.playId == pid)]
    cp = curves[(curves.gameId == gid) & (curves.playId == pid)]
    clock = rp.clock.iat[0]

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.axhspan(0, 2.5, color=GRID, alpha=0.5, lw=0)
    ax.text(0.05, 1.2, "covered  (< 2.5 yds)", color=INK2, fontsize=9, va="center")
    ends = cp.sort_values("t").groupby("nflId").sep.last().sort_values()
    label_y, last = {}, -9
    for nid, y in ends.items():
        last = max(y, last + 0.45)
        label_y[nid] = last
    for row in rp.sort_values("t_win").itertuples():
        c = cp[cp.nflId == row.nflId]
        won = row.beat
        ax.plot(c.t, c.sep, color=BLUE if won else GRAY, lw=2.4 if won else 1.6, zorder=3)
        label = f"{row.name} ({row.pos})"
        ax.text(c.t.iat[-1] + 0.05, label_y[row.nflId], label, color=INK if won else INK2,
                fontsize=9.5, va="center", fontweight="bold" if won else "normal")
        if won:
            ax.scatter([row.t_win], [c.sep[c.t == row.t_win].iat[0]], s=70, color=BLUE,
                       edgecolor=SURFACE, linewidth=2, zorder=4)
            ax.annotate(f"wins at {row.t_win:.1f}s", (row.t_win, c.sep[c.t == row.t_win].iat[0]),
                        xytext=(-8, -16), textcoords="offset points", color=INK, fontsize=10,
                        ha="right")
            after = c[(c.t >= row.t_win)]
            closed = after[after.sep < 2.5]
            w_end = closed.t.iat[0] if len(closed) else clock
            ax.axvspan(row.t_win, w_end, color=BLUE, alpha=0.10, lw=0)
            ax.text((row.t_win + w_end) / 2, 0.985, f"open window {row.t_win:.1f}–{w_end:.1f}s\n"
                    f"no throw — sack came {clock - row.t_win:.1f}s later", ha="center", va="top",
                    color=INK, fontsize=9.5, fontweight="bold", transform=ax.get_xaxis_transform())
    ax.axvline(clock, color=ORANGE, lw=2.2, zorder=2)
    ax.text(clock + 0.04, 0.6, "rush arrives\n(sack)", color=INK,
            fontsize=10, va="top")
    ax.set_xlim(0, clock + 1.3)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("seconds after snap")
    ax.set_ylabel("yards to nearest coverage defender")
    ax.set_title(f"The race on one play: {p.possessionTeam} vs {p.defensiveTeam}, {p.pff_passCoverage}")
    fig.text(0.125, 0.905, p.playDescription[:110], color=INK2, fontsize=9.5)
    fig.subplots_adjust(top=0.86, right=0.8)
    fig.savefig(FIGS / "1_race_one_play.png", dpi=160)
    plt.close(fig)


def fig_league_race(r, val):
    plays = r.drop_duplicates(["gameId", "playId"])
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.7, 1]})
    bins = np.arange(0, 6.01, 0.2)
    for data, col, lab in [(plays.t_pressure.dropna(), ORANGE, "rush reaches QB (pressured plays)"),
                           (r.t_win.dropna(), BLUE, "receiver first wins (earned 2.5+ yds)")]:
        h, e = np.histogram(data, bins=bins, density=True)
        ax.fill_between(e[:-1], h, step="post", color=col, alpha=0.18, lw=0)
        ax.step(e[:-1], h, where="post", color=col, lw=2, label=lab)
    ymax = ax.get_ylim()[1]
    for s_, col, txt, yy in [(r.t_win.median(), BLUE, "receivers win", 0.95),
                             (plays.t_pressure.median(), ORANGE, "rush arrives", 0.78)]:
        ax.axvline(s_, color=col, lw=1.5, ls="--")
        ax.text(s_ + 0.06, ymax * yy, f"median {txt}: {s_:.1f}s", fontsize=9.5, color=INK)
    ax.set_xlim(0, 6)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("seconds after snap")
    ax.set_yticks([])
    gap = plays.t_pressure.median() - r.t_win.median()
    ax.set_title(f"The race: receivers win only ~{gap:.1f}s before the rush arrives")
    ax.legend(frameon=False, loc="center right", fontsize=9.5)

    labels = ["Lost the race", "Beat the rush"]
    vals = [val.loc[False, "yds_per_target"], val.loc[True, "yds_per_target"]]
    bars = ax2.bar(labels, vals, color=[GRAY, BLUE], width=0.55)
    for b, v, comp in zip(bars, vals, [val.loc[False, "comp_pct"], val.loc[True, "comp_pct"]]):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.2, f"{v:.1f} yds\n{comp:.0%} comp",
                 ha="center", color=INK, fontsize=10)
    ax2.set_ylim(0, max(vals) * 1.3)
    ax2.set_ylabel("yards per target")
    ax2.grid(axis="x", visible=False)
    ax2.set_title(f"Winning it = +{vals[1]-vals[0]:.1f} yds/target")
    fig.tight_layout()
    fig.savefig(FIGS / "2_the_race.png", dpi=160)
    plt.close(fig)


def fig_sacks(sacks):
    order = ["Receiver open ≥0.5s, ball held", "Receiver open <0.5s before rush",
             "Coverage won: nobody open"]
    cols = {order[0]: BLUE, order[1]: "#86b6ef", order[2]: GRAY}
    share = sacks.verdict.value_counts(normalize=True).reindex(order)
    fig, ax = plt.subplots(figsize=(11, 2.6))
    left = 0
    for k in order:
        ax.barh([0], [share[k]], left=left, color=cols[k], edgecolor=SURFACE, linewidth=2, height=0.6)
        ax.text(left + share[k] / 2, 0, f"{share[k]:.0%}", ha="center", va="center",
                color=SURFACE if k != order[1] else INK, fontsize=15, fontweight="bold")
        ax.text(left + share[k] / 2, -0.48, k, ha="center", va="top", color=INK2, fontsize=10)
        left += share[k]
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.9, 0.5)
    ax.axis("off")
    ax.set_title(f"Who owns the sack? {len(sacks)} sacks, Weeks 1-8 of 2021", pad=8)
    fig.tight_layout()
    fig.savefig(FIGS / "3_sack_blame.png", dpi=160)
    plt.close(fig)


def fig_man_zone(rec):
    d = rec[(rec.pos.isin(["WR", "TE"])) & (rec.n_man >= 40) & (rec.n_zone >= 60)].copy()
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axhline(0, color=INK2, lw=1)
    ax.axvline(0, color=INK2, lw=1)
    for pos, col in [("WR", BLUE), ("TE", AQUA)]:
        s = d[d.pos == pos]
        ax.scatter(s.broe_man * 100, s.broe_zone * 100, s=40, color=col, alpha=0.85,
                   edgecolor=SURFACE, linewidth=1.5, label=pos, zorder=3)
    d["score"] = np.hypot(d.broe_man, d.broe_zone) + (d.broe_man - d.broe_zone).abs()
    lab = d.nlargest(22, "score")
    for row in lab.itertuples():
        ax.annotate(row.name, (row.broe_man * 100, row.broe_zone * 100), xytext=(5, 4),
                    textcoords="offset points", fontsize=8.5, color=INK)
    lim = max(abs(d.broe_man).max(), abs(d.broe_zone).max()) * 100 + 3
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    kw = dict(fontsize=11, color=INK2, fontweight="bold")
    ax.text(lim - 1, lim - 1, "Beats everything", ha="right", va="top", **kw)
    ax.text(-lim + 1, lim - 1, "Zone-beater only\n→ play him man", ha="left", va="top", **kw)
    ax.text(lim - 1, -lim + 1, "Man-beater only\n→ play him zone", ha="right", va="bottom", **kw)
    ax.text(-lim + 1, -lim + 1, "Loses the race either way", ha="left", va="bottom", **kw)
    ax.set_xlabel("vs MAN: beat-the-rush rate over expected (pct pts)")
    ax.set_ylabel("vs ZONE: beat-the-rush rate over expected (pct pts)")
    ax.set_title("The coverage tell: which receivers only win against one coverage family")
    ax.legend(frameon=False, loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(FIGS / "4_man_zone_tell.png", dpi=160)
    plt.close(fig)


def fig_leaderboard(rec):
    fig, axes = plt.subplots(1, 3, figsize=(15, 6.2))
    for ax, pos in zip(axes, ["WR", "TE", "RB"]):
        s = rec[rec.pos == pos]
        n = 10 if pos != "RB" else 8
        s = pd.concat([s.nlargest(n, "broe"), s.nsmallest(5, "broe").iloc[::-1]]).drop_duplicates("nflId")
        s = s.iloc[::-1]
        cols = [BLUE if v > 0 else GRAY for v in s.broe]
        y = np.arange(len(s))
        ax.barh(y, s.broe * 100, color=cols, height=0.65)
        ax.set_yticks(y, [f"{n} ({t})" for n, t in zip(s.name, s.team)], fontsize=9)
        ax.axvline(0, color=INK2, lw=1)
        ax.grid(axis="y", visible=False)
        ax.set_title(f"{pos}s (min {100} routes)")
        ax.set_xlabel("beat-the-rush % over expected")
    fig.suptitle("Beat-the-Rush Over Expected: who creates separation before the pocket breaks",
                 x=0.01, ha="left", fontsize=15, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(FIGS / "5_leaderboard.png", dpi=160)
    plt.close(fig)


def main():
    FIGS.mkdir(parents=True, exist_ok=True)
    r = pd.read_parquet(OUT / "routes_scored.parquet")
    curves = pd.read_parquet(OUT / "sep_curves.parquet")
    plays = pd.read_csv(ROOT / "data" / "plays.csv")
    rec = pd.read_csv(OUT / "receivers.csv")
    sacks = pd.read_csv(OUT / "sacks.csv")
    val = pd.read_csv(OUT / "validation_targets.csv", index_col=0)
    val.index = val.index.astype(str).map({"True": True, "False": False})

    fig_example_play(r, curves, plays)
    fig_league_race(r, val)
    fig_sacks(sacks)
    fig_man_zone(rec)
    fig_leaderboard(rec)
    print("figures ->", FIGS)


if __name__ == "__main__":
    main()
