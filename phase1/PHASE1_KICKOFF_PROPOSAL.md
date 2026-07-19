# Phase 1 Kickoff Proposal — Card Payments (Single-Institution Pilot)
**Status: PROPOSAL — awaiting owner approval. No code written yet.**
Binding constraints inherited from Phase 0: see `../phase0/00_decisions_log.md` (D-001 → D-013).

## Objective of Phase 1
A working end-to-end vertical slice: synthetic card transactions stream in → real-time scoring
service returns approve / soft_challenge / hard_block in <100ms p99 → explainable alerts land
in an investigator queue. Single simulated institution, synthetic data only (D-009, D-012),
federated-ready boundaries by design.

## Workstreams and owners

### WS-1: Synthetic data generation (Data Scientist #2 + Fraud Analyst #10)
The foundation everything else trains and tests against.
- Generator producing realistic card-transaction streams: legitimate behavior profiles
  (recurring merchants, spend ranges, geo patterns, device consistency) plus injected fraud
  scenarios matching the Phase 0 taxonomy — CNP stolen-credential, ATO-driven, BIN-attack/
  card-testing patterns
- Labels emitted per D-013 labeling standard (`confirmed_fraud_cnp`, etc.)
- Tunable fraud prevalence (real-world base rate ~0.1–0.3% of transactions) so threshold
  tuning against the 5:1 cost ratio (D-010) and 200 alerts/day cap (D-007) is meaningful
- **Recommended stack:** Python; deterministic seeds for reproducible evaluation

### WS-2: Streaming ingestion pipeline (Data Engineer #3)
- Kafka (or Redpanda locally — Kafka-API-compatible, lighter for a pilot) as the transaction
  bus; topic design keeps institution-scoping explicit from day one (federated-ready per D-012)
- Stream consumer computing/updating real-time features into a low-latency feature store
  (Redis for the pilot) — velocity counters, per-card/per-device rolling aggregates
- **Key design rule from Phase 0:** anything expensive is computed here, asynchronously, ahead
  of scoring time — the scoring path only *reads* precomputed features (D-004: ~70–80ms
  compute budget)

### WS-3: Scoring service (Backend #4 + Distributed Systems #5)
- Low-latency API: transaction in → feature lookup (Redis) → model inference → decision out
- Decision logic implements the autonomy boundary (D-005): emits approve / soft_challenge /
  hard_block only; account-level actions are structurally impossible from this service
- p99 latency instrumented from the first commit — latency is a launch gate, not a
  post-hoc optimization
- **Recommended stack:** Python + FastAPI for the pilot (fastest iteration alongside the ML
  stack; a Go/Rust rewrite is a later scale decision, not a pilot decision)

### WS-4: Fraud model v0 (AI/ML Engineer #1 + Data Scientist #2)
- **Model family recommendation: gradient-boosted trees (XGBoost/LightGBM).** Reasoning
  against Phase 0 constraints: attribution-cheap (SHAP TreeExplainer satisfies D-011 within
  latency budget), strong tabular-data performance, threshold-tunable against the asymmetric
  5:1 cost function, well-understood failure modes. Deep/graph models are deliberately
  deferred — they'd need the D-011 latency-attribution flag raised first.
- Threshold tuned to minimize expected cost at 5:1, subject to the ≤200 alerts/day cap
- Bias/proxy-correlation review (guardrails checklist) runs at first evaluation cycle
- Two thresholds, not one: score ≥ T_block → hard_block; T_challenge ≤ score < T_block →
  soft_challenge — matching the graduated autonomy model

### WS-5: Alert generation + investigator queue (Platform #9 + Fraud Analyst #10)
- Alert payload exactly per the D-011 JSON spec (top 3–7 human-readable features)
- Minimal investigator view for the pilot: alert list + detail view + disposition action
  (confirm fraud / mark legitimate / unresolved) feeding labels back per the labeling standard
- First prototype output reviewed in the Fraud Analyst role before format freeze (D-011 trigger)

### WS-6: Evaluation harness (MLOps #7 + Data Scientist #2)
- Replay harness: run a labeled synthetic stream through the full pipeline, measure
  precision/recall/cost at threshold, alert volume/day, latency p50/p95/p99
- This is the scoreboard for every Phase 0 success criterion — built early so every
  model/threshold change is measured, not eyeballed

### Deferred within Phase 1 (explicitly not in this slice)
- Kubernetes/cloud deploy (Cloud/DevOps #8) — pilot runs locally via docker-compose;
  infra work begins when the slice works
- Device fingerprinting / behavioral biometrics capture (Cybersecurity #6) — pilot uses
  synthetic device/geo fields; real capture SDK is a later workstream
- Federation layer — per D-012, own phase after the core model works

## Build order (dependency-driven)
1. **WS-1 synthetic data** — everything depends on it
2. **WS-2 pipeline + WS-6 harness skeleton** — in parallel
3. **WS-4 model v0** — trains on WS-1 output, features from WS-2
4. **WS-3 scoring service** — wires WS-2 features + WS-4 model, latency-tested
5. **WS-5 alerts + queue** — consumes WS-3 decisions
6. **End-to-end evaluation** against all Phase 0 criteria → results reported to owner

## Phase 1 exit criteria (what "done" means)
- [ ] End-to-end slice runs: synthetic stream → decision → alert, locally reproducible
- [ ] p99 latency < 100ms demonstrated under realistic throughput
- [ ] Model beats a naive baseline at 5:1 cost with ≤200 alerts/day at pilot volume
- [ ] Every alert carries a compliant top-features explanation
- [ ] Bias/proxy review completed and reported
- [ ] Cost ratio re-derivation memo delivered (D-010 revisit trigger)
- [ ] Fraud Analyst review of alert format completed (D-011 revisit trigger)

## Decision requested from owner
Approve this Phase 1 plan (workstreams, stack recommendations, build order) — or flag
overrides. On approval, execution starts with WS-1 (synthetic data generator).
