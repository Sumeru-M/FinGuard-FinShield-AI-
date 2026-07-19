# Phase 0 — Framing & Guardrails: Card Payments
**Role: Product Manager (#11) | Status: PROPOSAL — awaiting your approval, nothing below is executed yet**

## Purpose
Lock the framing, success criteria, and guardrails for the **card-payments channel only**.
Completion of this phase is the sole gate for starting Phase 1 (technical build) on card
payments. P2P and wire transfer channels run their own Phase 0 independently and do not block
or get blocked by this one.

## Scope for this phase
- Channel: card payments (CNP and POS), real-time authorization-time scoring
- Out of scope here: P2P, wire/bank transfers, synthetic identity (long-horizon, non-transactional),
  money-laundering/mule network detection — each deferred to its own framing pass, not dropped
- Fraud types in scope for card payments: stolen-credential / CNP fraud, account-takeover-driven
  card fraud (session/device compromise leading to a fraudulent card transaction)

## Deliverables of Phase 0 (card payments)
1. **Fraud-type definition doc** — precise, testable definitions of what counts as fraud for
   this channel (feeds labeling standards for Fraud Analyst and model training later)
2. **Success criteria spec** — the three open items below, resolved to concrete numbers/formats
3. **Guardrail spec** — compliance regime decision + explainability/autonomy rules formalized
4. **Phase 1 entry checklist** — a short, explicit list Phase 1 roles check against before they start

## The three open items — how each gets resolved

### 1. Cost ratio (false positive vs. false negative)
**Owners:** PM (#11) + Fraud Analyst (#10)
**Method:** Since no historical loss data exists yet (greenfield), this is set as an *initial
working assumption* rather than derived from data — to be revisited once real/simulated data
exists in Phase 1.
**Proposed working default:** favor recall moderately over precision at launch (card issuers
typically weight fraud loss higher than isolated false declines, since a single false decline
is recoverable friction but fraud loss is not) — subject to your override.
**Deliverable:** a stated ratio or weighted cost formula (e.g. cost(FN) = 5x cost(FP)) that
AI/ML Engineer uses to tune the decision threshold in Phase 1.

### 2. Explainability format
**Owners:** AI/ML Engineer (#1) + Platform Engineer (#9) + Fraud Analyst (#10)
**Method:** Fraud Analyst defines what's actually usable in-workflow (this is a domain-expert
call, not an engineering preference); AI/ML confirms it's producible from the model families
under consideration; Platform confirms it's renderable in the investigator dashboard.
**Proposed working default:** top-contributing-features format (e.g. SHAP-style) as the
baseline — most broadly compatible with model choices and fastest to implement — with natural-
language rationale layered on top in a later iteration if investigators need it.
**Deliverable:** a short spec of the alert payload shape (fields, format, example).

### 3. Compliance regime
**Owners:** PM (#11), informed by Cybersecurity Engineer (#6)
**Method:** Given international applicability is the intent, default to designing against the
**strictest common denominator** across likely jurisdictions rather than picking one region —
this avoids costly retrofits later.
**Proposed working default:** treat data handling as GDPR-grade (strict privacy, data
minimization, right-to-explanation) by default, plus PCI-DSS for card data specifically since
the channel is card payments. Region-specific carve-outs (e.g. US FCRA adverse-action notices)
added as encountered rather than pre-built for every jurisdiction.
**Deliverable:** a guardrails checklist Data Engineer and Cybersecurity build against.

*(All three defaults above are proposals for your approval, not decisions — flag any you want
changed before this phase is marked complete.)*

## Sequencing within Phase 0 (card payments)
1. Fraud-type definitions + success criteria drafted (PM + Fraud Analyst) — **~first**
2. Explainability format spec drafted (AI/ML + Platform + Fraud Analyst) — parallel to step 1
3. Compliance/guardrails checklist drafted (PM + Cybersecurity) — parallel to step 1
4. All three reviewed together for internal consistency (e.g. does the compliance checklist
   conflict with the explainability format?) — PM synthesizes
5. Presented to you as a single consolidated Phase 0 sign-off package

## Exit criteria — what unlocks Phase 1 (card payments)
Phase 0 is complete, and Phase 1 (card payments) may begin, when you have approved:
- [ ] Fraud-type definitions for card payments
- [ ] Cost ratio / threshold-tuning target
- [ ] Explainability payload spec
- [ ] Compliance/guardrails checklist
- [ ] Confirmation that federated learning is required for this channel given the multi-
      institution, no-raw-data-sharing constraint (already validated in principle — this just
      confirms it applies to card payments specifically, since a single-institution v1 pilot
      is also a valid option if you want to defer the federated complexity for the first slice)

## What happens after approval
Once this Phase 0 package is approved, the next proposal will be a **Phase 1 technical kickoff
plan for card payments** — architecture options for the scoring pipeline, data engineer's
ingestion approach, and the AI/ML Engineer's model-family recommendation given the explainability
and latency constraints locked here. That will be a separate proposal, not started until this
one is approved.
