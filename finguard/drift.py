"""Cycle 20 (D-052): drift-monitoring hooks.

A model silently degrades when live traffic drifts from what it trained on. This module
computes distribution drift between a reference window (the training data) and a live
window, for both features and model scores, using the Population Stability Index (PSI) —
the standard, threshold-interpretable drift metric in credit/fraud ops:

    PSI < 0.10   no meaningful shift
    0.10-0.25    moderate shift — investigate
    PSI > 0.25   major shift — retrain candidate

Design intent: cheap, dependency-free (numpy only), and callable both as a batch report
(reference parquet vs live parquet) and incrementally from a live buffer. It flags; it
does not act — retraining/rollback stays a human/MLOps decision (D-005 spirit: the system
surfaces, humans decide).
"""

from __future__ import annotations

import numpy as np


def psi(reference: np.ndarray, live: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two 1-D samples. Bin edges are taken from the
    reference quantiles so PSI is comparable across features."""
    reference = np.asarray(reference, dtype=float)
    live = np.asarray(live, dtype=float)
    if reference.size == 0 or live.size == 0:
        return 0.0
    # quantile edges from reference; dedupe for near-constant features
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_pct = np.histogram(reference, edges)[0] / len(reference)
    live_pct = np.histogram(live, edges)[0] / len(live)
    eps = 1e-6
    ref_pct = np.clip(ref_pct, eps, None)
    live_pct = np.clip(live_pct, eps, None)
    return float(np.sum((live_pct - ref_pct) * np.log(live_pct / ref_pct)))


def classify(value: float) -> str:
    if value < 0.10:
        return "stable"
    if value < 0.25:
        return "moderate"
    return "major"


def feature_drift(reference_df, live_df, feature_columns) -> dict:
    """Per-feature PSI + classification between two feature frames."""
    report = {}
    for col in feature_columns:
        if col in reference_df.columns and col in live_df.columns:
            v = psi(reference_df[col].to_numpy(), live_df[col].to_numpy())
            report[col] = {"psi": round(v, 4), "status": classify(v)}
    worst = max(report.values(), key=lambda r: r["psi"], default={"psi": 0.0})
    return {
        "features": report,
        "max_psi": worst["psi"],
        "overall": classify(worst["psi"]),
        "drifting_features": [c for c, r in report.items() if r["status"] != "stable"],
    }


def score_drift(reference_scores: np.ndarray, live_scores: np.ndarray) -> dict:
    v = psi(reference_scores, live_scores)
    return {"psi": round(v, 4), "status": classify(v)}
