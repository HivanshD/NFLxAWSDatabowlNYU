"""Round 2 harness: signal, split-half stability, and a PRE-REGISTERED face-validity test
for the 8 new ideas, applied retroactively to the round-1 route metrics too."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict, GroupKFold

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "explore"
KEY = ["gameId", "playId", "nflId"]

# Pre-registered consensus top receivers of 2021 (fixed before looking at any metric output)
ELITE = ["Cooper Kupp", "Davante Adams", "Justin Jefferson", "Ja'Marr Chase", "Tyreek Hill", "Deebo Samuel",
         "Stefon Diggs", "Mike Evans", "CeeDee Lamb", "A.J. Brown", "Diontae Johnson", "Keenan Allen",
         "DK Metcalf", "Tyler Lockett", "Chris Godwin", "D.J. Moore", "Travis Kelce", "Mark Andrews",
         "George Kittle", "Darren Waller"]
MIN_ROUTES = 100


def split_half(df, val, min_n=25):
    d = df.dropna(subset=[val]).copy()
    d["h"] = d.gameId.rank(method="dense").astype(int) % 2
    g = d.groupby(["nflId", "h"])[val].agg(["mean", "size"]).unstack()
    g = g[(g["size"][0] >= min_n) & (g["size"][1] >= min_n)]
    return (round(float(np.corrcoef(g["mean"][0], g["mean"][1])[0, 1]), 2) if len(g) >= 10 else np.nan), len(g)


def face(df, val, higher_is_good, min_n=MIN_ROUTES):
    """Mean percentile of the elite list among WR/TE with >= min_n reps, in the pre-registered direction.
    0.5 = elite look average. Pass >= 0.64 (~2 SE above chance for ~18 players)."""
    d = df[df.pos.isin(["WR", "TE"])].dropna(subset=[val])
    g = d.groupby("name")[val].agg(["mean", "size"])
    g = g[g["size"] >= min_n]
    pct = g["mean"].rank(pct=True)
    if not higher_is_good:
        pct = 1 - pct
    e = pct.reindex([n for n in ELITE if n in pct.index])
    top = (g["mean"].sort_values(ascending=not higher_is_good)).head(6).index.tolist()
    return round(float(e.mean()), 2), len(e), top


def tgt_table(t, col, q=3):
    t = t.dropna(subset=[col]).copy()
    try:
        t["bin"] = pd.qcut(t[col], q, duplicates="drop")
    except ValueError:
        t["bin"] = t[col]
    return t.groupby("bin", observed=True).agg(n=("passResult", "size"),
                                               comp=("passResult", lambda s: (s == "C").mean()),
                                               INT=("passResult", lambda s: (s == "IN").mean()),
                                               ypt=("playResult", "mean")).round(3)


def report(name, df, val, higher, signal_note, min_n_face=MIN_ROUTES, min_n_sh=25):
    fv = face(df, val, higher, min_n_face)
    sh = split_half(df, val, min_n_sh)
    print(f"  stability {sh} | face-validity elite pct {fv[0]} (n={fv[1]}) {'PASS' if fv[0] >= 0.64 else 'FAIL'}")
    print(f"  top by metric: {fv[2]}")
    return dict(idea=name, stability=sh[0], face=fv[0], signal=signal_note)


def main():
    N = pd.read_parquet(E / "feat_new.parquet")
    N = N[N.pos.isin(["WR", "TE", "RB"])]
    N["targeted"] = N.targeted.fillna(False)
    T = N[N.targeted & N.passResult.isin(["C", "I", "IN"])]
    out = []

    print("\n=== N1 GRAVITY (defender attention) ===")
    # decoy value: per thrown play, gravity pulled by NON-targeted receivers vs play yards
    thrown = N[N.passResult.isin(["C", "I", "IN"]) & N.target_found.fillna(False)]
    pl = thrown.groupby(["gameId", "playId"]).apply(lambda d: pd.Series(dict(
        decoy_grav=d.loc[~d.targeted, "gravity"].sum(), tgt_grav=d.loc[d.targeted, "gravity"].sum(),
        n=len(d), yds=d.playResult.iat[0], comp=(d.passResult.iat[0] == "C")))).reset_index()
    pl["dg_bin"] = pd.qcut(pl.decoy_grav, 3, labels=["low", "mid", "high"])
    print(pl.groupby("dg_bin", observed=True).agg(plays=("yds", "size"), ypa=("yds", "mean"), comp=("comp", "mean")).round(3))
    print("  targeted receiver's own gravity:\n", tgt_table(T, "gravity"))
    out.append(report("N1 Gravity", N, "gravity", True, "decoy gravity vs play yds (see table)"))

    print("\n=== N2 EYES OFF (nearest defender facing QB) ===")
    print(T.groupby("eyes_on_qb").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                                      INT=("passResult", lambda s: (s == "IN").mean()), ypt=("playResult", "mean")).round(3))
    N["eyes_qb_f"] = N.eyes_on_qb.astype(float)
    out.append(report("N2 Eyes Off", N, "eyes_qb_f", False, "comp/INT by defender eyes"))

    print("\n=== N3 READ ORDER (QB shoulders on receiver) ===")
    d = N.dropna(subset=["qb_look_share"])
    auc = roc_auc_score(d.targeted, d.qb_look_share)
    print(f"  AUC(qb_look_share -> targeted) = {auc:.3f}")
    print("  corr(player look share, player target rate):",
          round(d.groupby("name").agg(a=("qb_look_share", "mean"), b=("targeted", "mean")).corr().iloc[0, 1], 2))
    out.append(report("N3 Read Order", N, "qb_look_share", True, f"AUC {auc:.2f} for target"))

    print("\n=== N4 CONFLICT MAKER ===")
    print(tgt_table(T.assign(c=T.conflict.clip(upper=2)), "c", q=1) if False else
          T.assign(c=T.conflict.clip(upper=2)).groupby("c").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                                                                 ypt=("playResult", "mean")).round(3))
    out.append(report("N4 Conflict", N, "conflict", True, "target outcome by conflict count"))

    print("\n=== N5 CLEAN ENTRY ===")
    deep = T.dropna(subset=["clean_entry"])
    print(deep.groupby("clean_entry").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                                          INT=("passResult", lambda s: (s == "IN").mean()), ypt=("playResult", "mean")).round(3))
    N["clean_f"] = N.clean_entry.astype(float)
    out.append(report("N5 Clean Entry", N, "clean_f", True, "deep-target ypt", min_n_face=40, min_n_sh=15))

    print("\n=== N6 WORK-BACK ===")
    print(tgt_table(T, "work_back"))
    out.append(report("N6 Work-Back", N, "work_back", True, "comp/INT by work-back"))

    print("\n=== N7 SCRAMBLE DRILL (plays >= 3.5s) ===")
    ext = T.dropna(subset=["ext_gain"])
    print("  extended targets", len(ext)); print(tgt_table(ext, "ext_speed"))
    out.append(report("N7 Scramble", N, "ext_speed", True, "ext-play target success", min_n_face=25, min_n_sh=10))

    print("\n=== N8 LANE TRAFFIC ===")
    T2 = T.assign(lane=T.lane_traffic.clip(upper=2))
    print(T2.groupby("lane").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                                 INT=("passResult", lambda s: (s == "IN").mean()), ypt=("playResult", "mean"), dist=("throw_dist", "mean")).round(3))
    X = np.c_[T.lane_traffic, T.throw_dist]
    y = (T.passResult == "C").astype(int)
    p0 = cross_val_predict(LogisticRegression(), X[:, [1]], y, cv=GroupKFold(5), groups=T.gameId, method="predict_proba")[:, 1]
    p1 = cross_val_predict(LogisticRegression(), X, y, cv=GroupKFold(5), groups=T.gameId, method="predict_proba")[:, 1]
    print(f"  completion AUC: throw distance only {roc_auc_score(y, p0):.3f} -> +lane traffic {roc_auc_score(y, p1):.3f}")
    out.append(report("N8 Lane Traffic", N, "lane_traffic", False, "comp/INT vs traffic"))

    print("\n=== ROUND-1 ROUTE METRICS, same face-validity test ===")
    R = pd.read_parquet(E / "feat_route.parquet")
    R = R[R.pos.isin(["WR", "TE", "RB"])]
    R["decel_rel"] = R.decel / R.vmax_pre.clip(lower=1)
    R["lev_flip_f"] = R.lev_flip.astype(float)
    R["bite_f"] = R.bite.astype(float)
    co = np.polyfit(R.dropna(subset=["melt", "cushion0"]).cushion0, R.dropna(subset=["melt", "cushion0"])["melt"], 1)
    R["melt_resid"] = R["melt"] - np.polyval(co, R.cushion0)
    for nm, v, h, mn in [("A3 Brake Lights", "decel_rel", True, 15), ("A5 Cushion Melt", "melt_resid", True, MIN_ROUTES),
                         ("B1 Hip Honesty", "hip", True, 15), ("B2 Bite Rate", "bite_f", True, 15),
                         ("B4 Leverage Flip", "lev_flip_f", True, 40), ("B5 First-Second Yds", "yds_1s", True, MIN_ROUTES)]:
        print(nm, end=": ")
        fv = face(R, v, h, mn)
        print(f"elite pct {fv[0]} (n={fv[1]}) {'PASS' if fv[0] >= 0.64 else 'FAIL'}; top {fv[2][:4]}")
    S = pd.read_parquet(ROOT / "outputs" / "routes_scored.parquet")
    S = S[S.clock >= 2.5].assign(w=lambda d: (d.t_win <= 2.5).astype(float))
    fv = face(S, "w", True, 60)
    print(f"Beat the Rush (fixed horizon): elite pct {fv[0]} (n={fv[1]}) {'PASS' if fv[0] >= 0.64 else 'FAIL'}; top {fv[2][:4]}")

    print("\n=== SUMMARY (new ideas) ===")
    print(pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()
