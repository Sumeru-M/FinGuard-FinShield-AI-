# Phase 1 Entry Checklist — Card Payments
**Role: Product Manager (#11), synthesizing all Phase 0 deliverables | Phase 0, Deliverable 5**

## Status of each exit criterion

- [x] **Fraud-type definitions** — complete, see `01_fraud_type_definitions.md`
- [x] **Cost ratio / threshold-tuning target** — working default set (5:1 FN:FP), see
      `02_success_criteria.md`; alert-volume ceiling still open
- [x] **Explainability payload spec** — working default set (top-features format), see
      `03_explainability_spec.md`
- [x] **Compliance/guardrails checklist** — working defaults set (PCI-DSS + GDPR-grade
      baseline), see `04_guardrails_checklist.md`
- [x] **Federated learning requirement confirmed** — multi-institution, no-raw-data-sharing
      topology confirmed earlier, so federated learning is validated as a real Phase 1+
      architectural requirement for this channel (not deferred as optional)

## Formerly open items — all resolved and approved (2026-07-18)
1. **Alert volume (D-007):** ~200 alerts/day cap for v1 threshold tuning
2. **Data retention (D-008):** 13 months transactions / 90 days behavioral / aggregates indefinite
3. **Legal/compliance review (D-009):** blocking gate on real-data ingestion only; Phase 1
   proceeds on synthetic data
4. **Cost ratio (D-010):** 5:1 accepted as placeholder, re-derived at first model eval cycle
5. **Explainability (D-011):** top-features format accepted; analyst review before freeze
6. **Federated learning v1 scope (D-012):** single-institution pilot on synthetic data,
   federated-ready by design; federation layer is its own later phase

**PHASE 0 (CARD PAYMENTS) IS CLOSED (D-013). PHASE 1 (CARD PAYMENTS) IS UNBLOCKED.**
See `00_decisions_log.md` for the full binding decision record.

## Consistency check across deliverables
- Explainability format (feature-attribution) is compatible with the compliance guardrail
  requiring retrievable explanations for hard-block decisions — no conflict
- Cost ratio (5:1) and latency budget (100ms) together constrain AI/ML Engineer's model-family
  choice in Phase 1: needs to be a model that supports fast attribution *and* can be threshold-
  tuned against an asymmetric cost function — noted as a Phase 1 kickoff input
- Federated learning requirement and 100ms latency budget together mean cross-institution
  signal aggregation cannot happen synchronously in the scoring path — federated model updates
  happen out-of-band (periodic retraining/aggregation), not per-transaction, which keeps the
  two requirements compatible rather than in tension

## Recommendation
Card-payments Phase 0 is substantively complete on the framing/guardrails front. The three
remaining open items (alert volume, retention period, legal review ownership) are narrow and
don't require re-opening the broader framing work — they can be answered directly and folded
in without redoing the deliverables above.

**Proposed next step (not yet started):** once you confirm or override the working defaults
above and answer the three open items, the next proposal will be the Phase 1 technical kickoff
for card payments — architecture options, Data Engineer's ingestion approach, and AI/ML
Engineer's model-family recommendation.
