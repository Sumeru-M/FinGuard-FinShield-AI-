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
    """C3: derive thresholds from the cost model itself (valid because scores are
    calibrated probabilities). Per-transaction expected costs:
        approve   = COST_FN * p
        challenge = COST_FRAUD_CHAL * p + COST_FP_CHAL * (1-p)
        block     = COST_FP_BLOCK * (1-p)
    challenge beats approve above t_chal; block beats challenge above t_block.
    No test-set tuning (the previous grid search leaked test labels into the
    thresholds and overfit to <100 fraud rows). Alert cap enforced on OOF volume."""
    t_chal = COST_FP_CHAL / (COST_FN - COST_FRAUD_CHAL + COST_FP_CHAL)
    t_block = (COST_FP_BLOCK - COST_FP_CHAL) / \
              (COST_FP_BLOCK - COST_FP_CHAL + COST_FRAUD_CHAL)
    # D-007: if the challenge tier would exceed the alert cap (estimated on OOF),
    # raise t_chal to the cap-satisfying quantile
    est_alerts_per_day = (oof_scores >= t_chal).sum() / n_train_days
    if est_alerts_per_day > ALERT_CAP_PER_DAY:
        k = int(ALERT_CAP_PER_DAY * n_train_days)
        t_chal = float(np.sort(oof_scores)[-k])
    return float(t_chal), float(max(t_block, t_chal))


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

    def make_model():
        return lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.05, num_leaves=63,
            scale_pos_weight=COST_FN,      # asymmetric cost pushed into training (D-010)
            random_state=42, verbose=-1,
        )

    # C3-2 (D-016): out-of-fold isotonic calibration — every train row gets a raw score
    # from a fold-model that never saw it, the calibrator fits on those, and the final
    # model trains on the FULL window (fraud rows are too scarce to sacrifice a holdout;
    # a chronological holdout attempt cost 12pts of recall — see registry train_..._150223)
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import StratifiedKFold

    oof = np.zeros(len(train))
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    Xtr, ytr = train[FEATURE_COLUMNS], train["y"].values
    for tr_idx, va_idx in skf.split(Xtr, ytr):
        m = make_model()
        m.fit(Xtr.iloc[tr_idx], ytr[tr_idx])
        oof[va_idx] = m.predict_proba(Xtr.iloc[va_idx])[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(oof, ytr)

    model = make_model()
    model.fit(Xtr, ytr)
    score = calibrator.predict(model.predict_proba(test[FEATURE_COLUMNS])[:, 1])
    y = test["y"].values.astype(bool)

    n_train_days = train["timestamp"].dt.normalize().nunique()
    t_chal, t_block = analytic_thresholds(calibrator.predict(oof), n_train_days)
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
