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
| D-016 | 2026-07-19 | Cycle 3 focus | Model quality: score calibration to revive soft-challenge tier + adversarial-robust features targeting evasive CNP (weakest cell, 76.2%) | Locked |
| D-017 | 2026-07-19 | P2P cost ratio | 10:1 FN:FP working placeholder for APP fraud (unrecoverable, no chargeback); re-derive with data | Locked |
| D-018 | 2026-07-19 | P2P delayed settlement | Autonomous, inside D-005 boundary: transaction-level and self-reversing (funds auto-release) | Locked |
| D-019 | 2026-07-19 | Mule detection | Deferred out of P2P v1 to its own AML-focused phase (regulatory adjacency); P2P v1 = APP-scam + ATO | Locked |
| D-020 | 2026-07-19 | Cycle 4 focus | Label-loop feedback (dispositions → device/card reputation features, 24h label latency) + investigator dashboard with dual lanes (model-driven vs card-under-investigation) | Locked |
| D-021 | 2026-07-19 | Cycle 5 focus | D-011 alert-format review executed in Fraud-Analyst role on the live dashboard + infra reality check (honest latency under load; Docker/Redis if environment allows) | Locked |
| D-022 | 2026-07-19 | Cycle 6 focus | Federation phase opens (D-012 fulfilled): multi-institution simulation, model-sharing (never data-sharing) via cross-institution ensemble, out-of-band aggregation per D-004 constraint | Locked |
| D-023 | 2026-07-19 | P2P alert lane | Separate P2P investigator lane, 100/day starting budget (APP-scam review is a different skill; no cross-channel starvation) | Locked |
| D-024 | 2026-07-19 | Recipient reputation | Approved in principle for P2P v1; GATED on data-minimization review before real data (D-009 pattern) | Locked |
| D-025 | 2026-07-19 | P2P Phase 1 kickoff | Vertical slice: P2P generator (APP-scam + ATO per D-019 scope), sender+recipient features, 10:1 cost model (D-017), delayed-settlement action (D-018), 100/day cap (D-023) | Locked |
| D-026 | 2026-07-19 | Cycle 8 focus | P2P red-team pass (evasive scam variants: installment coaching, aged mules, sleeper activation) + wire-transfer Phase 0 framing in parallel (docs only) | Locked |
| D-027 | 2026-07-19 | Wire cost model | Per-dollar expected-loss scoring (fixed review cost + amount-proportional loss terms → amount-dependent hold threshold) | Locked |
| D-028 | 2026-07-19 | Wire autonomy | Inverted rule: machine may HOLD any wire autonomously; human sign-off required to RELEASE a held wire above $100k | Locked |
| D-029 | 2026-07-19 | Wire v1 scope | Corporate-first (BEC/invoice manipulation + ATO wires); retail wire scams deferred (reuse P2P APP work later) | Locked |
| D-030 | 2026-07-19 | Wire AML boundary | Sanctions/AML screening OUT of scope — existing bank systems own it; this system consumes their verdict as an input feature only | Locked |
| D-031 | 2026-07-19 | Cycle 9 | Wire Phase 1 vertical slice approved (generator, BEC features, per-dollar thresholds, hold/release decisions) | Locked |
| D-032 | 2026-07-19 | Cycle 10 | Wire red-team: account-establishment BEC, fake-vendor onboarding, structuring ATO (sub-$100k sizing) + counter-features | Locked |
| D-033 | 2026-07-20 | Team structure v2 | 11 role subagents instantiated in `.claude/agents/` (charter in `_TEAM.md`); agents report to Team Lead session, Team Lead reports to owner; owner-gated decisions unchanged | Locked |
| D-034 | 2026-07-20 | Cycle 11 | Wire hardening v2 per analyst backlog: bigger eval cells, counter-feature window attacks, establishment test/strike split, email+behavior ablation, maker-checker review gate | Locked |
| D-035 | 2026-07-20 | Wire beneficiary control | APPROVED: mandatory cooling-off + cumulative-dollar cap on new beneficiary accounts until callback/CoP verification (closes establishment frontier; implementation next wire cycle) | Locked |
| D-036 | 2026-07-20 | Sub-$100k release policy | Dual-control release: second-analyst co-sign required to release any held wire (closes hostile-analyst poisoning path) | Locked |
| D-037 | 2026-07-20 | Sanctions feed auth | Spec now (Cybersecurity), build at real integration | Locked |
| D-038 | 2026-07-20 | Cycle 12 | Consolidation: shared core library, test suite from harness gates, README/architecture docs. Parallel agent work: Cybersecurity (D-037 spec), PM (docs) | Locked |
| D-039 | 2026-07-20 | Cycle 13 | Implement approved/correctness items: wire label-timing fix (F4), D-035 new-beneficiary cooling-off + cumulative cap, D-036 dual-control release accounting; maker-checker review gate | Locked |
| D-040 | 2026-07-20 | Wire control params | D-035 values set: $50k cumulative cap / 45-day cooling window (reduces legit-onboarding friction vs $25k/30d; median invoice ~$13k) | Locked |
| D-041 | 2026-07-20 | Verification-completion control | Pursue in Cycle 14: release tied to simulated callback-confirmation event (legit clears, fake vendor never does) instead of a fixed clock — closes slow-establishment frontier | Locked |
| D-042 | 2026-07-20 | Sanctions fail posture | Fail-closed, no exception: wires hold/block if the screening feed is unavailable (per D-037 spec default, D-030 boundary) | Locked |
| D-043 | 2026-07-20 | P2P friction policy | Approved for implementation: mandatory delayed-settlement + confirmation-of-payee prompts on first-time-recipient payments (mitigates undetectable installment-scam cell; D-018 permits) | Locked |
| D-044 | 2026-07-20 | AML audit retention | 5 years for sanctions verdicts + wire dispositions (AML/BSA horizon; exceeds 90-day security baseline D-008, compliance records only) | Locked |
| D-045 | 2026-07-20 | Sanctions vendor SLA | Published list-update SLA is a HARD vendor-selection criterion (needed to size verdict freshness/replay window) | Locked |
| D-046 | 2026-07-20 | Cycle 14 scope | Two tracks: (a) apply D-040 params + build D-041 verification control + implement D-043 P2P friction; (b) federation hardening (orchestration + DP/tree-leakage mitigation) | Locked |
| D-047 | 2026-07-21 | Wire per-wire floor | Any wire above $10k to an UNVERIFIED beneficiary is held regardless of cumulative — closes the single-shot BEC seam the D-040 cap raise opened | Locked |
| D-048 | 2026-07-21 | Federation aggregator | Third-party vendor operates the neutral round aggregator (stateless/replicated per design doc); consortium/rotating options rejected | Locked |
| D-049 | 2026-07-21 | Cycle 15 scope | Three tracks: (a) controls backlog — per-wire floor, never-verifying-supplier override path, disposition audit-trail + role auth; (b) federation DP privacy accountant; (c) card-channel red-team round 2 (reputation features + hold-state attacked with P2P/wire tradecraft) | Locked |
| D-050 | 2026-07-23 | Federation cadence + delta | Adopted by recommendation (owner-overridable, per efficiency directive): QUARTERLY federation rounds within lifetime eps_total=100, delta=1e-5 standard; RDP accounting deferred post-pilot | Locked |
| D-051 | 2026-07-23 | Scope freeze | Owner directive: NO cross-channel intelligence in pilot; stick to original goal statement; pilot = C16 (sleeper counter-feature) + C17 (final scorecard + close); PM strict on time/asset allocation, no redundant owner decisions | Locked |
