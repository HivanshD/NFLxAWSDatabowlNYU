"""What makes a cheap chipper? Chip mechanics (from tracking) vs route depth after the chip.
Writes outputs/chip_mechanics.json."""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.formula.api as smf
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "outputs"
RT = pd.read_parquet(OUT / "chip_routes.parquet"); RT.columns = [c.replace(".", "_") for c in RT.columns]
c = RT[RT.chip & RT.pos.isin(["TE", "RB"])].dropna(subset=["chip_len", "chip_start", "depth_2_0"]).copy()
c["start_depth"] = c.x0                                         # yds from LOS at snap (negative = behind)
c["al"] = c.aligned.fillna("UNK").str.replace(r"[LR]$", "", regex=True)
c["len_bin"] = pd.cut(c.chip_len, [0, 0.4, 0.7, 10], labels=["quick (<=0.4s)", "medium (0.5-0.7s)", "long (>0.7s)"])
c["start_bin"] = pd.cut(c.chip_start, [-1, 0.7, 1.2, 10], labels=["early (<=0.7s)", "mid (0.8-1.2s)", "late (>1.2s)"])
res = {}
for col in ["len_bin", "start_bin"]:
    g = c.groupby(["pos", col], observed=True).agg(n=("depth_2_0", "size"), depth2=("depth_2_0", "mean"), tgt=("targeted", lambda s: s.fillna(False).mean()))
    print(g.round(2)); res[col] = g.round(3).reset_index().astype(str).to_dict("records")
g = c[c.pos == "TE"].groupby("al").agg(n=("depth_2_0", "size"), depth2=("depth_2_0", "mean"), start=("start_depth", "mean")).query("n>=20")
print(g.round(2)); res["te_alignment"] = g.round(3).reset_index().astype(str).to_dict("records")
for pos in ["TE", "RB"]:
    d = c[c.pos == pos]
    m = smf.ols("depth_2_0 ~ chip_len + chip_start + start_depth + C(down) + pff_playAction", d.assign(pff_playAction=d.pff_playAction.fillna(0))).fit(cov_type="HC1")
    res[f"ols_{pos}"] = {k: {"est": float(m.params[k]), "se": float(m.bse[k])} for k in ["chip_len", "chip_start", "start_depth"]}
    print(pos, {k: f"{m.params[k]:+.2f} (se {m.bse[k]:.2f})" for k in ["chip_len", "chip_start", "start_depth"]}, "n", int(m.nobs))
# cheap vs costly chippers: their mechanics
tab = pd.read_csv(OUT / "chip_tax_by_player.csv")
mech = c.groupby("nflId").agg(chip_len=("chip_len", "mean"), chip_start=("chip_start", "mean"), start_depth=("start_depth", "mean"))
t = tab.merge(mech, left_on="nflId", right_index=True)
t["group"] = np.where(t.verdict.str.contains("less"), "cheap", np.where(t.verdict.str.contains("more"), "costly", "average"))
g = t[t.pos == "TE"].groupby("group")[["chip_len", "chip_start", "start_depth", "chip_tax"]].mean()
print(g.round(2)); res["te_cheap_vs_costly"] = g.round(3).reset_index().to_dict("records")
r = t[t.pos == "TE"][["chip_tax", "chip_len", "chip_start", "start_depth"]].corr().chip_tax
print("TE player-level corr with chip_tax (higher = cheaper):", r.round(2).to_dict()); res["te_player_corr"] = r.round(3).to_dict()
(OUT / "chip_mechanics.json").write_text(json.dumps(res, indent=2, default=str))

# ---- figure: route depth at 2.0 s by chip timing and contact length (TE and RB) ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
SURFACE, INK, INK2, GRID, BLUE, ORANGE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#eb6834"
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), facecolor=SURFACE, sharey=True)
for ax, col, ttl in [(axes[0], "start_bin", "WHEN he makes contact"), (axes[1], "len_bin", "HOW LONG he stays on the rusher")]:
    ax.set_facecolor(SURFACE)
    g = c.groupby(["pos", col], observed=True).depth_2_0.agg(["mean", "sem", "size"]).reset_index()
    cats = list(c[col].cat.categories)
    for i, (pos, colr) in enumerate([("TE", BLUE), ("RB", ORANGE)]):
        s = g[g.pos == pos].set_index(col).reindex(cats)
        x = np.arange(len(cats)) + (i - 0.5) * 0.36
        ax.bar(x, s["mean"], width=0.34, color=colr, label=pos)
        ax.errorbar(x, s["mean"], yerr=1.96 * s["sem"], fmt="none", ecolor=INK, lw=1, capsize=3)
        for xi, v, e in zip(x, s["mean"], 1.96 * s["sem"]):
            ax.text(xi + 0.19, v / 2, f"{v:+.1f}", ha="left", va="center", fontsize=9, color=INK, fontweight="bold")
    ax.axhline(0, color=INK2, lw=1.2)
    ax.text(-0.55, 0.15, "line of scrimmage", fontsize=8.5, color=INK2)
    ax.set_xticks(range(len(cats)), cats)
    ax.set_title(ttl, loc="left", fontsize=12.5, fontweight="bold", color=INK)
    ax.grid(axis="y", color=GRID); ax.set_axisbelow(True)
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
axes[0].set_ylabel("route depth at 2.0 s after a chip (yds past LOS)", color=INK2)
axes[0].legend(frameon=False, loc="lower left")
fig.suptitle("What makes a cheap chip: hit early, get off fast", x=0.01, ha="left", fontsize=15, fontweight="bold", color=INK)
fig.text(0.01, 0.885, "Chip routes only (1,265 TE/RB chips). Bars = mean depth at 2.0 s with 95% CI. Timing = seconds from snap to first contact with the rusher (tracking).",
         fontsize=9.5, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.87))
fig.savefig(OUT / "figs" / "9_what_makes_a_cheap_chip.png", dpi=160, facecolor=SURFACE)
