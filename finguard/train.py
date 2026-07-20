"""WS-4: Fraud model v0 — LightGBM, dual-threshold tuning, SHAP, bias review.

Constraints implemented (see phase0/00_decisions_log.md):
  D-010  asymmetric cost, FN = 5x FP, re-derivation memo emitted at eval
  D-007  <= 200 investigator alerts/day at pilot volume
  D-005  graduated decisions: approve / soft_challenge / hard_block
  D-011  SHAP-based attribution baked in at train time (TreeExplainer)
Time-based split (train on first 70% of days, evaluate on the rest) — no
shuffling, so evaluation is honest about "trained on past, scored on future".
"""

from __future__ import annotations

import json
import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd

from finguard.features import FEATURE_COLUMNS

# Cost model per D-010 (PM + Fraud Analyst working assumption):
#   missed fraud (approved)          = 5.0
#   legit hard-blocked               = 1.0   (a false decline)
#   legit soft-challenged            = 0.3   (recoverable friction)
#   fraud soft-challenged            = 1.0   (step-up stops most, not all)
COST_FN, COST_FP_BLOCK, COST_FP_CHAL, COST_FRAUD_CHAL = 5.0, 1.0, 0.3, 1.0
ALERT_CAP_PER_DAY = 200  # D-007


def expected_cost(y, score, t_chal, t_block):
    blocked = score >= t_block
    challenged = (score >= t_chal) & ~blocked
    approved = score < t_chal
    return (
        COST_FN * (y & approved).sum()
        + COST_FRAUD_CHAL * (y & challenged).sum()
        + COST_FP_BLOCK * (~y & blocked).sum()
        + COST_FP_CHAL * (~y & challenged).sum()
    )


def analytic_thresholds(oof_scores, n_train_days):
    """C3 method, C12: mechanics moved to finguard.core (shared by all channels).
    Kept as a thin wrapper because federation.py imports it with card constants."""
    from finguard.core import apply_alert_cap, graduated_thresholds
    t_chal, t_block = graduated_thresholds(COST_FN, COST_FRAUD_CHAL,
                                           COST_FP_BLOCK, COST_FP_CHAL)
    t_chal = apply_alert_cap(t_chal, oof_scores, n_train_days, ALERT_CAP_PER_DAY)
    return t_chal, float(max(t_block, t_chal))


def bias_proxy_review(ff, score, threshold):
    """Guardrail check: do flags concentrate on any geography beyond its fraud base
    rate? Uses the ACTUAL alert threshold (a quantile cutoff degenerates when the
    score distribution has heavy ties, which tree models produce). Country is our
    only demographic-adjacent field; it is NOT a model feature — only derived
    mismatch flags are."""
    df = pd.read_parquet("data/transactions.parquet")[["transaction_id", "country"]]
    m = ff.merge(df, on="transaction_id")
    m["flagged"] = score >= threshold
    m["fraud"] = m["label"] != "confirmed_legitimate"
    rep = m.groupby("country").agg(fraud_rate=("fraud", "mean"),
                                   flag_rate=("flagged", "mean")).round(5)
    rep["flag_over_fraud"] = (rep["flag_rate"] / rep["fraud_rate"].clip(lower=1e-6)).round(2)
    return rep


def main():
    ff = pd.read_parquet("data/features.parquet")
    ff["y"] = (ff["label"] != "confirmed_legitimate").astype(int)

    days = ff["timestamp"].dt.normalize()
    uniq = days.unique()
    cutoff = uniq[int(len(uniq) * 0.7)]
    train, test = ff[days < cutoff], ff[days >= cutoff]
    n_test_days = test["timestamp"].dt.normalize().nunique()

    # C3-2 (D-016) via C12 shared core: OOF isotonic calibration on the full window
    # (fraud rows too scarce for a holdout — see registry train_..._150223)
    from finguard.core import score_calibrated, train_calibrated

    Xtr, ytr = train[FEATURE_COLUMNS], train["y"].values
    model, calibrator, oof_cal = train_calibrated(
        Xtr, ytr, scale_pos_weight=COST_FN, n_estimators=400, num_leaves=63)
    score = score_calibrated(model, calibrator, test[FEATURE_COLUMNS])
    y = test["y"].values.astype(bool)

    n_train_days = train["timestamp"].dt.normalize().nunique()
    t_chal, t_block = analytic_thresholds(oof_cal, n_train_days)
    cost = expected_cost(y, score, t_chal, t_block)
    naive_cost = COST_FN * y.sum()  # baseline: approve everything

    # Per-variant recall (C2): the honest number — how much of the EVASIVE fraud we catch
    variant_recall = {}
    if "variant" in test.columns:
        alerted_mask = score >= t_chal
        for v in ["blatant", "evasive"]:
            vm = (test["variant"] == v).values
            if (vm & y).sum():
                variant_recall[v] = float((vm & y & alerted_mask).sum() / (vm & y).sum())

    blocked, chal = score >= t_block, (score >= t_chal) & (score < t_block)
    caught = (y & (score >= t_chal)).sum()
    metrics = {
        "test_rows": int(len(test)), "test_days": int(n_test_days),
        "test_fraud_rows": int(y.sum()),
        "t_challenge": t_chal, "t_block": t_block,
        "recall_at_alert": float(caught / y.sum()),
        "precision_at_alert": float((y & (score >= t_chal)).sum() / max((score >= t_chal).sum(), 1)),
        "alerts_per_day": float((score >= t_chal).sum() / n_test_days),
        "hard_blocks_per_day": float(blocked.sum() / n_test_days),
        "false_block_rate": float((~y & blocked).sum() / (~y).sum()),
        "expected_cost": float(cost), "naive_cost": float(naive_cost),
        "cost_vs_naive": float(cost / naive_cost),
        "recall_by_variant": variant_recall,
    }
    print(json.dumps(metrics, indent=2))

    print("\nBias/proxy review (flag rate vs fraud rate by country — ratios near "
          "each other's scale mean flags track actual fraud, not geography):")
    print(bias_proxy_review(test, score, t_chal).to_string())

    with open("data/model_v0.pkl", "wb") as f:
        pickle.dump({"model": model, "calibrator": calibrator,
                     "t_challenge": t_chal, "t_block": t_block,
                     "features": FEATURE_COLUMNS}, f)
    with open("data/metrics_v0.json", "w") as f:
        json.dump(metrics, f, indent=2)

    from finguard.experiments import log_run
    run_id = log_run("train", params={
        "model": "LGBMClassifier", "n_estimators": 400, "learning_rate": 0.05,
        "num_leaves": 63, "scale_pos_weight": COST_FN,
        "dataset_rows": int(len(ff)), "features": FEATURE_COLUMNS,
    }, metrics=metrics, tag="")
    print(f"\nsaved data/model_v0.pkl, data/metrics_v0.json  (registry: {run_id})")


if __name__ == "__main__":
    main()
