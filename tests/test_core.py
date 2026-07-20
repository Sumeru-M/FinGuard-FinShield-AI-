"""C12-2: shared-core unit tests — threshold algebra and calibrated training."""

import numpy as np
import pandas as pd
import pytest

from finguard.core import (apply_alert_cap, graduated_thresholds, score_calibrated,
                           train_calibrated)


def test_card_thresholds_match_cycle3_derivation():
    # D-010 card constants: FN=5, fraud_challenged=1, FP_block=1, FP_challenge=0.3
    t_chal, t_block = graduated_thresholds(5.0, 1.0, 1.0, 0.3)
    assert t_chal == pytest.approx(0.3 / (5.0 - 1.0 + 0.3))     # 0.06977 (Cycle 3)
    assert t_block == pytest.approx(0.7 / (0.7 + 1.0))          # 0.41176 (Cycle 3)
    assert t_chal < t_block


def test_p2p_thresholds_match_cycle7_derivation():
    # D-017 P2P constants: FN=10, fraud_held=1, FP_block=1, FP_hold=0.2
    t_hold, t_block = graduated_thresholds(10.0, 1.0, 1.0, 0.2)
    assert t_hold == pytest.approx(0.0217, abs=1e-3)
    assert t_block == pytest.approx(0.4444, abs=1e-3)


def test_alert_cap_raises_threshold_only_when_exceeded():
    scores = np.linspace(0, 1, 1000)
    # cap generous -> threshold unchanged
    assert apply_alert_cap(0.5, scores, n_days=10, cap_per_day=200) == 0.5
    # cap tight (10/day over 10 days = top 100 scores) -> raised
    t = apply_alert_cap(0.5, scores, n_days=10, cap_per_day=10)
    assert t > 0.5
    assert (scores >= t).sum() <= 100


def test_train_calibrated_produces_probabilities_and_ranks_fraud_higher():
    rng = np.random.default_rng(0)
    n = 600
    y = (rng.random(n) < 0.15).astype(int)
    # one informative feature + one noise feature
    X = pd.DataFrame({
        "signal": y * rng.normal(2.0, 0.5, n) + (1 - y) * rng.normal(0.0, 0.5, n),
        "noise": rng.normal(0, 1, n),
    })
    model, cal, oof_cal = train_calibrated(X, y, scale_pos_weight=5.0,
                                           n_estimators=50, num_leaves=7)
    s = score_calibrated(model, cal, X)
    assert s.min() >= 0.0 and s.max() <= 1.0
    assert len(oof_cal) == n
    assert s[y == 1].mean() > s[y == 0].mean()
