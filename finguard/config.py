"""Cycle 18 (D-052): single source of operational configuration.

Every operational knob that was previously hardcoded across modules lives here, each
overridable by environment variable at deploy time. Defaults preserve the exact
pilot behavior (config refactor must be byte-identical — no model-behavior change).

Secrets policy: NO secret is ever hardcoded here or committed. Secret-bearing values
(DB URLs with credentials, API keys, feed tokens) are read from the environment ONLY,
default to None, and the deploy environment injects them. This module holds operational
parameters, not secrets.

Read the env ONCE at import (cheap, values are process-lifetime). Tests that need a
different value set the env var and call reload().
"""

from __future__ import annotations

import os


def _f(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v is not None and v.strip() != "" else default


def _i(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v is not None and v.strip() != "" else default


def _s(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v.strip() != "" else default


def _opt(name: str):
    """Secret/optional value: env-only, None if unset. Never has a hardcoded default."""
    v = os.environ.get(name)
    return v if v is not None and v.strip() != "" else None


class Config:
    """Namespaced, env-overridable operational config. All FINGUARD_-prefixed."""

    def __init__(self):
        # --- Service ---
        self.host = _s("FINGUARD_HOST", "127.0.0.1")
        self.port = _i("FINGUARD_PORT", 8100)
        self.log_level = _s("FINGUARD_LOG_LEVEL", "warning")
        self.model_path = _s("FINGUARD_MODEL_PATH", "data/model_v0.pkl")
        self.alerts_db = _s("FINGUARD_ALERTS_DB", "data/alerts.db")

        # --- Scoring engine (cards) ---
        self.hold_ttl_hours = _f("FINGUARD_HOLD_TTL_HOURS", 48.0)
        # C19: feature-store backend — "memory" (default, pilot) or "redis" (production).
        # redis is used only when backend=redis AND redis_url is set.
        self.feature_store = _s("FINGUARD_FEATURE_STORE", "memory")
        self.behavioral_retention_days = _i("FINGUARD_BEHAVIORAL_RETENTION_DAYS", 90)  # D-008

        # --- Card cost model (D-010: 5:1 FN:FP) ---
        self.card_cost_fn = _f("FINGUARD_CARD_COST_FN", 5.0)
        self.card_cost_fp_block = _f("FINGUARD_CARD_COST_FP_BLOCK", 1.0)
        self.card_cost_fp_chal = _f("FINGUARD_CARD_COST_FP_CHAL", 0.3)
        self.card_cost_fraud_chal = _f("FINGUARD_CARD_COST_FRAUD_CHAL", 1.0)
        self.card_alert_cap = _i("FINGUARD_CARD_ALERT_CAP", 200)

        # --- P2P cost model (D-017: 10:1) + friction (D-043) ---
        self.p2p_cost_fn = _f("FINGUARD_P2P_COST_FN", 10.0)
        self.p2p_cost_fraud_hold = _f("FINGUARD_P2P_COST_FRAUD_HOLD", 1.0)
        self.p2p_cost_fp_block = _f("FINGUARD_P2P_COST_FP_BLOCK", 1.0)
        self.p2p_cost_fp_hold = _f("FINGUARD_P2P_COST_FP_HOLD", 0.2)
        self.p2p_alert_cap = _i("FINGUARD_P2P_ALERT_CAP", 100)
        self.p2p_cop_abandon_app = _f("FINGUARD_P2P_COP_ABANDON_APP", 0.40)
        self.p2p_settlement_recall = _f("FINGUARD_P2P_SETTLEMENT_RECALL", 0.30)

        # --- Wire cost model (D-027 per-dollar) + controls (D-040/041/047) ---
        self.wire_r_frac = _f("FINGUARD_WIRE_R_FRAC", 0.10)
        self.wire_d_frac = _f("FINGUARD_WIRE_D_FRAC", 0.002)
        self.wire_review_cost = _f("FINGUARD_WIRE_REVIEW_COST", 50.0)
        self.wire_human_release_above = _f("FINGUARD_WIRE_HUMAN_RELEASE_ABOVE", 100_000.0)
        self.wire_new_beneficiary_cap = _f("FINGUARD_WIRE_NEW_BENEFICIARY_CAP", 50_000.0)
        self.wire_per_wire_floor = _f("FINGUARD_WIRE_PER_WIRE_FLOOR", 10_000.0)

        # --- Secrets (env-only, None until deploy injects them) ---
        self.redis_url = _opt("FINGUARD_REDIS_URL")          # C19
        self.kafka_brokers = _opt("FINGUARD_KAFKA_BROKERS")  # C19
        self.sanctions_feed_token = _opt("FINGUARD_SANCTIONS_FEED_TOKEN")  # D-037


# Process-lifetime singleton; reload() lets tests re-read env.
cfg = Config()


def reload() -> Config:
    global cfg
    cfg = Config()
    return cfg
