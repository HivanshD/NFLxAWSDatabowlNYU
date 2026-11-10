"""Figures for The Chip Tax -> outputs/figs/*.png"""
from __future__ import annotations

import json
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
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#b5b3ad"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    "axes.titlesize": 13.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def load():
    R = pd.read_parquet(OUT / "chip_rushers.parquet")
    RT = pd.read_parquet(OUT / "chip_routes.parquet")
    for d in (R, RT):
        d.columns = [c.replace(".", "_") for c in d.columns]
    return R, RT, json.loads((OUT / "chip_results.json").read_text())


def fig_two_sides(R, RT):
    """Left: the chipper's route depth over time. Right: the chipped rusher's distance from the QB."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5))
    ts = [0, 1.5, 2.0, 2.5, 3.0]
    D = RT[RT.groupby("nflId").chip.transform("sum") >= 3]
    for pos, col in [("TE", BLUE), ("RB", ORANGE)]:
        for chip, ls, lw in [(False, "--", 1.6), (True, "-", 2.6)]:
            s = D[(D.pos == pos) & (D.chip == chip)]
            ys = [s.x0.mean()] + [s[f"depth_{str(t).replace('.', '_')}"].mean() for t in ts[1:]]
            a.plot(ts, ys, ls=ls, lw=lw, color=col, marker="o", ms=4)
            a.text(3.05, ys[-1], f"{pos} {'chip' if chip else 'no chip'}", color=INK if chip else INK2,
                   fontsize=9.5, va="center", fontweight="bold" if chip else "normal")
    a.axhline(0, color=INK2, lw=1)
    a.text(0.02, 0.15, "line of scrimmage", color=INK2, fontsize=9, transform=a.get_yaxis_transform())
    a.set_xlim(0, 3.6)
    a.set_xlabel("seconds after snap")
    a.set_ylabel("yards past the line of scrimmage")
    a.set_title("What the chipper pays: his route")

    Rc = R[R.groupby("nflId").chipped.transform("sum") >= 3]
    for chip, col, lab in [(False, GRAY, "not chipped"), (True, BLUE, "chipped")]:
        s = Rc[Rc.chipped == chip]
        ys = [s.dq0.mean(), s.dq_1_5.mean(), s.dq_2_0.mean(), s.dq_2_5.mean()]
        b.plot(ts[:4], ys, color=col, lw=2.6 if chip else 1.8, marker="o", ms=4)
        b.text(2.55, ys[-1], lab, color=INK, fontsize=10, va="center", fontweight="bold" if chip else "normal")
    b.set_xlim(0, 3.1)
    b.set_ylim(bottom=0)
    b.set_xlabel("seconds after snap")
    b.set_ylabel("edge rusher's distance to the QB (yds)")
    b.set_title("What the QB gets: the rusher stays ~1 yd away")
    fig.suptitle("The Chip Tax: one route pays for one rusher", x=0.01, ha="left", fontsize=16, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIGS / "1_two_sides_of_a_chip.png", dpi=160)
    plt.close(fig)


def fig_receipt(res, RT):
    c, b, r = res["cost"], res["benefit"], res["receipt"]
    D = RT[RT.groupby("nflId").chip.transform("sum") >= 3]
    ci = lambda e, k=1: f"95% CI {k * (e['est'] - 1.96 * e['se']):+.1f} to {k * (e['est'] + 1.96 * e['se']):+.1f}"
    pay = [
        (f"{c['t_release']['est']:+.1f} s", "later into his route", ci(c["t_release"])),
        (f"{c['depth_2_0']['est']:+.1f} yds", f"route depth at 2.0s (from {D[~D.chip].depth_2_0.mean():+.1f})", ci(c["depth_2_0"])),
        (f"{c['targeted']['est'] * 100:+.0f} pts", f"chance he's targeted (from {c['target_rate_nochip']:.0%})", ci(c["targeted"], 100)),
    ]
    get = [
        (f"{b['pressure']['est'] * 100:+.1f} pts", f"pressure by the chipped rusher (from {b['pressure_rate_unchipped']:.0%})", ci(b["pressure"], 100)),
        (f"{r['sack']['est'] * 100:+.1f} pts", f"sack rate (from {r['sack']['base']:.1%})", ci(r["sack"], 100)),
        (f"{r['deep']['est'] * 100:+.1f} pts", f"targets 15+ yds downfield (from {r['deep']['base']:.0%})", ci(r["deep"], 100)),
        (f"{r['playResult']['est']:+.1f} yds", f"per play (from {r['playResult']['base']:.1f})", ci(r["playResult"])),
    ]
    fig = plt.figure(figsize=(12, 5.6))
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.text(0.03, 0.93, "THE CHIP TAX: the receipt", fontsize=18, fontweight="bold", color=INK)
    ax.text(0.03, 0.87, f"{res['n_chips']:,} chips by TEs/RBs, 2021 Wks 1-8. Every line is a controlled comparison.",
            fontsize=10, color=INK2)
    for x0, title, col, items, sub in [
        (0.03, "THE CHIPPER PAYS", ORANGE, pay, "same player: chip routes vs his own non-chip routes"),
        (0.52, "THE OFFENSE GETS", BLUE, get, "same rusher chipped vs not; plays vs same protection + same hold time")]:
        ax.text(x0, 0.76, title, fontsize=13, fontweight="bold", color=col)
        ax.text(x0, 0.715, sub, fontsize=8.5, color=INK2)
        for i, (big, lab, cix) in enumerate(items):
            y = 0.6 - i * 0.14
            ax.text(x0, y, big, fontsize=20, fontweight="bold", color=col, va="center")
            ax.text(x0 + 0.15, y + 0.02, lab, fontsize=10.5, color=INK, va="center")
            ax.text(x0 + 0.15, y - 0.035, cix, fontsize=8.5, color=INK2, va="center")
    ax.plot([0.5, 0.5], [0.05, 0.78], color=GRID, lw=1.5)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.savefig(FIGS / "2_the_receipt.png", dpi=160)
    plt.close(fig)


def fig_tax_by_player():
    t = pd.read_csv(OUT / "chip_tax_by_player.csv")
    t = t[t.pos.isin(["TE", "RB"])].sort_values(["pos", "chip_tax"], ascending=[False, True])
    fig, ax = plt.subplots(figsize=(10, 11))
    cols = {"TE": BLUE, "RB": ORANGE}
    y = np.arange(len(t))[::-1]
    for yi, row in zip(y, t.itertuples()):
        strong = row.verdict != "about average"
        c = cols[row.pos]
        ax.errorbar(row.chip_tax, yi, xerr=1.28 * row.chip_tax_sd, color=c if strong else GRAY, lw=1.6, capsize=0, zorder=2)
        ax.scatter(row.chip_tax, yi, s=70 if strong else 40, color=c if strong else SURFACE, edgecolor=c, lw=1.8, zorder=3)
        ax.text(0.15, yi, f"{row.chips}", va="center", fontsize=8, color=INK2)
    for pos in ["TE", "RB"]:
        s = t[t.pos == pos]
        ys = y[(t.pos == pos).values]
        ax.plot([s.pos_mean.iat[0]] * 2, [ys.min() - 0.5, ys.max() + 0.5], color=cols[pos], ls=":", lw=1.2)
        ax.text(s.pos_mean.iat[0], ys.max() + 0.7, f"{pos} average {s.pos_mean.iat[0]:.1f}", ha="center", fontsize=9, color=INK2)
    ax.text(0.15, y.max() + 1.2, "chips", fontsize=8, color=INK2)
    labels = [f"{n} ({p})" for n, p in zip(t.name, t.pos)]
    ax.set_yticks(y, labels, fontsize=9)
    for tl, row in zip(ax.get_yticklabels(), t.itertuples()):
        tl.set_fontweight("bold" if row.verdict != "about average" else "normal")
        tl.set_color(INK if row.verdict != "about average" else INK2)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_xlim(t.chip_tax.min() - 1.5, 0.6)
    ax.set_xlabel("Chip Tax: route depth lost at 2.0s when he chips (yds), shrunk toward position average; bars = 80% interval")
    ax.grid(axis="y", visible=False)
    ax.set_title("The Chip Tax by player: a back pays ~2 yds, a tight end ~5.\nBold = clearly cheaper or costlier than his position (filled dot)")
    fig.tight_layout()
    fig.savefig(FIGS / "3_chip_tax_by_player.png", dpi=160)
    plt.close(fig)


def fig_open_but_harmless(RT):
    t = RT[RT.targeted.fillna(False) & RT.passResult.isin(["C", "I", "IN"])]
    fig, ax = plt.subplots(figsize=(10, 6))
    n, c = t[~t.chip], t[t.chip]
    ax.scatter(n.depth_end, n.sep_end, s=10, color=GRAY, alpha=0.35, label=f"TE/RB targets, no chip (n={len(n)})", lw=0)
    ax.scatter(c.depth_end, c.sep_end, s=34, color=ORANGE, alpha=0.9, edgecolor=SURFACE, lw=1,
               label=f"targets after a chip (n={len(c)})")
    for d, col, nm in [(n, INK2, "no chip"), (c, ORANGE, "after chip")]:
        ax.scatter([d.depth_end.median()], [d.sep_end.median()], s=180, marker="X", color=col, edgecolor=INK, lw=1, zorder=5)
        ax.annotate(f"median {nm}: {d.depth_end.median():.1f} yds deep, {d.sep_end.median():.1f} yds open",
                    (d.depth_end.median(), d.sep_end.median()), xytext=(12, 12 if nm == "after chip" else -18),
                    textcoords="offset points", fontsize=10, color=INK, fontweight="bold")
    ax.axvline(0, color=INK2, lw=1)
    ax.set_xlim(-8, 25)
    ax.set_ylim(0, 20)
    ax.set_xlabel("yards past the line of scrimmage when the ball is thrown")
    ax.set_ylabel("yards to nearest coverage defender")
    ax.set_title("Why chippers 'catch 80%': wide open, at the line, and nobody cares")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(FIGS / "4_open_but_harmless.png", dpi=160)
    plt.close(fig)


def fig_dumbbell(res):
    """Before -> after for every rate a chip moves (all in %, one honest axis)."""
    c, b, r = res["cost"], res["benefit"], res["receipt"]
    rows = [  # label, base %, effect est, se (in pts), side
        ("Chipper is targeted", c["target_rate_nochip"] * 100, c["targeted"]["est"] * 100, c["targeted"]["se"] * 100, "cost"),
        ("Chipped rusher pressures the QB", b["pressure_rate_unchipped"] * 100, b["pressure"]["est"] * 100, b["pressure"]["se"] * 100, "buy"),
        ("Play ends in a sack", r["sack"]["base"] * 100, r["sack"]["est"] * 100, r["sack"]["se"] * 100, "buy"),
        ("Target is 15+ yds downfield", r["deep"]["base"] * 100, r["deep"]["est"] * 100, r["deep"]["se"] * 100, "buy"),
    ]
    fig, ax = plt.subplots(figsize=(12.5, 4.6))
    y = np.arange(len(rows))[::-1]
    for yi, (lab, base, est, se, side) in zip(y, rows):
        after = base + est
        col = ORANGE if side == "cost" else BLUE
        ax.plot([base, after], [yi, yi], color=col, lw=3, alpha=0.5, solid_capstyle="round")
        ax.errorbar(after, yi, xerr=1.96 * se, color=col, lw=1.2, capsize=3)
        ax.scatter(base, yi, s=90, color=SURFACE, edgecolor=INK2, lw=1.8, zorder=3)
        ax.scatter(after, yi, s=110, color=col, edgecolor=SURFACE, lw=1.5, zorder=4)
        lo, hi = sorted([base, after])
        ax.text(lo - 0.6, yi, f"{base:.0f}%" if base == lo else f"{after:.0f}%", ha="right", va="center", fontsize=10,
                color=INK2 if base == lo else INK, fontweight="normal" if base == lo else "bold")
        ax.text(hi + 0.6, yi, f"{after:.0f}%" if after == hi else f"{base:.0f}%", ha="left", va="center", fontsize=10,
                color=INK if after == hi else INK2, fontweight="bold" if after == hi else "normal")
    ax.set_yticks(y, [r_[0] for r_ in rows])
    ax.set_xlim(0, 24)
    ax.set_xlabel("rate (%)   hollow = no chip, filled = chip (95% CI)")
    ax.grid(axis="y", visible=False)
    ax.set_title("What a chip moves: the chipper leaves the target list, the rush fades, throws go deeper")
    fig.text(0.01, 0.01, "Orange = cost to the chipper; blue = what the offense gets. Controlled: same player / same rusher / same protection + hold time.",
             fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGS / "2b_what_a_chip_moves.png", dpi=160)
    plt.close(fig)


def main():
    FIGS.mkdir(parents=True, exist_ok=True)
    R, RT, res = load()
    fig_two_sides(R, RT)
    fig_receipt(res, RT)
    fig_dumbbell(res)
    fig_tax_by_player()
    fig_open_but_harmless(RT)
    print("figures ->", FIGS)


if __name__ == "__main__":
    main()
