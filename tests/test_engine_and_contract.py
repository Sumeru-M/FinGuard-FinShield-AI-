"""C12-2: scoring-engine regressions + frozen alert-format contract (D-011 amended).
Uses the trained bundle in data/model_v0.pkl (built by the standard pipeline)."""

import os

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("data/model_v0.pkl"),
    reason="model bundle not built (run the card pipeline first)")


class _Txn:
    """Fraud-shaped cold-start transaction (the Cycle 2 regression scenario)."""
    def __init__(self, i, ts, card="card_000042"):
        self.transaction_id = f"test_{i}"
        self.institution_id = "inst_001"
        self.timestamp = ts
        self.card_id = card
        self.merchant_id = "m_04999"
        self.merchant_category = "gift_cards"
        self.amount = 480.0
        self.country = "BR"
        self.device_id = "dev_fraud_999999"
        self.device_age_days = 0.01
        self.channel = "ecom"
        self.session_behavior_score = 0.31


def _engine():
    from finguard.scoring import ScoringEngine
    return ScoringEngine()


def test_repetition_attack_never_decays_to_approve():
    # Cycle 2's adaptive-repetition hole must stay closed.
    e = _engine()
    decisions = []
    for i in range(40):
        t = _Txn(i, pd.Timestamp("2026-07-01 10:00") + pd.Timedelta(minutes=7 * i))
        decisions.append(e.score(t)["decision"])
    assert decisions[0] != "approve"          # cold-start fraud pattern alerts
    assert "approve" not in decisions          # hold floors every repeat


def test_hold_expires_after_ttl_and_clears_on_disposition():
    e = _engine()
    e.score(_Txn(0, pd.Timestamp("2026-07-01 10:00")))
    # normal-looking txn on same card 3 days later: hold expired -> approve possible
    t = _Txn(1, pd.Timestamp("2026-07-05 10:00"))
    t.session_behavior_score, t.device_id = 0.86, "dev_000042_0"
    t.amount, t.device_age_days = 32.0, 300.0
    t.merchant_category, t.merchant_id = "grocery", "m_00042"
    assert e.score(t)["decision"] == "approve"
    e.holds["inst_001:card_000042"] = pd.Timestamp("2026-07-05 09:00")
    e.clear_hold("inst_001", "card_000042")
    assert "inst_001:card_000042" not in e.holds


def test_service_observability_and_hardening():
    # C18: health/ready/metrics contract + input hardening, via FastAPI TestClient.
    from fastapi.testclient import TestClient
    from finguard.scoring import create_app
    client = TestClient(create_app())

    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"   # model bundle present

    good = {"transaction_id": "m1", "timestamp": "2026-07-01T10:00:00",
            "card_id": "card_000042", "merchant_id": "m_1", "merchant_category": "grocery",
            "amount": 50.0, "country": "US", "device_id": "d1", "device_age_days": 100.0,
            "channel": "ecom", "session_behavior_score": 0.9}
    assert client.post("/score", json=good).status_code == 200

    m = client.get("/metrics").json()
    assert m["scored_total"] >= 1
    assert set(m["decisions"]) >= {"approve", "soft_challenge", "hard_block"}
    assert "p99" in m["latency_ms"]

    # hardening: out-of-range / malformed inputs are rejected with 422, not 500
    for bad in [{**good, "amount": -5.0}, {**good, "session_behavior_score": 1.7},
                {**good, "device_age_days": -1.0}, {**good, "timestamp": "not-a-date"}]:
        assert client.post("/score", json=bad).status_code == 422


def test_disposition_requires_analyst_and_is_audited(tmp_path):
    # C15 (D-049a): the label loop feeds model reputation — every disposition must
    # carry an analyst identity and land in the append-only audit trail.
    from finguard.scoring import AlertQueue
    q = AlertQueue(str(tmp_path / "alerts.db"))
    q.push({"alert_id": "a1", "transaction_id": "t1", "timestamp": "2026-07-01",
            "risk_score": 0.9, "decision": "hard_block"})
    with pytest.raises(PermissionError):
        q.disposition("a1", "confirmed_fraud_cnp", analyst_id="")
    q.disposition("a1", "confirmed_fraud_cnp", analyst_id="analyst_7")
    q.disposition("a1", "confirmed_legitimate", analyst_id="analyst_9")  # override
    trail = q.audit_trail("a1")
    assert len(trail) == 2
    assert trail[0]["analyst_id"] == "analyst_9"          # newest first
    assert trail[0]["prior_disposition"] == "confirmed_fraud_cnp"  # override is visible
    assert trail[1]["analyst_id"] == "analyst_7"


def test_alert_payload_matches_frozen_d011_contract():
    e = _engine()
    r = e.score(_Txn(0, pd.Timestamp("2026-07-01 10:00"), card="card_contract"))
    assert r["decision"] != "approve"
    a = r["alert"]
    # required fields (D-011 amended, Cycle 5)
    for field in ("alert_id", "transaction_id", "card_id", "institution_id",
                  "timestamp", "risk_score", "decision", "transaction",
                  "alert_reason", "fraud_type_prediction", "top_features",
                  "card_under_investigation"):
        assert field in a, f"missing frozen-contract field {field}"
    # removed field must STAY removed (misleading semantics — Cycle 5 review)
    assert "confidence" not in a
    # transaction context block
    for field in ("amount", "merchant_id", "merchant_category", "country", "channel"):
        assert field in a["transaction"]
    # model-driven alerts carry 3-7 attributions; hold-floored carry none
    assert a["alert_reason"] in ("model_risk", "card_under_investigation")
    if a["alert_reason"] == "model_risk":
        assert 3 <= len(a["top_features"]) <= 7
        for f in a["top_features"]:
            assert set(f) == {"feature_name", "contribution_weight", "feature_value"}
    else:
        assert a["top_features"] == []
