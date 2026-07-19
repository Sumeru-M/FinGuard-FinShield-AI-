"""WS-3 + WS-5: Real-time scoring engine, FastAPI service, and alert generation.

The ScoringEngine is the synchronous hot path (D-004: 100ms p99 budget):
feature-store read -> LightGBM inference -> SHAP attribution -> decision.
Decisions are approve / soft_challenge / hard_block ONLY — account-level
actions are structurally impossible here (D-005).

Alerts follow the D-011 payload spec exactly: top 3–7 human-readable
contributing features with relative weights, emitted for every non-approve
decision into the investigator queue (SQLite for the pilot).
"""

from __future__ import annotations

import pickle
import sqlite3
import time
import json

import numpy as np
import pandas as pd

from finguard.features import FEATURE_COLUMNS, FEATURE_DISPLAY, InMemoryFeatureStore

DB_PATH = "data/alerts.db"


HOLD_TTL = pd.Timedelta(hours=48)


class ScoringEngine:
    def __init__(self, model_path="data/model_v0.pkl", store=None):
        with open(model_path, "rb") as f:
            bundle = pickle.load(f)
        self.model = bundle["model"]
        self.calibrator = bundle.get("calibrator")   # C3-2: optional isotonic calibration
        self.t_challenge = bundle["t_challenge"]
        self.t_block = bundle["t_block"]
        self.store = store or InMemoryFeatureStore()
        self.booster = self.model.booster_
        # Investigation-hold state (Cycle 2 / D-015): card -> hold-set timestamp.
        # Closes the adaptive-repetition hole: once a card alerts, later txns can't
        # decay to approve just because repetition normalized the card's profile.
        self.holds: dict[str, pd.Timestamp] = {}

    def _hold_key(self, txn):
        return f"{txn.institution_id}:{txn.card_id}"

    def _is_held(self, txn) -> bool:
        set_at = self.holds.get(self._hold_key(txn))
        if set_at is None:
            return False
        if txn.timestamp - set_at > HOLD_TTL:
            del self.holds[self._hold_key(txn)]
            return False
        return True

    def clear_hold(self, institution_id: str, card_id: str):
        self.holds.pop(f"{institution_id}:{card_id}", None)

    def score(self, txn) -> dict:
        """txn: object with the raw transaction fields. Returns decision + alert payload."""
        t0 = time.perf_counter()
        feats = self.store.features_for(txn)
        x = np.array([[feats[c] for c in FEATURE_COLUMNS]])
        # booster.predict avoids sklearn's per-call feature-name validation on the hot path
        risk = float(self.booster.predict(x)[0])
        if self.calibrator is not None:
            risk = float(self.calibrator.predict([risk])[0])

        held = self._is_held(txn)
        if risk >= self.t_block:
            decision = "hard_block"
        elif risk >= self.t_challenge or held:
            decision = "soft_challenge"   # held cards are floored at soft_challenge (D-005-safe)
        else:
            decision = "approve"

        result = {
            "transaction_id": txn.transaction_id,
            "timestamp": str(txn.timestamp),
            "risk_score": round(risk, 6),
            "decision": decision,
            "latency_ms": None,  # filled below, after attribution
        }

        if decision != "approve":
            # SHAP attribution only on the alert path — approves don't pay for it
            contrib = self.booster.predict(x, pred_contrib=True)[0][:-1]  # last col = bias
            order = np.argsort(-np.abs(contrib))
            total = np.abs(contrib).sum() or 1.0
            top = [
                {
                    "feature_name": FEATURE_DISPLAY[FEATURE_COLUMNS[i]],
                    "contribution_weight": round(float(abs(contrib[i]) / total), 4),
                    "feature_value": str(round(float(feats[FEATURE_COLUMNS[i]]), 4)),
                }
                for i in order[:7] if abs(contrib[i]) / total >= 0.02
            ][:7]
            top = top if len(top) >= 3 else [
                {
                    "feature_name": FEATURE_DISPLAY[FEATURE_COLUMNS[i]],
                    "contribution_weight": round(float(abs(contrib[i]) / total), 4),
                    "feature_value": str(round(float(feats[FEATURE_COLUMNS[i]]), 4)),
                }
                for i in order[:3]
            ]
            result["alert"] = {
                "alert_id": f"alert_{txn.transaction_id}",
                "transaction_id": txn.transaction_id,
                "card_id": txn.card_id,
                "institution_id": txn.institution_id,
                "timestamp": str(txn.timestamp),
                "risk_score": round(risk, 6),
                "decision": decision,
                "fraud_type_prediction": "unscored_v0",  # typed prediction is a v1 model iteration
                "top_features": top,
                "confidence": round(abs(risk - 0.5) * 2, 4),
                "card_under_investigation": held,
            }
            # Only model-driven alerts set/refresh the hold — a hold-floored alert must
            # not extend itself, or a legit customer could stay challenged indefinitely
            if risk >= self.t_challenge:
                self.holds[self._hold_key(txn)] = txn.timestamp

        self.store.update(txn)
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        return result


class AlertQueue:
    """WS-5 investigator queue. Dispositions feed the label loop (Phase 0 labeling standard)."""

    DISPOSITIONS = {"confirmed_fraud_cnp", "confirmed_fraud_ato",
                    "confirmed_fraud_synthetic_card", "confirmed_legitimate", "unresolved"}

    def __init__(self, db_path=DB_PATH):
        # check_same_thread=False: FastAPI serves sync endpoints from a threadpool;
        # writes are serialized by sqlite itself at this pilot's volume
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
            alert_id TEXT PRIMARY KEY, transaction_id TEXT, timestamp TEXT,
            risk_score REAL, decision TEXT, payload TEXT,
            disposition TEXT DEFAULT NULL)""")

    def push(self, alert: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,NULL)",
            (alert["alert_id"], alert["transaction_id"], alert["timestamp"],
             alert["risk_score"], alert["decision"], json.dumps(alert)))
        self.conn.commit()

    def pending(self, limit=50):
        cur = self.conn.execute(
            "SELECT payload FROM alerts WHERE disposition IS NULL ORDER BY risk_score DESC LIMIT ?",
            (limit,))
        return [json.loads(r[0]) for r in cur.fetchall()]

    def get(self, alert_id: str) -> dict | None:
        cur = self.conn.execute("SELECT payload FROM alerts WHERE alert_id=?", (alert_id,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def disposition(self, alert_id: str, label: str):
        if label not in self.DISPOSITIONS:
            raise ValueError(f"invalid disposition {label!r}; must be one of {sorted(self.DISPOSITIONS)}")
        self.conn.execute("UPDATE alerts SET disposition=? WHERE alert_id=?", (label, alert_id))
        self.conn.commit()


from pydantic import BaseModel


class TxnIn(BaseModel):
    transaction_id: str
    institution_id: str = "inst_001"
    timestamp: str
    card_id: str
    merchant_id: str
    merchant_category: str
    amount: float
    country: str
    device_id: str
    device_age_days: float
    channel: str
    session_behavior_score: float


class _T:  # engine expects attribute access with a pandas Timestamp
    def __init__(self, m: TxnIn):
        self.__dict__.update(m.model_dump())
        self.timestamp = pd.Timestamp(m.timestamp)


def create_app():
    """FastAPI wrapper — the network-facing form of the engine."""
    from fastapi import Body, FastAPI, HTTPException

    app = FastAPI(title="FinGuard scoring service")
    engine = ScoringEngine()
    queue = AlertQueue()

    @app.post("/score")
    def score(txn: TxnIn = Body(...)):
        result = engine.score(_T(txn))
        if "alert" in result:
            queue.push(result["alert"])
        return result

    @app.get("/alerts")
    def alerts(limit: int = 50):
        return queue.pending(limit)

    @app.post("/alerts/{alert_id}/disposition/{label}")
    def disposition(alert_id: str, label: str):
        try:
            queue.disposition(alert_id, label)
        except ValueError as e:
            raise HTTPException(422, str(e))
        hold_cleared = False
        if label == "confirmed_legitimate":
            a = queue.get(alert_id)
            if a and "card_id" in a:
                engine.clear_hold(a["institution_id"], a["card_id"])
                hold_cleared = True
        return {"alert_id": alert_id, "disposition": label, "hold_cleared": hold_cleared}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8100, log_level="warning")
