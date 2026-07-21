# Cycle 13 Results — Wire Label-Timing Fix + Approved Controls
**To: Owner | Executed under D-039 | Date: 2026-07-20**
**Review gate:** Fraud Analyst agent (7 findings); two report-accuracy fixes applied
before publish, larger findings carried as caveats + owner items below.

## What was implemented (all already-approved or correctness — no new decisions taken)
1. **F4 label-timing fix.** Training positives now require `discovered_at < cutoff` —
   a fraud row is a training label only once it would actually have been discovered
   (ordinary fraud: +5 days; establishment *test* payments: inherit their *strike's*
   discovery time). Never touches features or test-set ground truth.
2. **D-035 control.** New/changed beneficiary accounts are capped at $25k cumulative
   within a 30-day cooling window, held pending callback/CoP verification.
3. **D-036 accounting.** Held wires ≤$100k route to a dual-control queue (second-analyst
   co-sign); >$100k to the human-release queue (D-028).

## Honest results (39-day window, 233 fraud wires, $15.0M)

| Metric | Cycle 11 | Cycle 13 |
|---|---|---|
| Recall by value | 99.8% | 99.3% |
| Recall by count | 98.7% | 97.4% (model-only 97.0%) |
| **bec_establish_strike** | 100% (leak-inflated) | **97.3% (F4-honest)** |
| **bec_establish_slow_strike** (frontier) | 81.3% (leak-inflated) | **68.75% (F4-honest)** |
| Precision | 20.0% | 21.2% |
| False holds/day | 23.6 | 21.7 |
| Expected loss vs naive | 0.110 | 0.114 |
| Largest missed wire | $6.2k | **$54.4k** (a bec_establish_slow_strike) |

**F4 did what it was built to do:** 422 raw train-fraud rows → 287 labeled positives
(135 undiscovered-at-cutoff rows correctly train as unlabeled), and the two establishment
strike cells dropped to their *honest* values. These numbers are lower and more
trustworthy — the prior cells were inflated by the label leak F4 removed.

## The load-bearing finding (analyst-flagged, reported honestly, NOT smoothed)
**The 30-day fixed cooling window is under-sized against the very attack it targets.**
The slow-establishment strike lands ~25–40 days after account creation; roughly half of
cases (n_tests=3) land *past* day 30 and the control switches off (`age<30 AND cum≥$25k`
is an AND — it doesn't decay, it cuts out). That is precisely the $54.4k miss and the
68.75% frontier cell: a patient attacker beats a calendar window with patience alone, no
cleverness. Per the analyst, the real fix is **not a bigger arbitrary window** (60/90
days just delays the same bypass) but tying release to *verification-completion* — a
legit account change clears on an independent callback; a fake vendor's callback never
clears, so its hold never lifts regardless of time. Modeling that faithfully needs a
simulated callback-confirmation event (not the fraud label — that would be the oracle
cheat F4 exists to prevent), which is new generator work → **Cycle 14 candidate.**

## Report-accuracy fixes applied this cycle (from the review)
- `dual_control_releases_per_day` → `dual_control_queue_per_day`: it counts wires
  *awaiting* second-analyst disposition (25.7/day), not auto-releases — most are
  correctly-held fraud. The old name invited a dangerous misread.
- `largest_missed_wire` now carries `largest_missed_variant` so the worst miss is
  dispositionable (confirmed: bec_establish_slow_strike — the control-bypass, not a
  stray outlier).

## Needs-owner (flagged by review, not decided)
1. **Ratify or set the $25k cap / 30-day window.** D-035 approved the *mechanism*, not
   these numbers — same category as the D-027 cost constants, which you set explicitly.
   Note: median legit invoice is ~$13k, so two normal payments to a newly-onboarded
   legit supplier cross $25k inside one billing cycle — a real driver of the 6.7
   control-only holds/day (legitimate onboarding friction, which you approved in
   principle). Both values are named constants at the top of `wire.py`, owner-tunable.
2. **Verification-completion control vs. accept the fixed-window bypass as known
   residual risk** — a scope/roadmap call (Cycle 14 work if pursued).
3. Discovery-latency is a flat 5 days across fraud types; real BEC discovery runs weeks,
   ATO hours. Differentiating by type is a later data-science refinement (non-blocking).

## Reviewer volume note
27.5 wire holds/day (1.8 human-release + 25.7 dual-control queue) at 21.2% precision is
a reviewer-SLA/staffing question for whoever owns wire review capacity — flagged, not a
hard cap violation (wire has no numeric alert cap; it is SLA-bound).
