# Phase 1 Results Report — Card Payments Pilot
**To: Owner | From: all roles via PM (#11) | Date: 2026-07-18**
Executed under D-014. Everything below is built, run, and verified locally.

## Exit criteria scorecard

| Criterion | Target | Achieved | Verdict |
|---|---|---|---|
| End-to-end slice runs | stream → decision → alert | Yes, reproducible via 4 commands | PASS |
| Latency p99 (engine) | < 100ms | **0.64ms** (p50 0.11ms) | PASS |
| Latency p99 (HTTP round-trip) | < 100ms | **16.9ms** localhost | PASS |
| Beats naive baseline at 5:1 cost | cost ratio < 1.0 | **0.035** (96.5% cost reduction) | PASS |
| Alert volume | ≤ 200/day | **8.9/day** | PASS |
| Explainable alerts | D-011 payload | Every alert carries top 3–7 features | PASS |
| Bias/proxy review | completed + reported | Done — see caveat 3 | PASS w/ caveat |
| Recall / precision | (report) | **96.7% / 98.9%** on held-out 10 days | — |
| Recall by type | (report) | CNP 95%, ATO 90%, card-testing 100% | — |

## What was built (`finguard/`)
- `datagen.py` — WS-1: 130k labeled synthetic transactions, 0.23% fraud prevalence,
  three taxonomy fraud patterns, deterministic seed
- `features.py` — WS-2: event-order stream replay, 17 point-in-time-correct features,
  institution-scoped keys (federated-ready per D-012), Redis-swappable store interface
- `train.py` — WS-4: LightGBM v0, asymmetric 5:1 cost in training + threshold search
  under the 200/day alert cap, bias review
- `scoring.py` — WS-3+WS-5: ScoringEngine hot path, FastAPI service (`/score`,
  `/alerts`, `/alerts/{id}/disposition/{label}`), SQLite investigator queue with
  label-loop dispositions validated against the Phase 0 labeling standard
- `harness.py` — WS-6: full-stream replay evaluation; results in `data/eval_report.json`

## Caveats the owner should know (reported faithfully)
1. **Synthetic data is too easy.** The model separates fraud almost perfectly, so the
   tuned thresholds collapsed to a single hard-block band — the soft_challenge tier
   never fires on this dataset. Expect all metrics to get substantially worse on real
   data; that is normal and is what the D-010 re-derivation cycle is for.
2. **Adaptive-repetition weakness (observed in testing).** If an attacker repeats an
   identical transaction pattern on one card long enough, the card's profile normalizes
   and later repeats score low. First-burst detection works (that's when the alert
   fires), but v0 has no "already-alerted card" hold state. Recommend a
   card-under-investigation flag as a v0.1 item.
3. **Bias review artifact.** Flag-rate/fraud-rate ratios are elevated for low-fraud
   countries (IN ~11x, US ~6x) at the review's fixed quantile cutoff. Actual false
   blocks in evaluation: **1 total**, so no evidence of harmful disparity at the
   operating threshold — but this metric must be re-run on real data before launch.
4. **Infra adaptation.** Docker daemon unavailable on this machine, so the pilot uses
   an in-process feature store behind a Redis-compatible interface instead of
   Kafka+Redis containers. Streaming semantics (event-order, point-in-time reads) are
   preserved; swap-in is an infra task, not a redesign.
5. **FastAPI on Python 3.14** required body models at module scope (lazy-annotation
   change) — fixed, noted for future services.

## Owner-gated items now due (per Phase 0 revisit triggers)
- **D-010 memo:** on this synthetic distribution the 5:1 ratio was not binding (the
  model is cost-optimal far below both caps). Recommendation: keep 5:1 until real or
  harder synthetic data makes the trade-off real. No change requested.
- **D-011 analyst review:** live alert format now exists and can be inspected
  (`/alerts` endpoint or `data/alerts.db`). The format freeze awaits a Fraud-Analyst
  pass — recommend doing this before any dashboard build in WS-5's next iteration.

## Reproduce
```
.venv/bin/python -m finguard.datagen --out data/transactions.parquet
.venv/bin/python -m finguard.features
.venv/bin/python -m finguard.train
.venv/bin/python -m finguard.harness          # exit-criteria scorecard
.venv/bin/python -m finguard.scoring          # serve on 127.0.0.1:8100
```
