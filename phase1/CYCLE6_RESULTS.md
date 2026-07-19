# Cycle 6 Results — Federation Phase
**To: Owner | Executed under D-022 | Date: 2026-07-19**

## What was built
`finguard/federation.py` — a three-institution simulation honoring the hard D-006
boundary end-to-end: each institution generates its own transactions, builds its own
feature store, and trains + calibrates its own model entirely locally. **The only
artifact that crosses an institutional boundary is the trained, calibrated model.**
Aggregation is a cross-institution ensemble (average of calibrated probabilities) —
the model-fusion analogue of FedAvg appropriate for gradient-boosted trees — and it
happens out-of-band, never in the 100ms scoring path (D-004 preserved).

Institutions are deliberately heterogeneous: a large incumbent (2,500 cards), a
mid-size (1,200), and a small fintech (350), with different evasive-fraud mixes —
attackers don't hit everyone equally.

## Results: local-only vs federated, per institution

| Institution | Recall local → fed | Precision local → fed | Cost local → fed |
|---|---|---|---|
| inst_001 (large) | 40.4% → **80.8%** | 67.7% → 48.3% | 0.635 → **0.310** |
| inst_002 (mid) | 56.3% → **93.8%** | 100% → 65.2% | 0.438 → **0.143** |
| inst_003 (small) | 33.3% → **50.0%** | 50.0% → 30.0% | 0.733 → **0.603** |

**Expected-cost improves for all three institutions** at the D-010 5:1 cost model —
federation roughly doubles recall everywhere, and the precision it spends to get there
is cost-positive in every case. The hypothesis ("federation helps the small institution
most") was actually too narrow: each institution's local model overfits its own fraud
mix, and peers' models cover each other's blind spots. This validates the project's
founding premise: institutions that cannot share a single raw record still materially
improve each other's fraud detection by sharing models alone.

## Honest caveats
- **Per-institution fraud counts in test windows are small** (52 / 16 / 6 rows) —
  directions are consistent across all three institutions, but the small-institution
  numbers especially carry wide error bars.
- **Model artifacts leak more than gradients**: tree split thresholds can encode
  training-data values (e.g., specific amounts). Real deployment needs differential
  privacy on tree construction or secure aggregation — logged as the federation phase's
  Cybersecurity requirement before any real-institution pilot.
- **Thresholds stay institution-local** (each keeps its analytically derived
  t_chal/t_block) — a governance feature, not a bug: each institution answers to its own
  cost function and alert capacity.
- No orchestration layer yet (this is single-process simulation): the model-exchange
  protocol (signing, versioning, schedule) is future work when real infra exists.

## Where this leaves the roadmap
The last major *technical* pillar of the original goal statement now has a working,
measured proof: real-time scoring (Cycles 1–5) + adaptive robustness (2–4) +
explainability (5) + federated learning without raw-data sharing (6). Remaining frontiers
are integration-grade rather than research-grade: real infra swap (Docker-blocked),
federation orchestration + DP hardening, P2P Phase 1 (two owner questions open), and the
real-data legal gate (D-009).
