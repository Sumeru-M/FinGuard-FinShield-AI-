# Decisions Log — FinGuard / FraudShield AI
Single source of truth for decisions made by the project owner (sole decision maker).
Every entry is binding on all roles until explicitly revised by the owner.

| # | Date | Decision | Detail | Status |
|---|---|---|---|---|
| D-001 | 2026-07-18 | Team structure | 11 distinct roles, PM as single funnel, owner as sole approver | Locked |
| D-002 | 2026-07-18 | Phase gating model | Per-channel Phase 0 → Phase 1; card payments leads, P2P and wire run their own Phase 0 independently and in parallel | Locked |
| D-003 | 2026-07-18 | Channel sequence | Card payments → P2P transfers → wire/bank transfers | Locked |
| D-004 | 2026-07-18 | Latency budget | 100ms p99 end-to-end (~70–80ms compute budget) | Locked |
| D-005 | 2026-07-18 | Autonomy boundary | System may soft-challenge and hard-block a transaction autonomously; no account-level action without a human | Locked |
| D-006 | 2026-07-18 | Data topology | Multi-institution, no raw data sharing → federated learning is a confirmed requirement (see D-012 for v1 scoping) | Locked |
| D-007 | 2026-07-18 | Alert capacity | ~200 alerts/day cap for v1 threshold tuning (assumes 1–3 reviewers) | Locked |
| D-008 | 2026-07-18 | Data retention | 13 months raw transaction records; 90 days behavioral/session data; anonymized aggregates indefinite | Locked |
| D-009 | 2026-07-18 | Legal/compliance review | Blocking gate on real-data ingestion only; Phase 1 proceeds on synthetic data | Locked |
| D-010 | 2026-07-18 | Cost ratio | 5:1 (FN:FP) placeholder; re-derive at first model evaluation cycle | Locked (revisit trigger set) |
| D-011 | 2026-07-18 | Explainability | Top-contributing-features (SHAP-style) format; Fraud Analyst reviews first prototype output before freeze | Locked (revisit trigger set) |
| D-012 | 2026-07-18 | Federated learning v1 scope | v1 = single-institution pilot on synthetic data, federated-ready by design; federation layer is its own later phase | Locked |
| D-013 | 2026-07-18 | Phase 0 (card payments) | **CLOSED** — all exit criteria met; Phase 1 (card payments) unblocked | Locked |
| D-014 | 2026-07-18 | Phase 1 kickoff | Approved as proposed: 6 workstreams, GBT model family, Python/FastAPI/Redis/Kafka pilot stack, dependency-driven build order starting WS-1 | Locked |
| D-015 | 2026-07-19 | Cycle 2 direction | "Red team then harden": adversarial data v2, honest retrain, investigation-hold state, experiment tracking. Dashboard/infra/federation wait one cycle. P2P Phase 0 framing runs in parallel | Locked |
