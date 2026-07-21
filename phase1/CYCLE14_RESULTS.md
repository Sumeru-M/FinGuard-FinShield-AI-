# Cycle 14 Results — Verification Control, P2P Friction, Federation Hardening
**To: Owner | Executed under D-040 → D-046 | Date: 2026-07-21**
Two parallel tracks (wire+P2P controls; federation hardening). Maker-checker review by
the Fraud Analyst agent caught one bug (fixed + rerun) and one new gap (owner item below).

## Track A — Wire verification-completion control (D-040/D-041)
Replaced the fixed 30-day cooling window with **release tied to callback-verification-
completion**: each beneficiary account gets an independent callback outcome (legit
confirms ~97%, fraud confirms ~5% — modeling occasional social-engineered callbacks);
an account stays capped at $50k cumulative (D-040) until it verifies. A patient attacker
can no longer outwait a clock — a fraud account never verifies.

| Metric | Cycle 13 (fixed window) | Cycle 14 (verification) |
|---|---|---|
| Recall by value | 99.3% | **99.5%** |
| Recall by count | 97.4% | 97.9% |
| bec_establish_slow_strike (frontier) | 68.75% | **81.25%** |
| False holds/day | 21.7 | **18.6** (verified legit accounts release) |
| Largest missed wire | $54.4k (slow-establishment) | $46.1k (**bec_evasive** — see gap) |

**The patience-bypass is closed** — the worst miss is no longer a slow-establishment
strike. Verified legit accounts now release, cutting false holds.

### ⚠ New gap the analyst surfaced (owner decision below)
Raising the cap to $50k (D-040) widened the free-pass window for **single-shot evasive
BEC**: `bec_evasive` is one wire at the real invoice amount (~$13k median, well under
$50k), so the cumulative cap never triggers and it rests entirely on the model. The
$46.1k largest miss is exactly this shape. The cap raise reduced legit friction as
intended but opened this seam — an honest trade the owner should rule on (option below).

## Track B — P2P friction policy (D-043)
Mandatory Confirmation-of-Payee + delayed settlement on first-time-recipient payments;
CoP abandonment at first contact collapses the whole installment scheme.
**Analyst caught a bug**: my first cut only credited CoP when *every* installment was
model-missed; CoP actually fires at the *first* contact. Fixed to gate on the
first-chronological payment — a ~6.5x larger eligible population.

| Metric | Model-only | + Friction (corrected) |
|---|---|---|
| Recall | 84.4% | **89.3%** (+4.9pt) |
| app_evasive (the undetectable cell) | 78.0% | **85.1%** (+7.1pt) |
| Fraud prevented by friction | — | 15 rows (was mis-measured as 2) |

**Cost, stated separately (analyst guidance):** 108.9 legit CoP prompts/day — a
*customer-facing one-tap* friction, NOT analyst-queue load (does not touch the D-023
100/day cap). CoP is reasonably targeted: 6.0% of first-time-recipient payments are
fraud vs 3.7% base rate. The compliance/liability rationale (UK-PSR-style CoP mandate)
justifies the policy independent of the measured lift.

## Track C — Federation hardening (Distributed Systems agent, D-046b)
New `finguard/federation_dp.py` closes the Cycle 6 tree-leakage caveat **structurally**:
institutions never exchange raw models — each shares only DP-noised predictions on a
shared synthetic probe set, and peers distill surrogate models from those. Measured
across the same 3 institutions:
- **Distillation alone** (leak closed, no noise) recovers most of Cycle 6's federated
  recall gain at comparable/better cost (large inst: 90.4% recall; mid: 93.8%/88.2%
  precision).
- **DP noise only pays in a narrow band (epsilon 20–50)**: output-level DP on a
  [0,1] probability has full-range sensitivity, so textbook epsilon≈1 swamps the
  thresholds (recall floods, precision collapses, cost 5–68x). Reported honestly as the
  transition, not a cherry-picked point.
Design doc `phase1/FEDERATION_ORCHESTRATION.md`: Ed25519 artifact signing, versioning,
weekly rounds, straggler handling, `artifact_kind` that structurally forbids raw_model.

## Needs-owner
1. **Wire single-shot BEC gap (new).** Accept the $50k-cap single-shot `bec_evasive`
   seam as residual risk (model-only defense on those), OR add a **per-wire floor** to
   the control (e.g. hold any unverified-beneficiary wire above $X regardless of
   cumulative) — closes the seam at the cost of more first-payment holds. Same
   cost/risk category as the D-040 cap decision.
2. **Federation aggregator operator** (from the design doc): consortium infra vs
   rotating institution vs third-party vendor — governance/cost, not engineering.
3. **DP epsilon is a per-round dial, not a lifetime budget** — a real deployment needs a
   formal privacy accountant before indefinite rounds. Flagged, not blocking.

## Backlog (analyst-flagged, non-blocking)
- ~3% of legit new suppliers never verify (0.97 prob) → permanently capped with no
  override path in code; add a manual-override/escalation path.
- `CONFIRM_PROB_FRAUD=0.05` and the $50k/45d params are owner-tunable knobs, named here.
- Federation probe-set representativeness needs a Data Science review before any real pilot.
