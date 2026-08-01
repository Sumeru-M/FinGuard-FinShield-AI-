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

from finguard.config import cfg
from finguard.features import FEATURE_COLUMNS, FEATURE_DISPLAY, InMemoryFeatureStore

DB_PATH = cfg.alerts_db                          # C18: was "data/alerts.db"


HOLD_TTL = pd.Timedelta(hours=cfg.hold_ttl_hours)  # C18: was hours=48

# D-011 analyst-review fixes (Cycle 5): units for day/money-denominated features
UNIT_DAYS = {"device_age_days", "device_observed_age_days", "merchant_observed_age_days"}
UNIT_MONEY = {"amount", "amount_sum_24h"}


def _fmt_value(col: str, v: float) -> str:
    if col in UNIT_DAYS:
        return f"{v:.1f} days"
    if col in UNIT_MONEY:
        return f"${v:,.2f}"
    return str(round(float(v), 4))


class ScoringEngine:
    def __init__(self, model_path=None, store=None):
        model_path = model_path or cfg.model_path   # C18: was "data/model_v0.pkl"
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
            model_driven = risk >= self.t_challenge
            # D-011 review: SHAP attributions only justify MODEL-driven alerts. On a
            # hold-floored alert the score is low and attributions would "explain why
            # this is NOT fraud" — misleading, so they are omitted there.
            top = []
            if model_driven:
                contrib = self.booster.predict(x, pred_contrib=True)[0][:-1]  # last col = bias
                order = np.argsort(-np.abs(contrib))
                total = np.abs(contrib).sum() or 1.0
                keep = [i for i in order[:7] if abs(contrib[i]) / total >= 0.02] or list(order[:3])
                top = [
                    {
                        "feature_name": FEATURE_DISPLAY[FEATURE_COLUMNS[i]],
                        "contribution_weight": round(float(abs(contrib[i]) / total), 4),
                        "feature_value": _fmt_value(FEATURE_COLUMNS[i], feats[FEATURE_COLUMNS[i]]),
                    }
                    for i in keep[:7]
                ]
            result["alert"] = {
                "alert_id": f"alert_{txn.transaction_id}",
                "transaction_id": txn.transaction_id,
                "card_id": txn.card_id,
                "institution_id": txn.institution_id,
                "timestamp": str(txn.timestamp),
                "risk_score": round(risk, 6),
                "decision": decision,
                # D-011 review: analysts need the transaction itself, not just features
                "transaction": {
                    "amount": txn.amount,
                    "merchant_id": txn.merchant_id,
                    "merchant_category": txn.merchant_category,
                    "country": txn.country,
                    "channel": txn.channel,
                },
                "alert_reason": "model_risk" if model_driven else "card_under_investigation",
                "fraud_type_prediction": "unscored_v0",  # typed prediction is a v1 model iteration
                "top_features": top,
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
        # C15 (D-049a): append-only audit trail — the label loop feeds model
        # reputation, so every disposition is attributable (Cycle 4 poisoning surface)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS disposition_audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT NOT NULL, disposition TEXT NOT NULL,
            analyst_id TEXT NOT NULL, prior_disposition TEXT,
            audited_at TEXT NOT NULL)""")

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

    def disposition(self, alert_id: str, label: str, analyst_id: str):
        if label not in self.DISPOSITIONS:
            raise ValueError(f"invalid disposition {label!r}; must be one of {sorted(self.DISPOSITIONS)}")
        if not analyst_id or not analyst_id.strip():
            raise PermissionError("disposition requires an analyst identity (role auth)")
        cur = self.conn.execute("SELECT disposition FROM alerts WHERE alert_id=?", (alert_id,))
        row = cur.fetchone()
        prior = row[0] if row else None
        self.conn.execute("UPDATE alerts SET disposition=? WHERE alert_id=?", (label, alert_id))
        self.conn.execute(
            "INSERT INTO disposition_audit (alert_id, disposition, analyst_id, "
            "prior_disposition, audited_at) VALUES (?,?,?,?,datetime('now'))",
            (alert_id, label, analyst_id.strip(), prior))
        self.conn.commit()

    def audit_trail(self, alert_id: str | None = None, limit: int = 100):
        q = "SELECT alert_id, disposition, analyst_id, prior_disposition, audited_at " \
            "FROM disposition_audit"
        args: tuple = ()
        if alert_id:
            q += " WHERE alert_id=?"
            args = (alert_id,)
        q += " ORDER BY seq DESC LIMIT ?"
        cur = self.conn.execute(q, args + (limit,))
        cols = ["alert_id", "disposition", "analyst_id", "prior_disposition", "audited_at"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


from pydantic import BaseModel, Field, field_validator


class Metrics:
    """C18: minimal in-process metrics — no external deps. Decision counts, alert-queue
    high-water, and a bounded latency window for percentiles."""

    def __init__(self, window: int = 5000):
        self.decisions: dict[str, int] = {"approve": 0, "soft_challenge": 0, "hard_block": 0}
        self.scored = 0
        self.errors = 0
        self._lat: list[float] = []
        self._window = window

    def record(self, decision: str, latency_ms: float):
        self.scored += 1
        self.decisions[decision] = self.decisions.get(decision, 0) + 1
        self._lat.append(latency_ms)
        if len(self._lat) > self._window:
            self._lat = self._lat[-self._window:]

    def snapshot(self, queue_depth: int) -> dict:
        lat = sorted(self._lat)
        def pct(p):
            if not lat:
                return 0.0
            return round(lat[min(len(lat) - 1, int(len(lat) * p))], 3)
        return {
            "scored_total": self.scored,
            "errors_total": self.errors,
            "decisions": dict(self.decisions),
            "latency_ms": {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99),
                           "window": len(lat)},
            "alert_queue_depth": queue_depth,
        }


class TxnIn(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=128)
    institution_id: str = "inst_001"
    timestamp: str
    card_id: str = Field(min_length=1, max_length=128)
    merchant_id: str
    merchant_category: str
    amount: float = Field(ge=0)                       # C18: amount can't be negative
    country: str = Field(min_length=1, max_length=8)
    device_id: str
    device_age_days: float = Field(ge=0)              # C18: age can't be negative
    channel: str
    session_behavior_score: float = Field(ge=0, le=1)  # C18: it's a [0,1] score

    @field_validator("timestamp")
    @classmethod
    def _valid_ts(cls, v):
        pd.Timestamp(v)   # raises if unparseable -> 422 rather than a 500 downstream
        return v


class _T:  # engine expects attribute access with a pandas Timestamp
    def __init__(self, m: TxnIn):
        self.__dict__.update(m.model_dump())
        self.timestamp = pd.Timestamp(m.timestamp)


def create_app():
    """FastAPI wrapper — the network-facing form of the engine."""
    import logging
    from fastapi import Body, FastAPI, HTTPException

    logging.basicConfig(level=cfg.log_level.upper(),
                        format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}')
    log = logging.getLogger("finguard")

    app = FastAPI(title="FinGuard scoring service")
    metrics = Metrics()
    # C18: graceful startup — a missing/corrupt model bundle becomes a 503-not-ready
    # service rather than an import-time crash.
    try:
        engine = ScoringEngine()
        model_ready = True
    except Exception as e:      # noqa: BLE001 - want any load failure to degrade gracefully
        engine = None
        model_ready = False
        log.error(f"model load failed: {e}")
    queue = AlertQueue()

    @app.get("/health")
    def health():
        return {"status": "ok"}                       # process is up

    @app.get("/ready")
    def ready():
        if not model_ready:
            raise HTTPException(503, "model not loaded")
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics_endpoint():
        return metrics.snapshot(len(queue.pending(10_000)))

    @app.post("/score")
    def score(txn: TxnIn = Body(...)):
        if not model_ready:
            metrics.errors += 1
            raise HTTPException(503, "model not loaded")
        result = engine.score(_T(txn))
        metrics.record(result["decision"], result.get("latency_ms", 0.0))
        if "alert" in result:
            queue.push(result["alert"])
        log.info(f'scored txn={txn.transaction_id} decision={result["decision"]}')
        return result

    @app.get("/dashboard")
    def dashboard():
        from fastapi.responses import FileResponse
        import os
        return FileResponse(os.path.join(os.path.dirname(__file__), "static", "dashboard.html"))

    @app.get("/alerts")
    def alerts(limit: int = 50):
        return queue.pending(limit)

    @app.get("/alerts/audit")
    def audit(alert_id: str | None = None, limit: int = 100):
        return queue.audit_trail(alert_id, limit)

    @app.post("/alerts/{alert_id}/disposition/{label}")
    def disposition(alert_id: str, label: str, analyst_id: str = ""):
        try:
            queue.disposition(alert_id, label, analyst_id)
        except PermissionError as e:
            raise HTTPException(401, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        hold_cleared = False
        a = queue.get(alert_id)
        if label == "confirmed_legitimate":
            if a and "card_id" in a:
                engine.clear_hold(a["institution_id"], a["card_id"])
                hold_cleared = True
        elif label.startswith("confirmed_fraud") and a and "card_id" in a:
            # C4 label loop: confirmed fraud feeds reputation features immediately
            engine.store.mark_confirmed_fraud(
                a["institution_id"], pd.Timestamp(a["timestamp"]),
                card_id=a["card_id"])
        return {"alert_id": alert_id, "disposition": label, "hold_cleared": hold_cleared}

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host=cfg.host, port=cfg.port, log_level=cfg.log_level)
