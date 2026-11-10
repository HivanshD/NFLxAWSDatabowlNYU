"""When does a chip pay off? EPA effect of a chip by situation + split-half stability of the Chip Tax.
Writes outputs/chip_when.json and outputs/figs/8_when_chip_pays.png."""
import json
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#b5b3ad"


def load():
    R = pd.read_parquet(OUT / "chip_rushers.parquet")
    RT = pd.read_parquet(OUT / "chip_routes.parquet")
    for d in (R, RT):
        d.columns = [c.replace(".", "_") for c in d.columns]
    pbp = pd.read_csv(ROOT / "data" / "external" / "pbp_2021.csv.gz", low_memory=False,
                      usecols=["old_game_id", "play_id", "epa"]).rename(columns={"old_game_id": "gameId", "play_id": "playId"})
    pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv", usecols=["gameId", "playId", "pff_role"])
    cnt = pff.pivot_table(index=["gameId", "playId"], columns="pff_role", aggfunc="size", fill_value=0)
    cnt = cnt[["Pass Block", "Pass Route"]].rename(columns={"Pass Block": "n_block", "Pass Route": "n_route"})
    plays = pd.read_csv(ROOT / "data" / "plays.csv")
    return R, RT, pbp, cnt, plays


def main():
    R, RT, pbp, cnt, plays = load()
    R["pressure_i"] = R.pressure.astype(int)
    # rusher quality = his own pressure rate when NOT chipped (>= 40 reps); play tier = best rusher faced
    q = R[~R.chipped].groupby("nflId").pressure_i.agg(["mean", "size"])
    q = q[q["size"] >= 40]["mean"]
    elite_cut = q.quantile(2 / 3)
    R["elite"] = R.nflId.map(q) >= elite_cut
    chip_pos = RT[RT.chip].groupby(["gameId", "playId"]).pos.agg(lambda s: "TE" if (s == "TE").any() else "RB")
    pl = plays.set_index(["gameId", "playId"]).join(cnt, how="inner")
    pl = pl.join(R.groupby(["gameId", "playId"]).agg(chip=("chipped", "any"), t_end=("t_end", "first"),
                                                       elite_rusher=("elite", "any")), how="inner")
    pl = pl.join(RT.groupby(["gameId", "playId"]).size().rename("n_terb"), how="inner").join(chip_pos.rename("chip_pos"))
    pl = pl.reset_index().merge(pbp, on=["gameId", "playId"], how="left")
    pl["chip_i"] = pl.chip.astype(int)
    pl["ytg"] = pl.yardsToGo.clip(upper=15)
    pl["pa"] = pl.pff_playAction.fillna(0)
    pl["drop"] = pl.dropBackType.fillna("UNK")
    pl["struct"] = pl.n_block.astype(str) + "b_" + pl.n_route.astype(str) + "r"
    pl = pl.dropna(subset=["ytg", "down", "epa"])
    ctrl = "C(down) + ytg + pa + C(drop) + C(possessionTeam) + C(defensiveTeam) + C(struct) + t_end"

    def eff(d):
        m = smf.ols(f"epa ~ chip_i + {ctrl}", d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId})
        return float(m.params["chip_i"]), float(m.bse["chip_i"]), int(d.chip_i.sum())

    groups = [
        ("All chips", pl),
        ("Chip by a TE", pl[(pl.chip_i == 0) | (pl.chip_pos == "TE")]),
        ("Chip by a RB/FB", pl[(pl.chip_i == 0) | (pl.chip_pos == "RB")]),
        ("Facing an elite rusher (top third)", pl[pl.elite_rusher]),
        ("No elite rusher on the field", pl[~pl.elite_rusher]),
        ("1st & 2nd down", pl[pl.down <= 2]),
        ("3rd & 4th down", pl[pl.down >= 3]),
        ("With play action", pl[pl.pa == 1]),
        ("No play action", pl[pl.pa == 0]),
    ]
    rows = []
    for lab, d in groups:
        e, se, n = eff(d)
        rows.append(dict(group=lab, epa=e, se=se, n_chip=n))
        print(f"{lab:38s} {e:+.3f} (se {se:.3f})  chips {n}")
    res = {"epa_by_group": rows}

    # split-half stability of the per-player raw Chip Tax (odd vs even game index)
    D = RT.dropna(subset=["depth_2_0"]).copy()
    D["half"] = D.gameId.rank(method="dense").astype(int) % 2
    g = D.groupby(["nflId", "half", "chip"]).depth_2_0.agg(["mean", "size"]).unstack(["half", "chip"])
    ok = ((g["size"][0][True] >= 5) & (g["size"][1][True] >= 5) & (g["size"][0][False] >= 15) & (g["size"][1][False] >= 15))
    g = g[ok]
    t0 = g["mean"][0][True] - g["mean"][0][False]
    t1 = g["mean"][1][True] - g["mean"][1][False]
    pos = RT.drop_duplicates("nflId").set_index("nflId").pos.reindex(g.index)
    res["split_half"] = {"all": {"r": float(np.corrcoef(t0, t1)[0, 1]), "n": int(len(g))}}
    for p in ["TE", "RB"]:
        m = pos == p
        if m.sum() >= 6:
            res["split_half"][p] = {"r": float(np.corrcoef(t0[m], t1[m])[0, 1]), "n": int(m.sum())}
    print("split-half stability of Chip Tax:", res["split_half"])
    (OUT / "chip_when.json").write_text(json.dumps(res, indent=2))

    # figure: dot-and-whisker, EPA per play, one axis
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(11, 5.8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    y = np.arange(len(df))[::-1]
    for yi, r in zip(y, df.itertuples()):
        lo, hi = r.epa - 1.96 * r.se, r.epa + 1.96 * r.se
        sig = lo > 0 or hi < 0
        col = (BLUE if r.epa > 0 else ORANGE) if sig else GRAY
        ax.plot([lo, hi], [yi, yi], color=col, lw=2.2, solid_capstyle="round")
        ax.scatter(r.epa, yi, s=110, color=col if sig else SURFACE, edgecolor=col, lw=2, zorder=3)
        ax.text(max(hi, 0) + 0.02, yi, f"{r.epa:+.2f} EPA  ({r.n_chip} chips)", va="center", fontsize=9.5,
                color=INK if sig else INK2, fontweight="bold" if sig else "normal")
    ax.axvline(0, color=INK2, lw=1)
    for k in [0.5, 2.5, 4.5, 6.5]:
        ax.axhline(len(df) - 1 - k, color=GRID, lw=1)
    ax.set_yticks(y, df.group, fontsize=10.5)
    ax.set_xlim(min(-0.6, (df.epa - 2 * df.se).min() - 0.05), max(0.8, (df.epa + 2 * df.se).max() + 0.35))
    ax.set_xlabel("expected points added per play: chip plays vs plays with the same protection + hold time (95% CI)", color=INK2)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color=GRID)
    ax.set_title("When does a chip pay off? Directional only: no split is clearly different from zero", loc="left", fontsize=13.5, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "figs" / "8_when_chip_pays.png", dpi=160, facecolor=SURFACE)


if __name__ == "__main__":
    main()
