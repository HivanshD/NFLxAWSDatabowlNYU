"""Strict signal + stability tests for the 10 candidate ideas."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "explore"
KEY = ["gameId", "playId", "nflId"]


def split_half(df, val, by="nflId", min_n=25):
    """Odd vs even game halves: corr of player means. ~0 = noise, >0.5 = real trait."""
    d = df.dropna(subset=[val]).copy()
    d["half"] = d.gameId.rank(method="dense").astype(int) % 2
    g = d.groupby([by, "half"])[val].agg(["mean", "size"]).unstack()
    g = g[(g["size"][0] >= min_n) & (g["size"][1] >= min_n)]
    if len(g) < 10:
        return np.nan, len(g)
    return np.corrcoef(g["mean"][0], g["mean"][1])[0, 1], len(g)


def auc_cv(df, feats, y, cats=()):
    X = df[list(feats)].copy()
    for c in cats:
        X[c] = X[c].astype("category")
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, categorical_features="from_dtype")
    p = cross_val_predict(m, X, df[y].astype(int), cv=GroupKFold(5), groups=df.gameId, method="predict_proba")[:, 1]
    return roc_auc_score(df[y], p), p


def outcome(t, col, q=3):
    t = t.dropna(subset=[col]).copy()
    t["bin"] = pd.qcut(t[col], q, labels=["low", "mid", "high"][:q] if q == 3 else None, duplicates="drop")
    return t.groupby("bin", observed=True).agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()),
                                               ypt=("playResult", "mean")).round(3)


def main():
    R = pd.read_parquet(E / "feat_route.parquet")
    tg = pd.read_parquet(ROOT / "outputs" / "routes.parquet")[KEY + ["targeted"]]
    R = R.merge(tg, on=KEY, how="left")
    R = R[R.pos.isin(["WR", "TE", "RB"])]
    T = R[R.targeted.fillna(False) & R.passResult.isin(["C", "I", "IN"])]
    man = R[R.pff_passCoverageType == "Man"]
    rep = {}

    print("\n=== A1 POKER FACE: TE/RB block vs route ===")
    tl = pd.read_parquet(E / "feat_tell.parquet").dropna(subset=["depth"])
    base = ["aligned", "pos", "offenseFormation", "personnelO", "down", "yardsToGo", "dropBackType", "depth", "wide"]
    cats = ["aligned", "pos", "offenseFormation", "personnelO", "dropBackType"]
    a0, _ = auc_cv(tl, base, "route", cats)
    a1, p1 = auc_cv(tl, base + ["o_snap", "o_abs", "s_pre", "o_pre_sd"], "route", cats)
    a2, _ = auc_cv(tl, base + ["o_snap", "o_abs", "s_pre", "o_pre_sd", "s_03", "dx_03", "dir_03"], "route", cats)
    print(f"route share {tl.route.mean():.2f} | AUC alignment/context {a0:.3f} -> +pre-snap body {a1:.3f} -> +first 0.3s {a2:.3f}")
    tl["p"] = p1
    tl["correct"] = (tl.p > 0.5) == tl.route
    te = tl[tl.pos == "TE"].groupby("name").agg(n=("route", "size"), blk=("route", lambda s: 1 - s.mean()),
                                                 acc=("correct", "mean"))
    te = te[(te.n >= 80) & (te.blk >= 0.1)].sort_values("acc")
    print("TE predictability (pre-snap model accuracy), blocks >=10% of reps:\n", te.round(2).head(5).to_string(), "\n...\n", te.round(2).tail(5).to_string())
    print("split-half reliability of player tell accuracy:", split_half(tl.assign(c=tl.correct.astype(float)), "c", min_n=30))

    print("\n=== A2/B4 LEVERAGE (man coverage) ===")
    print("flip rate", man.lev_flip.mean().round(3), "| reliability", split_half(man.assign(f=man.lev_flip.astype(float)), "f"))
    tm = T[T.pff_passCoverageType == "Man"]
    print(tm.groupby("lev_flip").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()), ypt=("playResult", "mean")).round(3))
    print("corr(lev_end, sep_end) in man:", man[["lev_end", "sep_end"]].corr().iloc[0, 1].round(3))

    print("\n=== A3 BRAKE LIGHTS ===")
    b = R[R.has_break == True]
    print("routes with detected break", round(len(b) / len(R), 3), "| corr(decel, sep_gain):", b[["decel", "sep_gain"]].corr().iloc[0, 1].round(3),
          "| corr(decel, vmax_pre):", b[["decel", "vmax_pre"]].corr().iloc[0, 1].round(3))
    b = b.assign(decel_rel=b.decel / b.vmax_pre.clip(lower=1))
    print("corr(decel_rel, sep_gain):", b[["decel_rel", "sep_gain"]].corr().iloc[0, 1].round(3), "| reliability decel_rel", split_half(b, "decel_rel", min_n=10))
    print(outcome(T[T.has_break == True].assign(decel_rel=lambda d: d.decel / d.vmax_pre.clip(lower=1)), "decel_rel"))

    print("\n=== A5 CUSHION MELT ===")
    import numpy.polynomial.polynomial as P
    c = R.dropna(subset=["melt", "cushion0"])
    co = P.polyfit(c.cushion0, c["melt"], 1)
    R["melt_resid"] = R["melt"] - P.polyval(R.cushion0, co)
    print("corr(melt, cushion0):", c[["melt", "cushion0"]].corr().iloc[0, 1].round(3), "| reliability melt_resid", split_half(R, "melt_resid"))
    print(outcome(T.assign(melt_resid=R.loc[T.index, "melt_resid"]), "melt_resid"))

    print("\n=== B1 HIP HONESTY ===")
    b = R[R.has_break == True].dropna(subset=["hip"])
    print("median |o-dir| pre-break", round(b.hip.median(), 1), "| corr(hip, bite):", round(np.corrcoef(b.hip, b.bite.astype(float))[0, 1], 3),
          "| corr(hip, sep_gain):", b[["hip", "sep_gain"]].corr().iloc[0, 1].round(3), "| reliability", split_half(b, "hip", min_n=10))

    print("\n=== B2 BITE RATE ===")
    print("bite rate", round(b.bite.mean(), 3), "| sep_gain bite vs not:", b.groupby("bite").sep_gain.mean().round(2).to_dict(),
          "| reliability", split_half(b.assign(bb=b.bite.astype(float)), "bb", min_n=10))
    tb = T[T.has_break == True]
    print(tb.groupby("bite").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()), ypt=("playResult", "mean")).round(3))

    print("\n=== B5 FIRST-SECOND YARDS vs press (man, cushion<=2.5) ===")
    pr = man[man.cushion0 <= 2.5]
    print("press reps", len(pr), "| reliability", split_half(pr, "yds_1s", min_n=12), "| all-routes reliability", split_half(R, "yds_1s"))
    print(outcome(T[(T.pff_passCoverageType == "Man") & (T.cushion0 <= 2.5)], "yds_1s"))

    print("\n=== A4 CHIP TAX / CHIP VALUE ===")
    ch = pd.read_parquet(E / "feat_chip.parquet")
    print("rusher reps", len(ch), "chipped", int(ch.chipped.sum()))
    s = ch.groupby(["aligned", "chipped"]).pressure.agg(["mean", "size"]).unstack()
    s = s[(s["size"][True] >= 40)]
    s["diff"] = s["mean"][True] - s["mean"][False]
    print(s.round(3).to_string())
    w = (s["size"][True] * s["diff"]).sum() / s["size"][True].sum()
    print("alignment-matched pressure change when chipped:", round(w, 3), "vs base", round(ch.pressure.mean(), 3))
    tr = R[R.pos.isin(["TE", "RB"])]
    print("cost (TE/RB): depth at 2s / targeted / ypt when targeted")
    print(tr.groupby(tr.blockType == "CH").agg(n=("depth_2s", "size"), depth2=("depth_2s", "mean"), tgt=("targeted", "mean")).round(3))
    tt = T[T.pos.isin(["TE", "RB"])]
    print(tt.groupby(tt.blockType == "CH").agg(n=("passResult", "size"), comp=("passResult", lambda s: (s == "C").mean()), ypt=("playResult", "mean")).round(3))

    print("\n=== B3 PICKUP SCORE ===")
    pk = pd.read_parquet(E / "feat_pickup.parquet")
    print("reps", len(pk), "lost rate", pk.lost.mean().round(3))
    a0, _ = auc_cv(pk, ["blockType", "pos"], "lost", ["blockType", "pos"])
    a1, _ = auc_cv(pk, ["blockType", "pos", "t_contact", "s_blk", "s_rush", "square", "qb_dist", "depth_contact"], "lost", ["blockType", "pos"])
    print(f"AUC block type only {a0:.3f} -> +contact mechanics {a1:.3f}")
    for c in ["s_blk", "s_rush", "square", "qb_dist", "t_contact"]:
        print(f"  {c}: lost={pk[pk.lost][c].median():.2f} vs won={pk[~pk.lost][c].median():.2f}")


if __name__ == "__main__":
    main()
