"""Team-level view of the Chip Tax: who chips, with whom, and what it costs.

Inputs : outputs/chip_routes.parquet, outputs/chip_tax_by_player.csv, data/plays.csv
Outputs: outputs/chip_teams.csv, outputs/figs/7_team_chipping.png
Team-season = 2021 Weeks 1-8.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIG = OUT / "figs"
FIG.mkdir(parents=True, exist_ok=True)

POS_DEFAULT = {"TE": -4.65, "RB": -1.73, "FB": -1.73}
BG, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
TE_C, RB_C = "#2a78d6", "#eb6834"

# ---------------- data ----------------
routes = pd.read_parquet(OUT / "chip_routes.parquet")
routes.columns = [c.replace(".", "_") for c in routes.columns]
tax = pd.read_csv(OUT / "chip_tax_by_player.csv")[["nflId", "chip_tax"]]
plays = pd.read_csv(ROOT / "data" / "plays.csv", usecols=["gameId", "playId", "possessionTeam"])

team_plays = plays.groupby("possessionTeam").agg(
    pass_plays=("playId", "size"), games=("gameId", "nunique"))

chips = routes[routes["chip"]].merge(tax, on="nflId", how="left")
chips["tax_used"] = chips["chip_tax"].fillna(chips["pos"].map(POS_DEFAULT))
chips["grp"] = chips["pos"].map({"TE": "TE", "RB": "RB/FB", "FB": "RB/FB"})

agg = chips.groupby("possessionTeam").agg(
    chips=("nflId", "size"),
    te_chips=("grp", lambda s: (s == "TE").sum()),
    rbfb_chips=("grp", lambda s: (s == "RB/FB").sum()),
    tax_per_chip=("tax_used", "mean"),
    has_player_est=("chip_tax", lambda s: s.notna().mean()),
)
df = team_plays.join(agg, how="left").fillna({"chips": 0, "te_chips": 0, "rbfb_chips": 0})
df["chips_per100"] = 100 * df["chips"] / df["pass_plays"]
df["te_per100"] = 100 * df["te_chips"] / df["pass_plays"]
df["rbfb_per100"] = 100 * df["rbfb_chips"] / df["pass_plays"]
df["te_share"] = df["te_chips"] / df["chips"]
df["route_yds_per_game"] = df["chips"] * df["tax_per_chip"].abs() / df["games"]
df = df.sort_values("chips_per100", ascending=False)
df.round(4).to_csv(OUT / "chip_teams.csv", index_label="team")

# ---------------- headline check ----------------
te_heavy = df[df["te_share"] >= df["te_share"].median()]
rb_heavy = df[df["te_share"] < df["te_share"].median()]
print(df[["pass_plays", "chips", "chips_per100", "te_share", "tax_per_chip",
          "route_yds_per_game"]].round(2).to_string())
print(f"\nTE-heavy half tax/chip: {te_heavy.tax_per_chip.mean():.2f}  "
      f"RB-heavy half: {rb_heavy.tax_per_chip.mean():.2f}")
print("corr(te_share, tax_per_chip):", round(df.te_share.corr(df.tax_per_chip), 3))
print("League TE chip tax / RB chip tax:",
      round(chips.loc[chips.grp == "TE", "tax_used"].mean(), 2),
      round(chips.loc[chips.grp == "RB/FB", "tax_used"].mean(), 2))

# ---------------- chart ----------------
d = df.iloc[::-1]  # highest chip rate at top
expensive = set(df.nsmallest(3, "tax_per_chip").index)
cheap = set(df.nlargest(3, "tax_per_chip").index)

plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": INK})
fig, ax = plt.subplots(figsize=(11, 11), dpi=160)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

y = range(len(d))
ax.barh(y, d["te_per100"], color=TE_C, height=0.72, label="TE chips", edgecolor=BG, linewidth=0.6)
ax.barh(y, d["rbfb_per100"], left=d["te_per100"], color=RB_C, height=0.72,
        label="RB / FB chips", edgecolor=BG, linewidth=0.6)

ax.set_yticks(list(y))
ax.set_yticklabels(d.index, fontsize=10)
for lab, team in zip(ax.get_yticklabels(), d.index):
    if team in expensive or team in cheap:
        lab.set_fontweight("bold")

xmax = d["chips_per100"].max()
ax.set_xlim(0, xmax * 1.02)
ax.xaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(axis="y", length=0)
ax.tick_params(axis="x", labelsize=9)
ax.set_xlabel("Chips per 100 pass plays", fontsize=10)
ax.set_ylim(-0.6, len(d) - 0.4)

# tax-per-chip text column in the right margin (axes-fraction x, data y)
trans = ax.get_yaxis_transform()
col_x = 1.10
ax.text(col_x, len(d) - 0.1, "Tax per chip\n(route yds)", transform=trans, ha="center",
        va="bottom", fontsize=9, color=MUTED, fontweight="bold")
for yi, (team, r) in zip(y, d.iterrows()):
    hl = team in expensive or team in cheap
    tag = "  most costly" if team in expensive else ("  cheapest" if team in cheap else "")
    ax.text(col_x, yi, f"{r.tax_per_chip:+.1f}", transform=trans, ha="center", va="center",
            fontsize=9.5, color=INK if hl else MUTED, fontweight="bold" if hl else "normal")
    if tag:
        ax.text(col_x + 0.04, yi, tag, transform=trans, ha="left", va="center",
                fontsize=8, color=MUTED, style="italic")
    # chip count at bar end
    ax.text(r.chips_per100 + xmax * 0.008, yi, f"{int(r.chips)}", va="center", ha="left",
            fontsize=7.5, color=MUTED)

ax.legend(loc="lower right", frameon=False, fontsize=9.5, ncol=1)

fig.text(0.02, 0.975, TITLE := "Who chips, and with whom? A TE chip costs ~2.7x an RB chip,\nso teams that chip with tight ends pay the steepest route tax",
         fontsize=14, fontweight="bold", ha="left", va="top", color=INK)
fig.text(0.02, 0.925,
         "Bars: chips per 100 pass plays by offense, split by who chipped (blue = TE, orange = RB/FB); "
         "small number = total chips.\n"
         "Right column: team tax per chip = mean Chip Tax (route depth lost at 2.0 s, yds) of the players "
         "who chipped; bold = 3 costliest and 3 cheapest.\n"
         "2021 NFL Weeks 1-8. Chippers without a player estimate get their position average (TE -4.65, RB/FB -1.73).",
         fontsize=9, ha="left", va="top", color=MUTED, linespacing=1.45)
fig.subplots_adjust(left=0.07, right=0.80, top=0.84, bottom=0.06)
fig.savefig(FIG / "7_team_chipping.png", facecolor=BG)
print("saved", FIG / "7_team_chipping.png")
