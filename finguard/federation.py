"""Cycle 6 (D-022): Federated learning simulation — model sharing, never data sharing.

Three synthetic institutions of very different sizes and fraud mixes. The hard
boundary (D-006): raw transactions, features, and feature-store state NEVER cross
institutions — each institution builds features and trains entirely locally. What
crosses the boundary is the trained, calibrated model artifact only, exchanged
out-of-band (never in the 100ms scoring path, per the D-004-compatible design).

Federation scheme for gradient-boosted trees: cross-institution ensemble fusion —
each institution scores with every peer model and averages calibrated
probabilities. (Classic FedAvg applies to gradient-descent parameters; for trees,
model-fusion ensembling is the standard parameter-sharing analogue.)

Hypothesis under test: federation helps the SMALL institution most — it has too
little fraud to learn evasive patterns alone, and peers' models carry that
knowledge in without a single raw record moving.
"""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold

from finguard import datagen
from finguard.features import FEATURE_COLUMNS, build_feature_frame
from finguard.train import COST_FN, analytic_thresholds, expected_cost

# Deliberately heterogeneous: a large incumbent, a mid-size, and a small fintech
# (different fraud mixes via evasive_share — attackers don't hit everyone equally)
INSTITUTIONS = [
    {"id": "inst_001", "cards": 2500, "days": 30, "seed": 42, "evasive_share": 0.5},
    {"id": "inst_002", "cards": 1200, "days": 30, "seed": 1337, "evasive_share": 0.7},
    {"id": "inst_003", "cards": 350,  "days": 30, "seed": 777, "evasive_share": 0.6},
]


def build_institution(cfg) -> dict:
    """Everything in here is institution-local. Nothing returned except what the
    institution itself owns."""
    df = datagen.generate(cfg["cards"], cfg["days"], 0.002, cfg["seed"], cfg["evasive_share"])
    df["institution_id"] = cfg["id"]
    ff = build_feature_frame(df)
    ff["y"] = (ff["label"] != "confirmed_legitimate").astype(int)
    days = ff["timestamp"].dt.normalize()
    cutoff = days.unique()[int(len(days.unique()) * 0.7)]
    return {"id": cfg["id"], "train": ff[days < cutoff], "test": ff[days >= cutoff]}


def train_local(inst) -> dict:
    """Local training + OOF isotonic calibration (same recipe as the main pipeline)."""
    tr = inst["train"]
    X, y = tr[FEATURE_COLUMNS], tr["y"].values
    oof = np.zeros(len(tr))
    for tr_i, va_i in StratifiedKFold(5, shuffle=True, random_state=42).split(X, y):
        m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63,
                               scale_pos_weight=COST_FN, random_state=42, verbose=-1)
        m.fit(X.iloc[tr_i], y[tr_i])
        oof[va_i] = m.predict_proba(X.iloc[va_i])[:, 1]
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oof, y)
    model = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63,
                               scale_pos_weight=COST_FN, random_state=42, verbose=-1)
    model.fit(X, y)
    n_days = tr["timestamp"].dt.normalize().nunique()
    t_chal, t_block = analytic_thresholds(cal.predict(oof), n_days)
    # The ONLY artifact that may leave the institution:
    return {"model": model, "calibrator": cal, "t_chal": t_chal, "t_block": t_block}


def fed_score(models: list[dict], X) -> np.ndarray:
    """Federated ensemble: average of every institution's calibrated probability."""
    return np.mean([a["calibrator"].predict(a["model"].predict_proba(X)[:, 1])
                    for a in models], axis=0)


def evaluate(y, score, t_chal, t_block) -> dict:
    yb = y.astype(bool)
    alerted, blocked = score >= t_chal, score >= t_block
    return {
        "recall": round(float((yb & alerted).sum() / max(yb.sum(), 1)), 4),
        "precision": round(float((yb & alerted).sum() / max(alerted.sum(), 1)), 4),
        "cost_vs_naive": round(float(
            expected_cost(yb, score, t_chal, t_block) / (COST_FN * max(yb.sum(), 1))), 4),
        "fraud_rows": int(yb.sum()),
    }


def main():
    insts = [build_institution(c) for c in INSTITUTIONS]
    artifacts = {i["id"]: train_local(i) for i in insts}

    report = {}
    for inst in insts:
        te = inst["test"]
        X, y = te[FEATURE_COLUMNS], te["y"].values
        own = artifacts[inst["id"]]

        local_score = own["calibrator"].predict(own["model"].predict_proba(X)[:, 1])
        fed = fed_score(list(artifacts.values()), X)
        # Institution keeps its own analytically derived thresholds in both settings
        report[inst["id"]] = {
            "test_rows": len(te),
            "local": evaluate(y, local_score, own["t_chal"], own["t_block"]),
            "federated": evaluate(y, fed, own["t_chal"], own["t_block"]),
        }

    print(json.dumps(report, indent=2))
    with open("data/federation_report.json", "w") as f:
        json.dump(report, f, indent=2)

    from finguard.experiments import log_run
    log_run("federation", params={"institutions": INSTITUTIONS}, metrics=report,
            tag="cycle6")


if __name__ == "__main__":
    main()
