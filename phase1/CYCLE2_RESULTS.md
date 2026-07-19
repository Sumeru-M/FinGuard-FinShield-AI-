# Cycle 2 Results — "Red Team Then Harden" (Card Payments)
**To: Owner | Executed under D-015 | Date: 2026-07-19**

## The headline, honestly
As predicted, the adversarial data broke the illusion. Model quality on evasive fraud is
materially worse than the Phase 1 pilot suggested — and that was the entire point of this
cycle. These numbers are trustworthy in a way the pilot's were not.

## v0 (pilot, easy data) vs v0.1 (adversarial data + investigation-hold)

| Metric | v0 / easy data | v0.1 model alone | v0.1 + hold state |
|---|---|---|---|
| Recall | 96.7% | 80.3% | **89.4%** |
| — blatant variants | — | 94.7% | 94.7% |
| — evasive variants | — | 74.5% | **87.2%** |
| Precision | 98.9% | 63.9% | 24.4% (see note) |
| Alerts/day | 8.9 | 8.3 | 24.2 (cap 200) |
| False hard-blocks (10 days) | 1 | ~30 | 30 |
| Cost vs naive | 0.035 | 0.288 | 0.354 |
| Latency p99 | 0.64ms | — | 0.53ms |

All four Phase 0 exit gates still PASS on the harder data.

**Precision note (important):** the drop to 24.4% is dominated by hold-floored alerts —
178 of 242 alerts are transactions on cards *already under investigation*, most of them the
victim's own legitimate activity after a fraud burst. Challenging a compromised card's
traffic is defensible protective friction (step-up auth, not blocks), but it means alert
volume is now ~3x model-only volume. The Fraud Analyst workflow must treat "card under
investigation" alerts as a separate, lighter-touch review lane — flagged for the D-011
format review.

## What Cycle 2 changed
1. **Adversarial generator v2** (`finguard/datagen.py`): evasive CNP (in-band amounts, aged
   device fingerprints, home country), slow-burn ATO (multi-day warmup then cash-out),
   distributed card-testing (cross-merchant, rotating devices) + legit travel bursts so
   foreign-country/new-device stopped being free wins. `variant` column enables honest
   per-variant reporting.
2. **Investigation-hold state** (`finguard/scoring.py`): alerted cards are floored at
   soft_challenge for 48h (TTL from last model-driven alert; hold-floored alerts cannot
   self-extend). Analyst disposition `confirmed_legitimate` clears the hold via the API.
   Regression test: the Phase 1 repetition attack that decayed to approve now stays
   challenged for its full run. This alone lifted evasive recall 74.5% → 87.2%.
3. **Experiment registry** (`finguard/experiments.py`): every train/eval run appends to
   `data/experiments.jsonl`; `python -m finguard.experiments diff <a> <b>` compares runs.
4. **Bias review fixed** (`finguard/train.py`): the quantile cutoff degenerated under tied
   tree scores (flagged 100% everywhere); now uses the true operating threshold. Result on
   v2 data: flag-over-fraud ratios 1.0–2.0 across all countries — flags track fraud, not
   geography. Clean, and now measured credibly.

## Remaining known weaknesses (not hidden)
- **Soft-challenge tier is still model-dead** — both tuned thresholds sit at the top of the
  score range; the tier only fires via hold-flooring. The score distribution is too
  bimodal; fixing this likely needs calibration work (e.g. isotonic/Platt + finer trees),
  a candidate for Cycle 3.
- **CNP evasive recall is the weakest cell** (76.2% by type) — in-band-amount fraud on aged
  devices in home country is genuinely hard with current features; candidate features:
  merchant-risk scores, time-of-day profiles, cross-card device reputation.
- **False hard-blocks rose to 30/10 days** (~3/day) — within tolerable range at 5:1 but
  should be watched as thresholds move.

## D-010 memo (cost ratio) — revisited as promised
On v2 data the 5:1 ratio is now binding (cost-optimal threshold changes if the ratio moves
±2x), so the placeholder finally matters. Recommendation unchanged: keep 5:1 until real
data, but it is no longer decorative — recorded here as the promised re-derivation.

## Reproduce
```
.venv/bin/python -m finguard.datagen           # v2 adversarial data (evasive share 0.5)
.venv/bin/python -m finguard.features
.venv/bin/python -m finguard.train
.venv/bin/python -m finguard.harness
.venv/bin/python -m finguard.experiments list  # run registry
```
