"""Cycle 12 (D-038): shared training/threshold core.

One implementation of the recipe every channel converged on:
    LightGBM (cost-asymmetric scale_pos_weight)
      -> 5-fold out-of-fold predictions
      -> isotonic calibration fit on OOF (never on test; a chronological-holdout
         attempt cost 12pts recall — registry train_20260719_150223)
      -> ANALYTIC decision thresholds derived from the channel's cost model
         (never grid-searched on test labels — that leakage was found in Cycle 3)

Channels keep their own cost constants and any channel-specific threshold shape
(wire's amount-dependent threshold stays in wire.py); the mechanics live here.
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold

import lightgbm as lgb


def make_gbm(scale_pos_weight: float, n_estimators: int = 300, num_leaves: int = 31,
             learning_rate: float = 0.05, seed: int = 42) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        n_estimators=n_estimators, learning_rate=learning_rate, num_leaves=num_leaves,
        scale_pos_weight=scale_pos_weight, random_state=seed, verbose=-1)


def train_calibrated(X, y, *, scale_pos_weight: float, n_estimators: int = 300,
                     num_leaves: int = 31, n_folds: int = 5, seed: int = 42):
    """OOF-calibrated model. Returns (model, calibrator, calibrated_oof_scores)."""
    y = np.asarray(y)
    oof = np.zeros(len(y))
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    for tr_i, va_i in skf.split(X, y):
        m = make_gbm(scale_pos_weight, n_estimators, num_leaves, seed=seed)
        m.fit(X.iloc[tr_i], y[tr_i])
        oof[va_i] = m.predict_proba(X.iloc[va_i])[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(oof, y)
    model = make_gbm(scale_pos_weight, n_estimators, num_leaves, seed=seed)
    model.fit(X, y)
    return model, calibrator, calibrator.predict(oof)


def score_calibrated(model, calibrator, X) -> np.ndarray:
    return calibrator.predict(model.predict_proba(X)[:, 1])


def graduated_thresholds(cost_fn: float, cost_fraud_mid: float,
                         cost_fp_hi: float, cost_fp_mid: float) -> tuple[float, float]:
    """Analytic dual thresholds for calibrated probabilities under a per-event
    cost model with a graduated middle action (challenge / hold_funds):
        approve:  cost_fn * p
        middle:   cost_fraud_mid * p + cost_fp_mid * (1-p)
        strong:   cost_fp_hi * (1-p)
    Returns (t_mid, t_strong): middle beats approve above t_mid; strong beats
    middle above t_strong."""
    t_mid = cost_fp_mid / (cost_fn - cost_fraud_mid + cost_fp_mid)
    t_strong = (cost_fp_hi - cost_fp_mid) / (cost_fp_hi - cost_fp_mid + cost_fraud_mid)
    return float(t_mid), float(max(t_strong, t_mid))


def apply_alert_cap(t_mid: float, oof_scores: np.ndarray, n_days: float,
                    cap_per_day: float) -> float:
    """D-007/D-023 family: if the middle tier would exceed the channel's alert cap
    (estimated on OOF volume), raise t_mid to the cap-satisfying quantile."""
    if (oof_scores >= t_mid).sum() / n_days > cap_per_day:
        k = int(cap_per_day * n_days)
        return float(np.sort(oof_scores)[-k])
    return t_mid
