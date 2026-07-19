# Guardrails Checklist — Card Payments
**Roles: Product Manager (#11) + Cybersecurity Engineer (#6) | Phase 0, Deliverable 4**

## Compliance regime — working default
Given the stated intent for international applicability, this system is designed against the
**strictest common denominator** rather than a single jurisdiction, to avoid costly retrofits.

**Baseline standards adopted by default:**
- **PCI-DSS** — mandatory given the channel is card payments (governs storage, transmission,
  and processing of cardholder data specifically). Non-negotiable, not a "strictest common
  denominator" choice — this applies regardless of jurisdiction if card data is touched.
- **GDPR-grade privacy handling** — adopted as the default privacy bar (data minimization,
  purpose limitation, right to explanation for adverse automated decisions, defined retention
  limits) even outside the EU, since it is currently the strictest widely-applicable standard
  and building to it by default avoids under-building for stricter markets later.
- **Region-specific additions** (e.g. US FCRA adverse-action notice requirements, other local
  financial-privacy statutes) — **not pre-built**; added when a specific market launch requires
  them. Flagged explicitly so this isn't mistaken for full multi-jurisdiction legal coverage.

**Explicit limitation:** this is an engineering guardrail baseline, not legal sign-off. Actual
regulatory compliance requires legal/compliance review before any real customer data is
processed — this checklist reduces retrofit risk but does not substitute for that review.

## Data handling guardrails (binding on Data Engineer + Cybersecurity Engineer, Phase 1+)
- [ ] Cardholder data (PAN, CVV, full track data) never stored in plaintext; tokenization or
      encryption-at-rest required for anything beyond what's needed for real-time scoring
- [ ] Raw transaction data retained **13 months** (covers card-network chargeback/dispute
      windows, which run up to 120+ days — chargebacks are our fraud ground truth, so purging
      earlier would degrade label quality); behavioral/session data retained **90 days**;
      anonymized aggregates retained indefinitely for model training. Purpose-justified under
      the GDPR-grade baseline (fraud investigation + dispute resolution). Locked per D-008.
- [ ] No raw customer data crosses institutional boundaries — this is the guardrail that makes
      federated learning a requirement, not an option, for any multi-institution deployment
      (confirmed earlier: data topology is multi-institution, no raw sharing)
- [ ] Data minimization: only fields actually used by a scoring feature are retained; no
      speculative data collection "in case it's useful later"

## Explainability as compliance (not just UX)
- [ ] Every hard-block or account-impacting decision must have a retrievable explanation
      (satisfied by the `top_features` payload from deliverable 3) — this is treated as a
      compliance requirement, not optional, given the "right to explanation" adopted under the
      GDPR-grade baseline

## Bias / ethical guardrails
- [ ] Geolocation, device type, and behavioral-biometric features must be reviewed for proxy
      correlation with protected characteristics (income, disability, age) before model
      training — owned by AI/ML Engineer + Data Scientist at Phase 1 model-evaluation stage,
      flagged here so it's a checked step, not an afterthought
- [ ] No feature used in scoring may be a direct protected characteristic (race, religion,
      etc.); proxy-correlation review covers indirect cases

## Autonomy boundary (confirmed earlier, restated here as a binding guardrail)
- System **may** autonomously: soft-challenge (step-up auth), hard-block a specific transaction
- System **may not** autonomously: suspend or close an account, take any action beyond the
  single transaction under review, without human sign-off

## Resolved items (formerly open)
1. **Data retention (D-008):** 13 months transactions / 90 days behavioral / aggregates
   indefinite — see data handling guardrails above
2. **Legal/compliance review (D-009):** tracked as a **blocking gate on real-data ingestion
   only**. All Phase 1 work proceeds on synthetic/simulated data with no legal exposure; the
   gate trips at the moment real transaction data would enter the system.
