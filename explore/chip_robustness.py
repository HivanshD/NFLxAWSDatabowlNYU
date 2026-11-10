"""Placebo + confound checks for every chip finding."""
from pathlib import Path
import warnings
import numpy as np, pandas as pd, statsmodels.formula.api as smf
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; E = ROOT / "explore"
R = pd.read_parquet(E / "chip_rushers.parquet"); RT = pd.read_parquet(E / "chip_routes.parquet")
R.columns = [c.replace(".", "_") for c in R.columns]; RT.columns = [c.replace(".", "_") for c in RT.columns]
pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv", usecols=["gameId", "playId", "pff_role"])
cnt = pff.pivot_table(index=["gameId", "playId"], columns="pff_role", aggfunc="size", fill_value=0)
cnt = cnt[["Pass Block", "Pass Route", "Pass Rush"]].rename(columns=lambda c: "n_" + c.split()[-1].lower())
R = R.join(cnt, on=["gameId", "playId"])
R["pressure_i"] = R.pressure.astype(int); R["chip_i"] = R.chipped.astype(int)
R["chip_play_i"] = R.groupby(["gameId", "playId"]).chipped.transform("any").astype(int)
R["al"] = R.aligned.fillna("UNK")
def fit(f, d):
    d = d.dropna(subset=[c for c in ["t_end", "dq0", "al"] if c in f] + ["pressure_i"])
    return smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId})
Rc = R[R.groupby("nflId").chipped.transform("sum") >= 3]
print("=== A. Chipped rusher: placebo + controls (same rusher) ===")
m = fit("dq0 ~ chip_i + C(nflId)", Rc); print(f"  PLACEBO pre-snap distance to QB: chipped {m.params['chip_i']:+.2f} yds (se {m.bse['chip_i']:.2f})")
m = fit("dq0 ~ chip_i + C(nflId) + C(al)", Rc); print(f"  ...same, with alignment control: {m.params['chip_i']:+.2f} (se {m.bse['chip_i']:.2f})")
for f, lab in [("pressure_i ~ chip_i + C(nflId) + C(down)", "base"),
               ("pressure_i ~ chip_i + C(nflId) + C(down) + C(al) + dq0", "+alignment +pre-snap distance"),
               ("pressure_i ~ chip_i + C(nflId) + C(down) + C(al) + dq0 + t_end", "+time to throw"),
               ("pressure_i ~ chip_i + C(nflId) + C(down) + C(al) + dq0 + t_end + n_block + n_route", "+protection size")]:
    m = fit(f, Rc); print(f"  pressure {lab:35s}: {m.params['chip_i']:+.3f} (se {m.bse['chip_i']:.3f})")
print("\n=== B. 'Pressure relocates' to other rushers: real or just longer plays? ===")
U = R[~R.chipped]; U = U[U.groupby("nflId").chip_play_i.transform("sum") >= 5]
for f, lab in [("pressure_i ~ chip_play_i + C(nflId) + C(down)", "base"),
               ("pressure_i ~ chip_play_i + C(nflId) + C(down) + t_end", "+time to throw"),
               ("pressure_i ~ chip_play_i + C(nflId) + C(down) + t_end + n_block + n_route + C(al)", "+protection size, alignment")]:
    m = fit(f, U); print(f"  other rushers {lab:30s}: {m.params['chip_play_i']:+.3f} (se {m.bse['chip_play_i']:.3f})")
print("\n=== C. Play level: sacks / depth / yards, vs plays with the SAME protection structure ===")
plays = pd.read_csv(ROOT / "data" / "plays.csv")
routes = pd.read_parquet(ROOT / "outputs" / "routes.parquet")
pl = plays.set_index(["gameId", "playId"]).join(cnt, how="inner")
pl = pl.join(R.groupby(["gameId", "playId"]).agg(chip=("chipped", "any"), t_end=("t_end", "first"), pr=("pressure_i", "max")), how="inner")
pl = pl.join(RT.groupby(["gameId", "playId"]).size().rename("n_terb"), how="inner")
pl = pl.join(routes[routes.targeted].set_index(["gameId", "playId"]).depth_at_throw).reset_index()
pl["chip_i"] = pl.chip.astype(int); pl["sack"] = (pl.passResult == "S").astype(int)
pl["deep"] = (pl.depth_at_throw >= 15).astype(float); pl["ytg"] = pl.yardsToGo.clip(upper=15)
pl["pa"] = pl.pff_playAction.fillna(0); pl["drop"] = pl.dropBackType.fillna("UNK")
pl["struct"] = pl.n_block.astype(str) + "b_" + pl.n_route.astype(str) + "r"
pl = pl.dropna(subset=["ytg", "down"])
base = "C(down) + ytg + pa + C(drop) + C(possessionTeam) + C(defensiveTeam)"
for y in ["pr", "sack", "depth_at_throw", "deep", "playResult"]:
    for extra, lab in [("", "context only"), ("+ C(struct)", "+same #blockers/#routes"), ("+ C(struct) + t_end", "+same structure +time to throw")]:
        d = pl.dropna(subset=[y])
        m = smf.ols(f"{y} ~ chip_i + {base} {extra}", d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId})
        print(f"  {y:15s} {lab:32s}: {m.params['chip_i']:+.3f} (se {m.bse['chip_i']:.3f})")
print("  chip plays by structure (top):", pl[pl.chip].struct.value_counts(normalize=True).head(4).round(2).to_dict())
print("  non-chip by structure (top):", pl[~pl.chip].struct.value_counts(normalize=True).head(4).round(2).to_dict())
print("  time to throw: chip", pl[pl.chip].t_end.mean().round(2), "vs", pl[~pl.chip].t_end.mean().round(2))
