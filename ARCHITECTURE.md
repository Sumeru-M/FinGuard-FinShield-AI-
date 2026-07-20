# Architecture

Companion to `README.md`. Covers the scoring path, per-channel deltas, the two
feedback mechanisms (hold-state and label-loop), federation design, point-in-time
correctness discipline, and known debts. Cites decision numbers throughout — see
`phase0/00_decisions_log.md` for the full log.

## The scoring path (shared shape, all three channels)

```
feature store (point-in-time read)
        |
        v
calibrated GBT (LightGBM + OOF isotonic calibration)
        |
        v
analytic cost-model threshold(s)
        |
        v
graduated decision (approve / soft / hard, channel-specific labels)
        |
        v
explainable alert (D-011 payload) --> investigator queue --> disposition --> label loop
```

Every channel converged independently on the same recipe, which is why it now lives
once in **`finguard/core.py`** (Cycle 12, D-038) rather than three times:

1. **LightGBM** with `scale_pos_weight` set from the channel's cost asymmetry.
2. **5-fold out-of-fold (OOF) isotonic calibration.** A chronological-holdout attempt
   was tried first and cost 12 points of recall — fraud rows are too scarce to
   sacrifice a slice of them to a naive holdout (registry run
   `train_20260719_150223`, Cycle 3). OOF calibration on the full window replaced it.
3. **Analytic thresholds derived directly from the cost model** — never grid-searched
   against test labels. Cycle 3 found and fixed a real leakage bug: the original tuner
   searched thresholds *on test labels* with under 100 fraud rows, which is overfit by
   construction. Because scores are calibrated probabilities, thresholds now fall out
   of straightforward cost-minimization algebra instead.

Channel-specific cost constants and any non-standard threshold shape (wire's
amount-dependent threshold) stay in each channel's own module (`train.py`, `p2p.py`,
`wire.py`); the shared mechanics (fold splitting, calibration, GBM construction) live
in `core.py`.

## Per-channel deltas

| | Cards | P2P | Wire |
|---|---|---|---|
| Latency budget | **100ms p99** end-to-end (D-004); ~70-80ms compute budget after network/serialization overhead | Softer: 200-500ms tolerated; friction (confirmation screens) is a *feature*, not a bug | Not a constraint at all — wires settle in hours to days; minutes of in-line enrichment are fine |
| Cost model | **5:1 FN:FP** flat ratio (D-010) | **10:1 FN:FP** (D-017) — APP losses are unrecoverable, no chargeback safety net | **Per-dollar expected loss** (D-027): `cost(release) = p·A`, `cost(hold) = p·R_frac·A + (1-p)·D_frac·A + REVIEW_COST` — an amount-dependent threshold, not a flat ratio |
| Decisions | approve / soft_challenge / hard_block | approve / hold_funds (delayed settlement) / block | approve / **hold** (any wire, autonomous) / release |
| Autonomy boundary | System may soft-challenge or hard-block a *transaction*; no account-level action without a human (D-005) | Same D-005 floor, plus hold_funds is autonomous and self-reversing — funds auto-release (D-018) | **Inverted**: machine may HOLD any wire alone; a held wire above **$100k requires human sign-off to release** (D-028) |
| Alert lane | 200/day cap (D-007) | Separate lane, 100/day (D-023) — different reviewer skill, no cross-channel starvation | Every held wire gets reviewed; volume isn't the binding constraint, reviewer SLA against hold-window expiry is |

The wire cost model is worth spelling out because it drives the channel's whole
character: holding beats releasing when `p > (D_frac·A + REVIEW_COST) / ((1 - R_frac +
D_frac)·A)`. As `A` (the amount) grows, the right-hand side shrinks — a $2M wire is
held on a whisper of suspicion, a $5k wire needs real evidence. Cycle 9 confirmed this
works as designed: every missed fraud was small (worst case $22.3k pre-red-team,
tightened to $7.9k in Cycle 10), no large wire ever escaped, and value-recall (98.7%,
later 99.8%) consistently beat count-recall (95.7%, later 97.7%).

## Hold-state mechanism

Two distinct hold mechanisms exist, both are "system floors a decision without new
human input, but a human can clear it":

- **Cards — investigation hold** (`finguard/scoring.py`, Cycle 2): once a card
  triggers a model-driven alert, its transactions are floored at `soft_challenge` for
  48 hours (TTL from the last model-driven alert; a hold-floored alert cannot
  self-extend the window). This closed the Phase 1 caveat that a repeated-pattern
  attacker could "wait out" a decaying risk score — regression-tested, and it alone
  lifted evasive recall from 74.5% to 87.2% (Cycle 2). Analyst disposition
  `confirmed_legitimate` clears the hold via the API.
- **Wire — release queue** (`finguard/wire.py`, D-028): a hold is the *default*
  outcome of a machine decision above the amount-dependent threshold; wires under
  $100k release only under dual-control (D-036: second-analyst co-sign — decided,
  implementation pending), and wires above $100k sit in a human-release
  queue (4.9/day at Cycle 9 volume, 3.0/day after Cycle 10's red-team-driven
  generator fix).

Both mechanisms exist because a static per-transaction score is not enough — the
system needs memory of "this entity is already under a cloud" that persists across
transactions without waiting for a fresh human verdict each time.

## Label loop

Analyst dispositions (`confirmed_fraud_*`, `confirmed_legitimate`) write back into the
running feature store, not just into a database of outcomes:

- A `confirmed_fraud_*` disposition marks the associated device/card/merchant as
  reputation-poisoned; the next transaction touching that entity sees it as a feature.
  This is point-in-time correct via a **24-hour label latency** — a confirmation is
  invisible to scoring until a day after the fraud event, so there is no oracle-label
  leakage (Cycle 4).
- This was the lever that cracked the card channel's hardest cell: evasive CNP recall
  went 71.4% -> 90.5% (+19pts) in the cycle the label loop shipped, because a
  fraudster can mimic a victim's spending pattern but cannot un-poison a device that
  defrauded a different card yesterday.
- **Known gap (Cycle 4, still open):** the offline training simulation assumes every
  fraud row gets confirmed within 24h; in production only alerted/disputed fraud gets
  a disposition, so real reputation coverage will be thinner than what's measured
  here. The live serving path only marks what analysts actually confirm — the
  optimism is specifically in the *offline* simulation used for training/eval.
- **Known risk (Cycle 4, Cybersecurity backlog):** reputation features are a
  poisoning surface — a hostile or compromised analyst account could mark legitimate
  devices as fraud-linked. Acceptable at pilot scale; needs disposition audit-trail +
  role auth before real deployment. Wire's analogous risk (a hostile analyst releasing
  sub-$100k structured wires) is called out in Cycle 11 needs-owner #2 and is part of
  why D-036 (dual-control release) was adopted for the wire channel specifically.

## Federation design (D-006 / D-012)

`finguard/federation.py` (Cycle 6, D-022) simulates three heterogeneous institutions
(2,500 / 1,200 / 350 cards, different evasive-fraud mixes). The hard boundary is
enforced end-to-end: each institution generates its own transactions, builds its own
feature store, and trains + calibrates its own model **entirely locally**. The only
artifact that ever crosses an institutional boundary is the trained, calibrated model.

- **Aggregation scheme:** cross-institution ensemble fusion — each institution scores
  with every peer model and averages calibrated probabilities. This is the model-fusion
  analogue of FedAvg appropriate for gradient-boosted trees (FedAvg proper applies to
  gradient-descent parameters, which GBTs don't have).
- **Timing:** aggregation happens out-of-band, never inside the 100ms scoring path —
  D-004 is preserved by construction, not by measurement.
- **Thresholds stay institution-local** even after model-sharing — each institution
  keeps its own analytically-derived `t_chal`/`t_block`, a deliberate governance
  choice: each institution answers to its own cost function and alert capacity, not a
  shared one.
- **Result:** expected cost improved for all three simulated institutions under the
  D-010 5:1 model; recall roughly doubled everywhere (e.g. the large institution:
  40.4% -> 80.8%). The hypothesis "federation helps the small institution most" was
  too narrow — every institution's local model overfits its own fraud mix, and peers
  cover each other's blind spots.
- **Known gap (Cybersecurity backlog, flagged Cycle 6, unresolved):** model artifacts
  leak more than raw gradients — tree split thresholds can encode training-data
  values. Differential privacy on tree construction or secure aggregation is required
  before any real-institution federation pilot. No orchestration layer (signing,
  versioning, exchange schedule) exists yet either; this is a single-process
  simulation.

## Point-in-time correctness discipline

This is treated as sacred (`_TEAM.md` house rule #1) because it's the difference
between an honest evaluation and a leaked one. The rule, applied consistently across
`features.py`, `p2p.py`, and `wire.py`: **feature state is read BEFORE the current
event updates it.** Concretely:

- Transactions/transfers/wires are processed in strict event-timestamp order, never
  shuffled.
- A card's rolling mean, a device's first-seen date, a recipient's fan-in count — all
  reflect only what happened *before* the current row, never including it.
- The label loop's 24h latency (above) is the same discipline applied to a slower
  signal: a disposition is a fact that becomes visible to future scoring only after a
  realistic delay, never instantly.
- Evaluation splits are chronological (train on the first ~70% of days, evaluate on
  the rest) — never a random shuffle, so the reported numbers describe "trained on
  past, scored on future," which is the only claim that transfers to production.

The Cycle 3 threshold-tuning leak (searching cutoffs against test labels) was a
violation of the same spirit one layer up — not a temporal leak, but a label leak —
and the fix (analytic thresholds from the cost model, not a search) is now the
standing method for exactly that reason.

## Known debts and deferred items

| Item | Status | Where |
|---|---|---|
| Docker-gated infra swap (Kafka/Redis) | Blocked by environment, not design. `InMemoryFeatureStore` implements the same interface a `RedisFeatureStore` would; swap is additive | Cycle 5 |
| Differential-privacy hardening on federation | Not started; tree-split leakage is a known real risk before any real-institution pilot | Cycle 6 |
| Federation orchestration layer (signing, versioning, exchange schedule) | Not built; current federation is single-process simulation | Cycle 6 |
| Label-timing fix for wire establishment fraud | Not started; establishment test-payments currently train as labeled fraud, inflating the establish-strike recall cell | Cycle 11 finding F4 |
| P2P/wire new-recipient friction control (cooling-off, cumulative-dollar cap, confirmation-of-payee) | **Approved for wire (D-035)**, not yet implemented. P2P's equivalent is still an open owner question (Cycle 8) | D-035/D-036, Cycle 11 needs-owner #1 |
| Sub-$100k held-wire release policy | Decided: dual-control release (D-036), implementation pending; structuring red-team variants target exactly this seam | D-036 |
| Sanctions-feed authentication | Spec'd (D-037, Cybersecurity), not integrated; current upstream sanctions verdict is a trusting stub | D-037, Cycle 11 needs-owner #3 |
| Disposition audit-trail + role auth on the label loop | Not built; analyst-reputation poisoning surface is currently unmitigated on cards | Cycle 4 |
| Wire counter-feature window attacks (7d/24h fixed windows) | Not red-teamed; an attacker spacing new accounts >7 days apart defeats the current new-account counter | Cycle 11 finding #2 |
| Bigger red-team eval cells | Many variant cells sit at n=6-20; directions are consistent but percentages carry wide confidence intervals | Cycles 8, 10, 11 (repeated caveat) |
