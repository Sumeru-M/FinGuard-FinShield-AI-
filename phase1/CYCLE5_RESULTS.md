# Cycle 5 Results — D-011 Format Review + Infra Reality Check
**To: Owner | Executed under D-021 | Date: 2026-07-19**

## C5-1: D-011 alert-format review (Fraud Analyst role) — FORMAT NOW FROZEN
Reviewed live payloads and the dashboard in-role. Four findings, all fixed and verified
in the browser; the spec amendment is recorded in `phase0/03_explainability_spec.md`:

1. **Missing transaction context (blocker):** alerts showed features but never the
   transaction itself. Added a `transaction` block (amount, merchant, category, country,
   channel) to the payload and a context line on every dashboard card.
2. **Hold-floored alerts were misleading:** a 0.0002-risk `soft_challenge` looked like a
   contradiction, and its SHAP list explained "why this is NOT fraud." Added
   `alert_reason` (`model_risk` vs `card_under_investigation`); hold-floored alerts now
   show an explicit warning line and omit attributions. Dashboard lanes now split on
   `alert_reason`, so a model-driven alert on an already-held card still gets full review.
3. **`confidence` field removed** — its |risk−0.5|·2 semantics read as "99.96% confident"
   on a low-risk hold alert. Actively harmful; deleted from the payload.
4. **Units added** — day-denominated features render as "2.3 days", money as "$32.67".

## C5-2: Infra reality check — honest latency under concurrent load
Docker daemon remains unavailable on this machine (Kafka/Redis containers still deferred;
the feature-store interface remains swap-ready). What could be measured honestly was:
the real HTTP service under concurrency — 8 parallel clients, 2,000 varied scoring
requests against a single uvicorn process:

| Measure | Result |
|---|---|
| Throughput | **~1,986 req/s** (single Python process) |
| HTTP p50 / p95 / p99 | 3.5ms / 5.4ms / **8.1ms** |
| Max latency | 18.9ms |
| Errors | 0 / 2000 |
| Budget (D-004) | 100ms p99 → **12x headroom** |

Backend/DistSys assessment: the earlier 0.4ms in-process figure was indeed flattering —
the honest network-path p99 is ~8ms under load. Still comfortably inside budget with
room for a real feature-store network hop (~1–2ms Redis RTT) and TLS. Single-process
throughput (~2k rps) is the first real ceiling; horizontal replicas behind a load
balancer is the standard answer and needs no redesign.

## Status of deferred infra
Kafka/Redis/Docker remain blocked by environment, not by design. When a Docker daemon is
available, the swap is: RedisFeatureStore implementing the existing store interface +
Redpanda topic per institution. No code above the store interface changes.

## Cycle 5 exit state
- D-011 revisit trigger: **CLOSED** (format frozen post-analyst-review)
- All Phase 0 gates re-verified this cycle (harness re-run after payload changes)
- Remaining owner-gated items: P2P open questions (alert lane, recipient reputation);
  federation layer timing; real-data legal gate (D-009) untouched as designed
