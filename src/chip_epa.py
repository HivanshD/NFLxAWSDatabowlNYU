"""Enhancements with public nflverse play-by-play (EPA, YAC) + a context-adjusted Chip Tax check.
Needs data/external/pbp_2021.csv.gz from
https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2021.csv.gz
Writes outputs/chip_results_epa.json."""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def eff(f, d, term="chip_i", cluster=True):
    m = smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": d.gameId}) if cluster else smf.ols(f, d).fit(cov_type="HC1")
    return {"est": float(m.params[term]), "se": float(m.bse[term]), "n": int(m.nobs)}


def main():
    pbp = pd.read_csv(ROOT / "data" / "external" / "pbp_2021.csv.gz", low_memory=False,
                      usecols=["old_game_id", "play_id", "epa", "yards_after_catch", "air_yards", "complete_pass", "success"])
    pbp = pbp.rename(columns={"old_game_id": "gameId", "play_id": "playId"})
    R = pd.read_parquet(OUT / "chip_rushers.parquet")
    RT = pd.read_parquet(OUT / "chip_routes.parquet")
    for d in (R, RT):
        d.columns = [c.replace(".", "_") for c in d.columns]
    routes = pd.read_parquet(OUT / "routes.parquet")
    pff = pd.read_csv(ROOT / "data" / "pffScoutingData.csv", usecols=["gameId", "playId", "pff_role"])
    cnt = pff.pivot_table(index=["gameId", "playId"], columns="pff_role", aggfunc="size", fill_value=0)
    cnt = cnt[["Pass Block", "Pass Route"]].rename(columns={"Pass Block": "n_block", "Pass Route": "n_route"})
    plays = pd.read_csv(ROOT / "data" / "plays.csv")
    res = {}

    # 1. EPA per play: chip plays vs same protection structure + hold time
    pl = plays.set_index(["gameId", "playId"]).join(cnt, how="inner")
    pl = pl.join(R.groupby(["gameId", "playId"]).agg(chip=("chipped", "any"), t_end=("t_end", "first")), how="inner")
    pl = pl.join(RT.groupby(["gameId", "playId"]).size().rename("n_terb"), how="inner").reset_index()
    pl = pl.merge(pbp, on=["gameId", "playId"], how="left")
    pl["chip_i"] = pl.chip.astype(int)
    pl["ytg"] = pl.yardsToGo.clip(upper=15)
    pl["pa"] = pl.pff_playAction.fillna(0)
    pl["drop"] = pl.dropBackType.fillna("UNK")
    pl["struct"] = pl.n_block.astype(str) + "b_" + pl.n_route.astype(str) + "r"
    pl = pl.dropna(subset=["ytg", "down", "epa"])
    ctrl = "C(down) + ytg + pa + C(drop) + C(possessionTeam) + C(defensiveTeam) + C(struct) + t_end"
    res["epa_per_play"] = eff(f"epa ~ chip_i + {ctrl}", pl)
    res["epa_per_play"]["base"] = float(pl[pl.chip_i == 0].epa.mean())
    pl["success"] = pl.success.astype(float)
    res["success_rate"] = eff(f"success ~ chip_i + {ctrl}", pl)
    res["success_rate"]["base"] = float(pl[pl.chip_i == 0].success.mean())

    # 2. YAC + EPA on catches by the chipper vs the same player's non-chip catches
    T = RT[RT.targeted.fillna(False)].merge(pbp, on=["gameId", "playId"], how="left")
    T["chip_i"] = T.chip.astype(int)
    CC = T[T.complete_pass == 1].dropna(subset=["yards_after_catch"])
    res["yac_raw"] = {"chip": float(CC[CC.chip].yards_after_catch.mean()), "no_chip": float(CC[~CC.chip].yards_after_catch.mean()),
                      "n_chip": int(CC.chip.sum())}
    res["yac_ctrl_depth"] = eff("yards_after_catch ~ chip_i + air_yards + C(pos)", CC.dropna(subset=["air_yards"]), cluster=False)
    res["epa_per_target_raw"] = {"chip": float(T[T.chip].epa.mean()), "no_chip": float(T[~T.chip].epa.mean()), "n_chip": int(T.chip.sum())}
    res["air_yards_raw"] = {"chip": float(T[T.chip].air_yards.mean()), "no_chip": float(T[~T.chip].air_yards.mean())}

    # 3. Context-adjusted Chip Tax: residualize depth at 2.0s on context, then chip-minus-nonchip per player
    D = RT.dropna(subset=["depth_2_0"]).merge(plays[["gameId", "playId"]], on=["gameId", "playId"])
    D["ytg"] = D.yardsToGo.clip(upper=15)
    for c in ["pff_passCoverageType", "dropBackType", "aligned"]:
        D[c] = D[c].fillna("UNK")
    D["pa"] = D.pff_playAction.fillna(0)
    D = D.dropna(subset=["down", "ytg"])
    m = smf.ols("depth_2_0 ~ C(aligned) + C(down) + ytg + pa + C(dropBackType) + C(pff_passCoverageType) + C(pos)", D).fit()
    D["resid"] = D.depth_2_0 - m.predict(D)
    g = D.groupby(["name", "chip"]).resid.agg(["mean", "size"]).unstack()
    g = g[(g["size"][True] >= 12) & (g["size"][False] >= 30)]
    adj = (g["mean"][True] - g["mean"][False]).rename("tax_ctx")
    tab = pd.read_csv(OUT / "chip_tax_by_player.csv").set_index("name").join(adj, how="inner")
    res["ctx_rank_corr"] = {p: float(tab[tab.pos == p][["depth_tax_yds", "tax_ctx"]].corr(method="spearman").iloc[0, 1])
                            for p in ["TE", "RB"]}
    res["ctx_rank_corr_all"] = float(tab[["depth_tax_yds", "tax_ctx"]].corr(method="spearman").iloc[0, 1])

    (OUT / "chip_results_epa.json").write_text(json.dumps(res, indent=2))
    e, s = res["epa_per_play"], res["success_rate"]
    print(f"EPA/play chip effect {e['est']:+.3f} (se {e['se']:.3f}) from {e['base']:+.3f} | success rate {s['est'] * 100:+.1f} pts (se {s['se'] * 100:.1f}) from {s['base']:.1%}")
    print(f"YAC on catches: chip {res['yac_raw']['chip']:.1f} vs {res['yac_raw']['no_chip']:.1f} (n chip {res['yac_raw']['n_chip']}) | "
          f"controlled for air yards: {res['yac_ctrl_depth']['est']:+.2f} (se {res['yac_ctrl_depth']['se']:.2f})")
    print(f"EPA per target: chip {res['epa_per_target_raw']['chip']:+.2f} vs {res['epa_per_target_raw']['no_chip']:+.2f} | air yards {res['air_yards_raw']}")
    print(f"context-adjusted Chip Tax rank corr: {res['ctx_rank_corr']} all {res['ctx_rank_corr_all']:.2f}")


if __name__ == "__main__":
    main()
