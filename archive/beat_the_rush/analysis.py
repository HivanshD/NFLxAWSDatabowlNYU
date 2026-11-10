"""Beat the Rush: turn 'open?' and 'pressured?' into one continuous race, credit
receivers for winning it, and surface the man/zone tell a coordinator can use.

Reads outputs/routes.parquet + outputs/sep_curves.parquet (from build_routes.py)
Writes outputs/receivers.csv, outputs/sacks.csv and figures in outputs/figs/.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
KEY = ["gameId", "playId", "nflId"]

WIN_SEP = 2.5    # yards from nearest coverage defender
WIN_GAIN = 1.0   # ...and gained >= 1 yd on the tightest point of the rep (earned, not cushion)
WIN_TIGHT = 4.0  # ...after a defender had actually been on him (within 4 yds)
MIN_ROUTES = 100


def add_wins(routes: pd.DataFrame, curves: pd.DataFrame) -> pd.DataFrame:
    c = curves.sort_values(KEY + ["t"]).copy()
    c["runmin"] = c.groupby(KEY).sep.cummin()
    c["win"] = ((c.sep >= WIN_SEP) & (c.sep - c.runmin >= WIN_GAIN) & (c.runmin <= WIN_TIGHT)
                & (c.depth >= 0))
    t_win = c[c.win].groupby(KEY).t.min().rename("t_win")
    sep_snap = c[c.t == 0].set_index(KEY).sep.rename("sep_snap")
    r = routes.join(t_win, on=KEY).join(sep_snap, on=KEY)
    r = r[r.pos.isin(["WR", "TE", "RB"])].copy()
    # The QB's clock: rush arrival if pressured, otherwise when he let it go
    r["clock"] = r.t_pressure.fillna(r.t_end)
    r["pressured"] = r.t_pressure.notna()
    r["beat"] = r.t_win <= r.clock
    # Continuous race margin (s): + = open with time to spare, NaN = never won
    r["margin"] = r.clock - r.t_win
    r["align"] = r.aligned.str.replace(r"[LR]$", "", regex=True).str.replace(r"[LR](?=\w)", "", regex=True)
    return r


def expected_beat(r: pd.DataFrame) -> pd.Series:
    """P(win before the clock) from context a receiver doesn't control."""
    cat = ["pff_passCoverage", "pff_passCoverageType", "align", "pos", "dropBackType", "pff_playAction"]
    num = ["sep_snap", "clock", "down", "yardsToGo"]
    X = r[cat + num].copy()
    X[cat] = X[cat].astype(str)
    X[num] = X[num].fillna(X[num].median())
    model = make_pipeline(
        ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore", min_frequency=30), cat),
                           ("n", StandardScaler(), num)]),
        LogisticRegression(max_iter=2000, C=0.5),
    )
    p = cross_val_predict(model, X, r.beat.astype(int), cv=5, method="predict_proba")[:, 1]
    print(f"expected-win model AUC (5-fold CV): {roc_auc_score(r.beat, p):.3f}")
    return pd.Series(p, index=r.index)


def receiver_table(r: pd.DataFrame) -> pd.DataFrame:
    g = r.groupby(["nflId", "name", "pos"])
    tab = g.agg(team=("possessionTeam", lambda s: s.mode().iat[0]), routes=("beat", "size"),
                beat_rate=("beat", "mean"), x_beat=("x_beat", "mean"),
                med_t_win=("t_win", "median"), med_margin=("margin", "median"),
                targets=("targeted", "sum")).reset_index()
    tab["broe"] = tab.beat_rate - tab.x_beat
    for cov in ["Man", "Zone"]:
        s = r[r.pff_passCoverageType == cov].groupby("nflId").agg(
            n=("beat", "size"), b=("beat", "mean"), xb=("x_beat", "mean"))
        tab = tab.join((s.b - s.xb).rename(f"broe_{cov.lower()}"), on="nflId")
        tab = tab.join(s.n.rename(f"n_{cov.lower()}"), on="nflId")
    return tab[tab.routes >= MIN_ROUTES].sort_values("broe", ascending=False)


def sack_blame(r: pd.DataFrame) -> pd.DataFrame:
    """For every sack: was somebody open before the rush got there?"""
    s = r[r.passResult == "S"]
    plays = s.groupby(["gameId", "playId"]).agg(
        team=("possessionTeam", "first"), clock=("clock", "first"),
        first_win=("t_win", "min"), best_margin=("margin", "max")).reset_index()
    lead = plays.clock - plays.first_win

    def label(row_lead):
        if pd.isna(row_lead) or row_lead < 0:
            return "Coverage won: nobody open"
        if row_lead >= 0.5:
            return "Receiver open ≥0.5s, ball held"
        return "Receiver open <0.5s before rush"
    plays["verdict"] = [label(x) for x in lead]
    plays["lead_time"] = lead
    return plays


def main():
    routes = pd.read_parquet(OUT / "routes.parquet")
    curves = pd.read_parquet(OUT / "sep_curves.parquet")
    r = add_wins(routes, curves)
    r["x_beat"] = expected_beat(r)
    r.to_parquet(OUT / "routes_scored.parquet", index=False)

    tgt = r[r.targeted & r.passResult.isin(["C", "I", "IN"])]
    val = tgt.groupby("beat").agg(targets=("beat", "size"),
                                  comp_pct=("passResult", lambda s: (s == "C").mean()),
                                  yds_per_target=("playResult", "mean"),
                                  int_pct=("passResult", lambda s: (s == "IN").mean()))
    print("\nTargets, by whether the receiver beat the rush:\n", val.round(3))
    val.to_csv(OUT / "validation_targets.csv")

    rec = receiver_table(r)
    rec.to_csv(OUT / "receivers.csv", index=False)
    sacks = sack_blame(r)
    sacks.to_csv(OUT / "sacks.csv", index=False)
    print("\nSack verdicts:\n", sacks.verdict.value_counts(normalize=True).round(3))
    print("\nTop BROE:\n", rec.head(12)[["name", "pos", "team", "routes", "beat_rate", "x_beat", "broe",
                                          "broe_man", "broe_zone"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
