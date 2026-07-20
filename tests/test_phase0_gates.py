"""C12-2: Phase 0 exit gates as regression tests against the published eval artifacts.
These fail if a future change regresses a locked gate without re-earning it."""

import json
import os

import pytest


def _load(path):
    if not os.path.exists(path):
        pytest.skip(f"{path} not built (run that channel's pipeline first)")
    with open(path) as f:
        return json.load(f)


def test_cards_gates():
    r = _load("data/eval_report.json")
    assert r["latency_ms"]["p99"] < r["latency_budget_ms"]      # D-004
    assert r["alerts_per_day"] <= r["alert_cap"]                # D-007
    assert r["expected_cost_vs_naive"] < 1.0                    # D-010 beats naive
    assert r["alert_payloads_queued"] > 0                       # D-011 explanations exist


def test_p2p_gates():
    r = _load("data/p2p_report.json")
    assert r["alerts_per_day"] <= r["alert_cap"]                # D-023 separate lane
    assert r["cost_vs_naive"] < 1.0                             # D-017 beats naive
    assert r["hold_tier_used"] is True                          # D-018 tier alive


def test_wire_gates():
    r = _load("data/wire_report.json")
    assert r["expected_loss_vs_naive"] < 1.0                    # D-027 beats naive
    assert r["recall_by_value"] >= r["recall_by_count"] - 0.02  # per-dollar posture:
    # value recall must not lag count recall (misses concentrate in SMALL wires)
    assert r["largest_missed_wire"] < 100_000                   # no big wire escapes
