"""The Chip Tax: what a chip costs the chipper, what it buys the offense, and who pays the most.

Reads outputs/chip_rushers.parquet, outputs/chip_routes.parquet (src/chip_extract.py) and
outputs/routes.parquet (src/build_routes.py). Writes outputs/chip_results.json, outputs/chip_tax_by_player.csv.

Every effect is a regression with fixed effects + play controls and game-clustered SEs:
  * COST   : same chipper, chip routes vs his own non-chip routes
  * BENEFIT: same rusher, chipped vs not chipped (alignment, pre-snap distance, hold time controlled)
  * RECEIPT: chip plays vs plays with the SAME protection structure (#blockers/#route runners) and hold time
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def load():
    R = pd.read_parquet(OUT / "chip_rushers.parquet")
    RT = pd.read_parquet(OUT / "chip_routes.parquet")
    for d in (R, RT):
        d.columns = [c.replace(".", "_") for c in d.columns]
    pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv", usecols=["gameId", "playId", "pff_role"])
    cnt = pff.pivot_table(index=["gameId", "playId"], columns="pff_role", aggfunc="size", fill_value=0)
    cnt = cnt[["Pass Block", "Pass Route"]].rename(columns={"Pass Block": "n_block", "Pass Route": "n_route"})
    return R, RT, cnt


def eff(formula, d, term, cluster=True):
    m = smf.ols(formula, d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId}) if cluster else smf.ols(formula, d).fit(cov_type="HC1")
    return {"est": float(m.params[term]), "se": float(m.bse[term]), "n": int(m.nobs)}


def cost(RT):
    RT = RT.copy()
    RT["chip_i"] = RT.chip.astype(int)
    RT["targeted"] = RT.targeted.fillna(False).astype(int)
    RT["ytg"] = RT.yardsToGo.clip(upper=15)
    RT["pa"] = RT.pff_playAction.fillna(0)
    for c in ["dropBackType", "pff_passCoverageType", "aligned"]:
        RT[c] = RT[c].fillna("UNK")
    D = RT[RT.groupby("nflId").chip.transform("sum") >= 3]
    ctrl = "C(down) + ytg + pa + C(dropBackType) + C(pff_passCoverageType) + C(aligned) + t_end + C(nflId)"
    res = {}
    for y in ["t_release", "depth_1_5", "depth_2_0", "depth_2_5", "depth_end", "targeted", "sep_end"]:
        d = D.dropna(subset=[y, "t_end", "down", "ytg"])
        res[y] = eff(f"{y} ~ chip_i + {ctrl}", d, "chip_i")
    res["target_rate_nochip"] = float(D[~D.chip].targeted.mean())
    return res


def benefit(R):
    R = R.copy()
    R["pressure_i"] = R.pressure.astype(int)
    R["chip_i"] = R.chipped.astype(int)
    R["al"] = R.aligned.fillna("UNK")
    Rc = R[R.groupby("nflId").chipped.transform("sum") >= 3].dropna(subset=["dq0", "t_end"])
    res = {
        "placebo_presnap_dist": eff("dq0 ~ chip_i + C(nflId) + C(al)", Rc, "chip_i"),
        "pressure": eff("pressure_i ~ chip_i + C(nflId) + C(down) + C(al) + dq0 + t_end + n_block + n_route", Rc, "chip_i"),
        "pressure_rate_unchipped": float(Rc[Rc.chip_i == 0].pressure_i.mean()),
    }
    for y in ["dq_2_0", "dq_2_5"]:
        d = Rc.dropna(subset=[y])
        res[y] = eff(f"{y} ~ chip_i + C(nflId) + C(down) + C(al) + dq0", d, "chip_i")
    home = Rc.dropna(subset=["t_home"])
    res["t_home_median"] = {"chipped": float(home[home.chipped].t_home.median()), "not": float(home[~home.chipped].t_home.median())}
    # placebo: do OTHER (unchipped) rushers on chip plays change, once hold time is controlled?
    R["chip_play_i"] = R.groupby(["gameId", "playId"]).chipped.transform("any").astype(int)
    U = R[~R.chipped]
    U = U[U.groupby("nflId").chip_play_i.transform("sum") >= 5].dropna(subset=["t_end"])
    res["other_rushers_raw"] = eff("pressure_i ~ chip_play_i + C(nflId) + C(down)", U, "chip_play_i")
    res["other_rushers_ctrl"] = eff("pressure_i ~ chip_play_i + C(nflId) + C(down) + t_end + n_block + n_route + C(al)", U, "chip_play_i")
    return res


def receipt(R, RT, cnt):
    plays = pd.read_csv(ROOT / "data" / "plays.csv")
    routes = pd.read_parquet(OUT / "routes.parquet")
    pl = plays.set_index(["gameId", "playId"]).join(cnt, how="inner")
    pl = pl.join(R.groupby(["gameId", "playId"]).agg(chip=("chipped", "any"), t_end=("t_end", "first")), how="inner")
    pl = pl.join(RT.groupby(["gameId", "playId"]).size().rename("n_terb"), how="inner")  # chip-eligible plays only
    pl = pl.join(routes[routes.targeted].set_index(["gameId", "playId"]).depth_at_throw).reset_index()
    pl["chip_i"] = pl.chip.astype(int)
    pl["sack"] = (pl.passResult == "S").astype(int)
    pl["deep"] = (pl.depth_at_throw >= 15).astype(float)
    pl["ytg"] = pl.yardsToGo.clip(upper=15)
    pl["pa"] = pl.pff_playAction.fillna(0)
    pl["drop"] = pl.dropBackType.fillna("UNK")
    pl["struct"] = pl.n_block.astype(str) + "b_" + pl.n_route.astype(str) + "r"
    pl = pl.dropna(subset=["ytg", "down"])
    ctrl = "C(down) + ytg + pa + C(drop) + C(possessionTeam) + C(defensiveTeam) + C(struct) + t_end"
    res = {}
    for y in ["sack", "depth_at_throw", "deep", "playResult"]:
        d = pl.dropna(subset=[y])
        res[y] = eff(f"{y} ~ chip_i + {ctrl}", d, "chip_i")
        res[y]["base"] = float(d[d.chip_i == 0][y].mean())
    res["hold_time"] = {"chip": float(pl[pl.chip].t_end.mean()), "no_chip": float(pl[~pl.chip].t_end.mean())}
    res["five_out_share_chip_plays"] = float((pl[pl.chip].n_route >= 5).mean())
    res["n_plays"], res["n_chip_plays"] = int(len(pl)), int(pl.chip_i.sum())
    deep_raw = pl.dropna(subset=["depth_at_throw"]).groupby("chip").deep.mean()
    res["deep_share_raw"] = {"chip": float(deep_raw[True]), "no_chip": float(deep_raw[False])}
    return res


def per_player(RT, R):
    g = RT.groupby(["nflId", "name", "pos", "chip"]).agg(
        n=("depth_2_0", "size"), d2=("depth_2_0", "mean"), sd=("depth_2_0", "std"),
        tgt=("targeted", lambda s: s.fillna(False).mean())).unstack()
    g = g[(g["n"][True] >= 12) & (g["n"][False] >= 30)]
    tab = pd.DataFrame({"chips": g["n"][True].astype(int), "routes_no_chip": g["n"][False].astype(int),
                        "depth_2s_no_chip": g["d2"][False], "depth_2s_chip": g["d2"][True],
                        "depth_tax_yds": g["d2"][True] - g["d2"][False],
                        "depth_tax_se": np.sqrt(g["sd"][True] ** 2 / g["n"][True] + g["sd"][False] ** 2 / g["n"][False]),
                        "target_rate_no_chip": g["tgt"][False], "target_rate_chip": g["tgt"][True]}).reset_index()
    # Empirical-Bayes shrinkage within position: pull small samples toward the position mean
    # by how much true player-to-player spread (tau^2) exists beyond sampling noise (se^2).
    out = []
    for pos, s in tab.groupby("pos"):
        s = s.copy()
        w = 1 / s.depth_tax_se ** 2
        m = (w * s.depth_tax_yds).sum() / w.sum()
        q = (w * (s.depth_tax_yds - m) ** 2).sum()
        df = len(s) - 1
        tau2 = max(0.0, (q - df) / (w.sum() - (w ** 2).sum() / w.sum())) if df > 0 else 0.0
        k = tau2 / (tau2 + s.depth_tax_se ** 2)
        s["chip_tax"] = m + k * (s.depth_tax_yds - m)
        s["chip_tax_sd"] = np.sqrt(tau2 * s.depth_tax_se ** 2 / (tau2 + s.depth_tax_se ** 2)) if tau2 > 0 else s.depth_tax_se
        s["pos_mean"] = m
        z = (s.chip_tax - m) / s.chip_tax_sd.replace(0, np.nan)
        s["verdict"] = np.where(z > 1.28, "pays less than his position", np.where(z < -1.28, "pays more than his position", "about average"))
        out.append(s)
    return pd.concat(out).sort_values("chip_tax")


def main():
    R, RT, cnt = load()
    R = R.join(cnt, on=["gameId", "playId"])
    res = {"cost": cost(RT), "benefit": benefit(R), "receipt": receipt(R, RT, cnt),
           "n_chips": int(RT.chip.sum()), "n_chipped_rusher_reps": int(R.chipped.sum())}
    tab = per_player(RT, R)
    res["tax_by_pos_median"] = tab.groupby("pos").depth_tax_yds.median().round(2).to_dict()
    tab.to_csv(OUT / "chip_tax_by_player.csv", index=False)
    (OUT / "chip_results.json").write_text(json.dumps(res, indent=2))

    c, b, rc = res["cost"], res["benefit"], res["receipt"]
    f = lambda e, k=1: f"{e['est'] * k:+.2f} (se {e['se'] * k:.2f})"
    print(f"COST (same chipper): release {f(c['t_release'])}s | depth@2s {f(c['depth_2_0'])} yds | depth@throw {f(c['depth_end'])} | "
          f"targeted {f(c['targeted'], 100)} pts (from {c['target_rate_nochip']:.1%}) | open-ness@throw {f(c['sep_end'])} yds")
    print(f"BENEFIT (same rusher): pressure {f(b['pressure'], 100)} pts (from {b['pressure_rate_unchipped']:.1%}) | "
          f"dist to QB @2s {f(b['dq_2_0'])} yds | t_home {b['t_home_median']} | placebo pre-snap dist {f(b['placebo_presnap_dist'])}")
    print(f"  other rushers on chip plays: raw {f(b['other_rushers_raw'], 100)} -> controlled {f(b['other_rushers_ctrl'], 100)} pts")
    print(f"RECEIPT (same structure + hold time): sack {f(rc['sack'], 100)} pts | target depth {f(rc['depth_at_throw'])} | "
          f"15+yd targets {f(rc['deep'], 100)} pts | yds/play {f(rc['playResult'])} | hold {rc['hold_time']} | 5-out {rc['five_out_share_chip_plays']:.0%}")
    print("tax by position (median yds):", res["tax_by_pos_median"])


if __name__ == "__main__":
    main()
