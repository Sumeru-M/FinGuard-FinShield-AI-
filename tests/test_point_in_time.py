"""C12-2: point-in-time correctness — the discipline that keeps training honest.
A transaction's features must reflect state BEFORE that transaction (house rule 1)."""

import pandas as pd

from finguard.features import build_feature_frame


def _txn(i, ts, card="card_A", device="dev_1", merchant="m_1", amount=50.0,
         label="confirmed_legitimate"):
    return dict(transaction_id=f"t{i}", institution_id="inst_001",
                timestamp=pd.Timestamp(ts), card_id=card, merchant_id=merchant,
                merchant_category="grocery", amount=amount, country="US",
                device_id=device, device_age_days=100.0, channel="ecom",
                session_behavior_score=0.9, label=label, variant="none")


def test_first_transaction_sees_empty_state():
    df = pd.DataFrame([_txn(0, "2026-06-01 10:00")])
    ff = build_feature_frame(df)
    r = ff.iloc[0]
    assert r["txn_count_24h"] == 0
    assert r["is_new_device_for_card"] == 1
    assert r["is_new_merchant_for_card"] == 1
    assert r["device_observed_age_days"] == 0.0


def test_second_transaction_sees_first_but_not_itself():
    df = pd.DataFrame([
        _txn(0, "2026-06-01 10:00"),
        _txn(1, "2026-06-01 11:00"),
    ])
    ff = build_feature_frame(df)
    r = ff.iloc[1]
    assert r["txn_count_24h"] == 1          # sees txn 0, not itself
    assert r["is_new_device_for_card"] == 0
    assert r["is_new_merchant_for_card"] == 0


def test_label_feedback_respects_24h_latency():
    # Fraud at 10:00 day 1; another txn on the same device 1h later must NOT see the
    # confirmation yet; a txn the NEXT day (>24h) must see it.
    df = pd.DataFrame([
        _txn(0, "2026-06-01 10:00", card="card_A", device="dev_shared",
             label="confirmed_fraud_cnp"),
        _txn(1, "2026-06-01 11:00", card="card_B", device="dev_shared"),
        _txn(2, "2026-06-02 11:00", card="card_C", device="dev_shared"),
    ])
    ff = build_feature_frame(df)
    assert ff.iloc[1]["device_confirmed_fraud_links"] == 0   # too soon
    assert ff.iloc[2]["device_confirmed_fraud_links"] == 1   # after label latency
