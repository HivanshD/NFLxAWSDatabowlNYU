"""Chip deep dive: 7 questions, with controls."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

warnings.filterwarnings("ignore")
E = Path(__file__).resolve().parent
R = pd.read_parquet(E / "chip_rushers.parquet")
RT = pd.read_parquet(E / "chip_routes.parquet")
R.columns = [c.replace(".", "_") for c in R.columns]
RT.columns = [c.replace(".", "_") for c in RT.columns]
RT["targeted"] = RT.targeted.fillna(False).astype(int)
RT["chip_i"] = RT.chip.astype(int)
RT["ytg"] = RT.yardsToGo.clip(upper=15)
RT["pa"] = RT.pff_playAction.fillna(0)
RT["drop"] = RT.dropBackType.fillna("UNK")
RT["cov"] = RT.pff_passCoverageType.fillna("Other")
RT["al"] = RT.aligned.fillna("UNK")
CTRL = "C(down) + ytg + pa + C(drop) + C(cov) + C(al) + t_end"


def fe(y, df, extra=""):
    """OLS with player fixed effects + play controls, SEs clustered by game."""
    d = df.dropna(subset=[y, "t_end"]).copy()
    m = smf.ols(f"{y} ~ chip_i + {CTRL} + C(nflId){extra}", d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId})
    return m.params["chip_i"], m.bse["chip_i"], len(d)


print("=== Q1. Is the route cost real? (same player, chip vs no chip, + play controls) ===")
multi = RT.groupby("nflId").chip.transform("sum") >= 3
D = RT[multi]
for y in ["depth_1_5", "depth_2_0", "depth_2_5", "depth_end", "t_release", "targeted", "sep_end"]:
    b, se, n = fe(y, D)
    raw = D[D.chip][y].mean() - D[~D.chip][y].mean()
    print(f"  {y:10s} raw diff {raw:+.2f} | controlled within-player {b:+.2f} (se {se:.2f}, n={n})")
T = D[(D.targeted == 1) & D.passResult.isin(["C", "I", "IN"])].copy()
T["comp"] = (T.passResult == "C").astype(int)
for y in ["comp", "playResult"]:
    m = smf.ols(f"{y} ~ chip_i + {CTRL} + depth_end", T.dropna(subset=["t_end", "depth_end"])).fit(cov_type="HC1")
    print(f"  targets only: {y} chip effect {m.params['chip_i']:+.3f} (se {m.bse['chip_i']:.3f}), n={len(T)}; "
          f"raw chip={T[T.chip][y].mean():.3f} vs no-chip={T[~T.chip][y].mean():.3f}")

print("\n=== Q2. What does a chip buy? (same rusher, chipped vs not) ===")
R["home25"] = (R.t_home <= 2.5).astype(float)
R["home30"] = (R.t_home <= 3.0).astype(float)
R["chip_i"] = R.chipped.astype(int)
R["pressure_i"] = R.pressure.astype(int)
R["sack_i"] = R.sack.astype(int)
Rm = R[R.groupby("nflId").chipped.transform("sum") >= 3]
for y in ["pressure_i", "sack_i", "home25", "dq_2_0", "dq_2_5", "min_dq"]:
    d = Rm.dropna(subset=[y])
    m = smf.ols(f"{y} ~ chip_i + C(nflId) + C(down) + t_end", d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId})
    print(f"  {y:10s} chipped {m.params['chip_i']:+.3f} (se {m.bse['chip_i']:.3f}) | unchipped mean {d[d.chip_i == 0][y].mean():.3f}")
d = Rm.dropna(subset=["t_home"])
print(f"  when they DO get home: t_home chipped {d[d.chipped].t_home.median():.2f}s vs {d[~d.chipped].t_home.median():.2f}s")
print("  rusher speed into the chip -> just after:", R[R.chipped].rush_s_pre.mean().round(2), "->", R[R.chipped].rush_s_post.mean().round(2))

print("\n=== Q3. Does chip LENGTH matter? ===")
ch = R[R.chipped].dropna(subset=["chip_frames"]).merge(
    RT[RT.chip][["gameId", "playId", "nflId", "depth_2_5", "targeted", "pos", "chip_start"]].rename(columns={"nflId": "chipper"}),
    on=["gameId", "playId", "chipper"], how="left")
ch["len_bin"] = pd.cut(ch.chip_frames, [0, 0.3, 0.6, 10], labels=["touch (<=0.3s)", "medium (0.4-0.6s)", "long (>0.6s)"])
base = R[~R.chipped].groupby("aligned").pressure_i.mean()
ch["exp_press"] = ch.aligned.map(base)
print(ch.groupby("len_bin", observed=True).agg(n=("pressure", "size"), pressure=("pressure", "mean"), exp_unchipped=("exp_press", "mean"),
      dq25=("dq_2_5", "mean"), chipper_depth25=("depth_2_5", "mean"), chipper_tgt=("targeted", "mean")).round(3))
print("  chip start timing:", ch.chip_start_x.describe()[["25%", "50%", "75%"]].round(2).to_dict())

print("\n=== Q4. TE vs RB as the chipper ===")
print(ch.groupby("pos").agg(n=("pressure", "size"), pressure=("pressure", "mean"), exp=("exp_press", "mean"),
                            chip_len=("chip_frames", "median"), depth25=("depth_2_5", "mean"), tgt=("targeted", "mean")).round(3))
nc = RT[~RT.chip].groupby("pos").agg(depth25=("depth_2_5", "mean"), tgt=("targeted", "mean")).round(3)
print("  same positions, no chip:\n", nc)

print("\n=== Q5. Which rushers are worth chipping? ===")
q = R[~R.chipped].groupby("nflId").agg(n=("pressure_i", "size"), q=("pressure_i", "mean"))
q = q[q.n >= 40]
Rq = R.merge(q.q.rename("rq"), left_on="nflId", right_index=True)
Rq["tier"] = pd.qcut(Rq.rq, 3, labels=["low", "mid", "elite"])
print(Rq.groupby(["tier", "chipped"], observed=True).pressure_i.agg(["mean", "size"]).unstack().round(3))
print("  chip share by tier:", Rq.groupby("tier", observed=True).chipped.mean().round(3).to_dict())

print("\n=== Q6. Why do chip routes catch so often? ===")
print(RT.groupby("chip").agg(sep_end=("sep_end", "mean"), depth_end=("depth_end", "mean"), t_end=("t_end", "mean")).round(2))
tt = RT[(RT.targeted == 1) & RT.passResult.isin(["C", "I", "IN"])]
print(tt.groupby("chip").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                             ypt=("playResult", "mean"), depth_at_throw=("depth_end", "mean"), sep=("sep_end", "mean")).round(2))

print("\n=== Q7. Net value in yards ===")
pl = R.groupby(["gameId", "playId"]).agg(press=("pressure_i", "max"), yds=("playResult", "first"), pr=("passResult", "first"))
v = pl.groupby("press").yds.mean()
print(f"  play value pressured {v[1]:.2f} vs clean {v[0]:.2f} -> a pressure costs ~{v[0]-v[1]:.2f} yds")
