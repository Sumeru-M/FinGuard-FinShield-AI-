# Success Criteria — Card Payments
**Roles: Product Manager (#11) + Fraud Analyst (#10) | Phase 0, Deliverable 2**

## 1. Latency budget
**Target: 100ms p99, end-to-end**, measured from transaction-scoring-request received to
decision returned. (Locked earlier in framing discussion.)
- Sub-budget guidance for Phase 1 architecture: reserve headroom for network/serialization
  overhead — treat ~70-80ms as the actual compute budget for feature retrieval + model
  inference + decision logic, not the full 100ms.
- Anything requiring heavier computation (e.g. graph traversal, cross-institution federated
  signal aggregation) must be pre-computed/cached asynchronously, not done in the synchronous
  scoring path.

## 2. Cost ratio (false positive vs. false negative)
**Working default: cost(false negative) = 5x cost(false positive).**
Rationale: at launch, with no historical loss data, card-issuer industry norms typically treat
undetected fraud loss as materially more costly than an isolated false decline (a false decline
is recoverable friction — retry, alternate payment method — whereas fraud loss is not
recoverable). This ratio is a **starting assumption**, explicitly meant to be revised once
real or simulated transaction/loss data exists in Phase 1.
- This ratio directly sets the decision threshold: AI/ML Engineer tunes the model's operating
  point so that, at the chosen threshold, the expected cost (FN_rate x 5 + FP_rate x 1) is
  minimized against realistic fraud/legitimate-transaction base rates.
- **Revisit trigger:** re-derive this ratio from real data no later than the first Phase 1
  model evaluation cycle — do not let this placeholder persist past initial calibration.

## 3. Alert volume / investigator capacity
**Resolved (D-007): ~200 alerts/day cap for v1 threshold tuning**, assuming a small review
team (1–3 reviewers) at launch. This cap interacts with the cost ratio: if 5:1 tuning produces
more than ~200 alerts/day on realistic volumes, the alert cap wins and the effective threshold
tightens. The cap is relaxed as the review team scales — it is a launch constraint, not a
permanent ceiling.

## 4. Explainability bar
See `03_explainability_spec.md` — resolved separately, feeds this criteria set.

## Summary table

| Metric | Value | Status |
|---|---|---|
| Latency (p99) | 100ms end-to-end | Locked (D-004) |
| Cost ratio (FN:FP) | 5:1 | Locked (D-010) — re-derive at first model eval cycle |
| Alert volume ceiling | ~200/day | Locked (D-007) — relaxes as review team scales |
| Explainability format | Top-features attribution | Locked (D-011) — analyst review before freeze |
