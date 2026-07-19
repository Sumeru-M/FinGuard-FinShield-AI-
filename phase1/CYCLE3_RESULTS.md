# Cycle 3 Results — Model Quality (Card Payments)
**To: Owner | Executed under D-016 | Date: 2026-07-19**

## Full-system comparison (same adversarial v2 data, 10-day held-out window)

| Metric | Cycle 2 (v0.1 + hold) | Cycle 3 (v0.2 + hold) | Direction |
|---|---|---|---|
| Recall | 89.4% | 89.4% | flat |
| — evasive variants | 87.2% | 85.1% | ~flat |
| — blatant variants | 94.7% | **100%** | up |
| Precision | 24.4% | **48.8%** | 2x better |
| Alerts/day | 24.2 | **12.1** | half the noise |
| False hard-blocks (10 days) | 30 | **1** | 30x better |
| Cost vs naive | 0.354 | **0.183** | best yet |
| Latency p99 | 0.53ms | 0.42ms | flat |

Model-only precision is **98.1%** (Cycle 2: 63.9%) at the same 80.3% model-only recall —
the hold state then lifts system recall to 89.4% with far fewer wasted analyst reviews.
All Phase 0 exit gates still PASS.

## What Cycle 3 changed
1. **Six adversarial-robust features** (`finguard/features.py`, now 23 features): the theme
   is *observed history beats attacker-supplied fields* — a fraudster can spoof
   `device_age_days`, but cannot fake how long OUR store has seen a device/merchant, how
   many cards a device has touched, a card's usual transaction hour (circular stats), or
   its amount z-score. These drove the false-block collapse (30 → 1) and blatant recall
   to 100%.
2. **Out-of-fold isotonic calibration** (`finguard/train.py`): raw LightGBM scores are now
   calibrated probabilities. First attempt (chronological holdout) cost 12pts of recall —
   fraud rows are too scarce to sacrifice; recorded honestly in the registry
   (train_20260719_150223) and replaced with 5-fold OOF calibration on the full window.
3. **Analytic thresholds replace grid search** — and fixed a latent methodology bug: the
   old tuner searched thresholds ON TEST LABELS (leakage, overfit to <100 fraud rows).
   Because scores are now calibrated probabilities, thresholds fall out of the D-010 cost
   model directly: challenge beats approve at p > 0.070; block beats challenge at
   p > 0.412. No data leakage, alert cap enforced on training-window OOF volume.

## Soft-challenge tier: structurally alive, empirically sparse
The tier now exists for real (t_chal 0.070 ≠ t_block 0.412, decisions in the band are
possible and hold-floored alerts use it). But on THIS synthetic distribution almost no
transaction lands between 0.07 and 0.41 — the data is still too separable for a genuine
"uncertain" population. Expect the band to populate on real data; not force-fixable with
more synthetic tuning and we won't pretend otherwise.

## Remaining weakest cell
Evasive CNP by type: **71.4%** recall — in-band amounts on aged-spoofed devices from the
victim's home country remains genuinely hard. The strongest untried lever is cross-card
device reputation with fraud-outcome feedback (device linked to prior CONFIRMED fraud),
which requires wiring analyst dispositions back into the feature store — a natural Cycle 4
candidate alongside the investigator dashboard (the label loop needs its UI anyway).

## Registry
Compare runs: `python -m finguard.experiments list` / `... diff <run_a> <run_b>`.
This cycle logged: failed holdout-calibration run, OOF run, final analytic-threshold run.
