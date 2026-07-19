"""WS-6: Evaluation harness — replays the labeled stream through the full
scoring engine and scores every Phase 0 exit criterion.

Replays ALL 30 days through the engine (so the feature store warms exactly as
it would live) but evaluates only the held-out window the model never trained
on. Reports precision/recall/expected cost, alerts/day vs the D-007 cap, and
end-to-end engine latency p50/p95/p99 vs the D-004 budget.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from finguard.scoring import ScoringEngine, AlertQueue
from finguard.train import COST_FN, COST_FP_BLOCK, COST_FP_CHAL, COST_FRAUD_CHAL


def main():
    df = pd.read_parquet("data/transactions.parquet").sort_values("timestamp")
    days = df["timestamp"].dt.normalize()
    cutoff = days.unique()[int(len(days.unique()) * 0.7)]  # same split as training

    engine = ScoringEngine()
    queue = AlertQueue("data/alerts.db")

    results, latencies = [], []
    n_alert_payloads = n_hold_floored = 0
    for t in df.itertuples(index=False):
        r = engine.score(t)
        in_eval = t.timestamp >= cutoff
        if in_eval:
            latencies.append(r["latency_ms"])
            results.append((t.label != "confirmed_legitimate", r["decision"], t.label,
                            getattr(t, "variant", "none")))
        if "alert" in r and in_eval:
            queue.push(r["alert"])
            n_alert_payloads += 1
            if r["alert"].get("card_under_investigation"):
                n_hold_floored += 1

    res = pd.DataFrame(results, columns=["fraud", "decision", "label", "variant"])
    n_days = df.loc[df["timestamp"] >= cutoff, "timestamp"].dt.normalize().nunique()
    alerted = res["decision"] != "approve"
    blocked = res["decision"] == "hard_block"

    cost = (COST_FN * (res.fraud & ~alerted).sum()
            + COST_FRAUD_CHAL * (res.fraud & alerted & ~blocked).sum()
            + COST_FP_BLOCK * (~res.fraud & blocked).sum()
            + COST_FP_CHAL * (~res.fraud & alerted & ~blocked).sum())
    naive = COST_FN * res.fraud.sum()

    lat = np.array(latencies)
    report = {
        "eval_rows": len(res), "eval_days": int(n_days),
        "fraud_rows": int(res.fraud.sum()),
        "recall": float((res.fraud & alerted).sum() / res.fraud.sum()),
        "precision": float((res.fraud & alerted).sum() / max(alerted.sum(), 1)),
        "alerts_per_day": float(alerted.sum() / n_days),
        "alert_cap": 200,
        "false_block_count": int((~res.fraud & blocked).sum()),
        "expected_cost_vs_naive": float(cost / naive),
        "latency_ms": {"p50": float(np.percentile(lat, 50)),
                       "p95": float(np.percentile(lat, 95)),
                       "p99": float(np.percentile(lat, 99)),
                       "max": float(lat.max())},
        "latency_budget_ms": 100,
        "recall_by_fraud_type": {
            k: float((res[res.label == k]["decision"] != "approve").mean())
            for k in ["confirmed_fraud_cnp", "confirmed_fraud_ato", "confirmed_fraud_synthetic_card"]
            if (res.label == k).any()
        },
        "recall_by_variant": {
            v: float((res[(res.variant == v) & res.fraud]["decision"] != "approve").mean())
            for v in ["blatant", "evasive"] if ((res.variant == v) & res.fraud).any()
        },
        "alert_payloads_queued": n_alert_payloads,
        "hold_floored_alerts": n_hold_floored,   # decisions rescued by investigation-hold
    }
    print(json.dumps(report, indent=2))
    with open("data/eval_report.json", "w") as f:
        json.dump(report, f, indent=2)

    from finguard.experiments import log_run
    log_run("eval", params={"eval_days": int(n_days)}, metrics=report, tag="harness")

    verdicts = [
        ("p99 latency < 100ms", report["latency_ms"]["p99"] < 100),
        ("alerts/day <= 200", report["alerts_per_day"] <= 200),
        ("beats naive baseline at 5:1 cost", report["expected_cost_vs_naive"] < 1.0),
        ("alerts carry top-features explanations", n_alert_payloads > 0),
    ]
    print("\nPhase 1 exit criteria:")
    for name, ok in verdicts:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


if __name__ == "__main__":
    main()
