"""Chip deep dive part 2: placebo, play-level net value, where the ball goes, per-chipper and per-team."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "explore"
R = pd.read_parquet(E / "chip_rushers.parquet")
RT = pd.read_parquet(E / "chip_routes.parquet")
R.columns = [c.replace(".", "_") for c in R.columns]
RT.columns = [c.replace(".", "_") for c in RT.columns]
routes = pd.read_parquet(ROOT / "outputs" / "routes.parquet")
R["pressure_i"] = R.pressure.astype(int)

play_chip = R.groupby(["gameId", "playId"]).chipped.any().rename("chip_play")
R = R.join(play_chip, on=["gameId", "playId"])

print("=== 1. PLACEBO: unchipped rushers on chip plays vs non-chip plays (same rusher) ===")
U = R[~R.chipped].copy()
U["chip_play_i"] = U.chip_play.astype(int)
U = U[U.groupby("nflId").chip_play.transform("sum") >= 5]
m = smf.ols("pressure_i ~ chip_play_i + C(nflId) + C(down)", U).fit(cov_type="cluster", cov_kwds={"groups": U.gameId})
print(f"  other rushers' pressure on chip plays: {m.params['chip_play_i']:+.3f} (se {m.bse['chip_play_i']:.3f}); base {U.pressure_i.mean():.3f}")
Rc = R[R.groupby("nflId").chipped.transform("sum") >= 3].copy()
Rc["chip_i"] = Rc.chipped.astype(int)
Rc["chip_play_i"] = Rc.chip_play.astype(int)
m2 = smf.ols("pressure_i ~ chip_i + chip_play_i + C(nflId) + C(down)", Rc).fit(cov_type="cluster", cov_kwds={"groups": Rc.gameId})
print(f"  chipped rusher effect net of 'chip play' effect: {m2.params['chip_i']:+.3f} (se {m2.bse['chip_i']:.3f})")

print("\n=== 2. PLAY-LEVEL NET VALUE (chip plays vs chip-ELIGIBLE plays: >=1 TE/RB running a route) ===")
plays = pd.read_csv(ROOT / "data" / "plays.csv")
elig = RT.groupby(["gameId", "playId"]).size().rename("n_terb")
q = R[~R.chipped].groupby("nflId").pressure_i.agg(["mean", "size"])
q = q[q["size"] >= 40]["mean"]
cut = q.quantile([1 / 3, 2 / 3]).values
R["tier"] = pd.cut(R.nflId.map(q), [-1, cut[0], cut[1], 2], labels=["low", "mid", "elite"])
best = R.dropna(subset=["tier"]).groupby(["gameId", "playId"]).tier.max().rename("best_rusher")
pl = plays.set_index(["gameId", "playId"]).join(play_chip, how="inner").join(elig, how="inner").join(best)
tgt = routes[routes.targeted].set_index(["gameId", "playId"])[["depth_at_throw", "sep_at_throw", "pos"]]
pl = pl.join(tgt.rename(columns={"pos": "tgt_pos"}))
pl = pl.reset_index()
pl["chip_i"] = pl.chip_play.astype(int)
pl["sack"] = (pl.passResult == "S").astype(int)
pl["comp"] = (pl.passResult == "C").astype(int)
pl["ytg"] = pl.yardsToGo.clip(upper=15)
pl["pa"] = pl.pff_playAction.fillna(0)
pl["drop"] = pl.dropBackType.fillna("UNK")
print(f"  eligible plays {len(pl)}, chip plays {pl.chip_i.sum()}")
ctrl = "C(down) + ytg + pa + C(drop) + C(possessionTeam) + C(defensiveTeam) + C(personnelO) + C(best_rusher)"
d = pl.dropna(subset=["best_rusher", "personnelO", "ytg", "down"])
for y in ["playResult", "sack", "comp", "depth_at_throw"]:
    dd = d.dropna(subset=[y])
    m = smf.ols(f"{y} ~ chip_i + {ctrl}", dd).fit(cov_type="cluster", cov_kwds={"groups": dd.gameId})
    print(f"  {y:15s} chip play {m.params['chip_i']:+.3f} (se {m.bse['chip_i']:.3f}) | no-chip mean {dd[dd.chip_i == 0][y].mean():.3f}")
print("  by best rusher on the play (controlled playResult / sack):")
for t in ["low", "mid", "elite"]:
    dd = d[d.best_rusher == t]
    a = smf.ols(f"playResult ~ chip_i + C(down) + ytg + pa + C(drop) + C(possessionTeam)", dd).fit(cov_type="HC1")
    b = smf.ols(f"sack ~ chip_i + C(down) + ytg + pa + C(drop) + C(possessionTeam)", dd).fit(cov_type="HC1")
    print(f"    {t:6s} plays {len(dd):5d} chips {dd.chip_i.sum():4d} | yds {a.params['chip_i']:+.2f} (se {a.bse['chip_i']:.2f}) | sack {b.params['chip_i']:+.3f} (se {b.bse['chip_i']:.3f})")

print("\n=== 3. WHERE DOES THE BALL GO on chip plays? ===")
t = d.dropna(subset=["depth_at_throw"])
print(t.groupby("chip_play").agg(n=("comp", "size"), tgt_depth=("depth_at_throw", "mean"), comp=("comp", "mean"),
                                 deep_share=("depth_at_throw", lambda s: (s >= 15).mean()), yds=("playResult", "mean")).round(3))
print("  target position share:\n", pd.crosstab(t.chip_play, t.tgt_pos, normalize="index").round(3))

print("\n=== 4. PER-CHIPPER CHIP TAX (own chip routes vs own non-chip routes) ===")
g = RT.groupby(["name", "pos", "chip"]).agg(n=("depth_2_0", "size"), d2=("depth_2_0", "mean"), tgt=("targeted", "mean")).unstack()
g = g[(g["n"][True] >= 12) & (g["n"][False] >= 30)]
tax = pd.DataFrame({"chips": g["n"][True], "depth_tax": g["d2"][True] - g["d2"][False],
                    "tgt_tax": g["tgt"][True] - g["tgt"][False]}).reset_index()
# protection bought: chipped rusher pressure vs that rusher's own unchipped rate
qq = R[~R.chipped].groupby("nflId").pressure_i.mean()
ch = R[R.chipped].copy()
ch["exp"] = ch.nflId.map(qq)
ch = ch.merge(RT[RT.chip][["gameId", "playId", "nflId", "name"]].rename(columns={"nflId": "chipper"}), on=["gameId", "playId", "chipper"])
prot = ch.groupby("name").apply(lambda x: pd.Series(dict(prot=(x.exp - x.pressure_i).mean())))
tax = tax.merge(prot, on="name", how="left").sort_values("depth_tax", ascending=False)
print(tax.round(3).to_string(index=False))

print("\n=== 5. TEAMS: how often do they chip, and how often on bottom-third rushers? ===")
ct = R[R.chipped].merge(plays[["gameId", "playId", "possessionTeam"]], on=["gameId", "playId"])
tm = ct.groupby("possessionTeam").agg(chips=("tier", "size"), wasted=("tier", lambda s: (s == "low").mean()),
                                      elite=("tier", lambda s: (s == "elite").mean())).sort_values("chips", ascending=False)
print(tm.round(2).head(10).to_string()); print("...", tm.round(2).tail(5).to_string())
tax.to_csv(E / "chipper_tax.csv", index=False)
tm.to_csv(E / "team_chips.csv")
