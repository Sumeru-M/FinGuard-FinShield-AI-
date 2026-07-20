# FinGuard (FraudShield AI)

Real-time, explainable fraud detection across three payment channels — **cards**,
**P2P transfers**, and **wire/bank transfers** — built federated-ready from day one so
multiple institutions can improve detection together without ever sharing raw
transaction data (D-006/D-012).

This is a **synthetic-data pilot**. Everything below is built, run, and verified
locally against generated data, red-teamed against adversarial variants per channel.
No real customer data has touched this system (D-009 blocks that until legal/compliance
sign-off). Numbers in this README are the honest, most-recently-reported ones —
including the ones that look bad — per house rule "honest numbers only" (`_TEAM.md`).

## What FinGuard does

For each channel, a transaction (or wire, or transfer) is scored in real time against
a calibrated fraud-probability model, converted into a decision via an **analytic,
cost-model-derived threshold** (never grid-searched on test labels — see
`ARCHITECTURE.md`), and — for anything but a clean approve — pushed to an investigator
queue with a frozen, D-011-spec explainability payload (top contributing features,
transaction context, plain-language units). Analyst dispositions feed back into the
feature store (the "label loop"), which is how the model learns that a device linked to
confirmed fraud yesterday is a bad sign today.

Decisions are graduated and scoped to the single transaction under review — the system
never takes account-level action without a human (D-005, and its channel-specific
variants D-018, D-028).

## Current state, channel by channel

| Channel | Phase | Red-teamed? | Headline honest number | Status |
|---|---|---|---|---|
| Cards | Phase 1, hardened 5 cycles | Yes (Cycles 2, 8-style methodology) | **92.4% system recall**, 46.2% precision, 13.2 alerts/day (cap 200, D-007) | Format frozen (D-011), federation proven |
| P2P transfers | Phase 1, red-teamed | Yes (Cycle 8) | **77.5% recall** (down from 76.7% pre-counter-features; APP-scam evasive cell only 69.6%) | Friction-policy question open with owner |
| Wire transfers | Phase 1, hardened 2 cycles | Yes (Cycles 10-11) | **99.8% recall by value**, but **81.3% on the slow-establishment-strike frontier cell** (n=16) | New-beneficiary process control open with owner (Cycle 11 needs-owner #1) |

Full per-cycle numbers: `phase1/CYCLE2_RESULTS.md` through `CYCLE11_RESULTS.md`.

### The finding that matters most, honestly

Two of three channels have a **structurally undetectable fraud cell** that pure ML does
not close, confirmed independently in both:

- **P2P (Cycle 8):** installment-coached APP scams to sleeper mule accounts —
  individually indistinguishable from the victim's normal behavior, sent to an account
  that *is* a normal account with months of real history. ~69.6% recall ceiling.
- **Wire (Cycle 11):** slow-establishment BEC strikes — the attacker manufactures
  exactly the account-age and history signals the model measures. 81.3% recall (n=16,
  wide confidence interval).

In both cases the team's recommendation is the same: pair detection with a **process
control** (mandatory cooling-off / cumulative-dollar cap / confirmation-of-payee on new
recipients) rather than chasing an unwinnable pure-ML target. This is approved in
principle for wire (D-035) but not yet implemented; P2P's equivalent is still an open
owner question (Cycle 8).

### What is NOT built

- **Docker-gated infrastructure.** Kafka/Redis containers are unavailable in this
  environment; the feature store uses an in-process, Redis-interface-compatible
  substitute. Streaming semantics (event order, point-in-time reads) are preserved —
  swapping in real Redis/Kafka is an infra task, not a redesign (Cycle 5).
- **Differential-privacy hardening on federation.** The current federated simulation
  shares only trained model artifacts, never raw data (D-006) — but tree split
  thresholds can still leak training-data values. DP on tree construction or secure
  aggregation is required before any real-institution federation pilot (Cycle 6).
- **Label-timing fix for wire establishment fraud.** Establishment test-payments
  currently train as labeled fraud; in production they'd be unlabeled until after the
  strike. The 100% establish-strike recall cell is likely somewhat inflated (Cycle 11,
  finding F4).
- **P2P/wire friction-control implementation.** D-035 (wire beneficiary cooling-off +
  cumulative cap) is approved but not yet built. P2P's equivalent friction policy is
  still an open owner question from Cycle 8.
- **Sub-$100k held-wire release policy.** Decided (D-036: dual-control — a second
  analyst must co-sign any release) but not yet implemented; the structuring red-team
  variants target exactly this seam.
- **Sanctions-feed authentication.** Spec'd (D-037, Cybersecurity) but not built; the
  upstream sanctions verdict is currently a trusting stub (D-030 draws AML out of
  scope regardless — this system only consumes the verdict as a feature).
- **AML/mule detection as a first-class target.** Deliberately deferred to its own
  regulatory-adjacent phase for both P2P (D-019) and wire (D-030); recipient/beneficiary
  reputation is used as a *feature*, never as a standalone flag.
- **Real-data legal/compliance review.** Blocking gate (D-009) on real transaction data
  ingestion; everything to date runs on synthetic data only.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Each channel is an independent four-command pipeline (generate data → build features →
train → evaluate):

**Cards:**
```bash
.venv/bin/python -m finguard.datagen --out data/transactions.parquet
.venv/bin/python -m finguard.features
.venv/bin/python -m finguard.train
.venv/bin/python -m finguard.harness          # exit-criteria scorecard vs Phase 0 gates
```

**P2P:**
```bash
.venv/bin/python -m finguard.p2p              # self-contained: generate, featurize, train, eval
```

**Wire:**
```bash
.venv/bin/python -m finguard.wire             # self-contained: generate, featurize, train, eval
```

**Federation simulation (cards, 3 synthetic institutions):**
```bash
.venv/bin/python -m finguard.federation
```

**Investigator dashboard (cards, dual-lane queue + live scoring API):**
```bash
.venv/bin/python -m finguard.scoring          # serves on 127.0.0.1:8100
# then open http://127.0.0.1:8100/dashboard
```

**Experiment registry** (every train/eval run is logged):
```bash
.venv/bin/python -m finguard.experiments list
.venv/bin/python -m finguard.experiments diff <run_a> <run_b>
```

## Repo map

```
phase0/                    Card-payments Phase 0 framing pack (taxonomy, success
                            criteria, guardrails, explainability spec) + the
                            decision log (00_decisions_log.md — D-001...D-038, law)
phase0_p2p/                P2P Phase 0 framing (draft; open owner questions)
phase0_wire/                Wire Phase 0 framing (draft; open owner questions)
phase1/                    Cycle-by-cycle results reports, all channels, all cycles
                            (CYCLE2...CYCLE11_RESULTS.md, PHASE1_RESULTS.md,
                            PHASE1_KICKOFF_PROPOSAL.md)
finguard/
  core.py                  Shared training/threshold library (Cycle 12, D-038):
                            LightGBM + OOF isotonic calibration + analytic
                            cost-model thresholds — the one implementation every
                            channel converged on independently
  datagen.py                Card synthetic-data generator (adversarial variants)
  features.py                Card feature store + point-in-time replay (26 features)
  train.py                    Card model: cost-asymmetric training, calibration,
                            analytic thresholds, SHAP, bias review
  scoring.py                  Scoring engine, FastAPI service, hold-state,
                            investigator alert queue
  static/dashboard.html      Investigator UI (dual-lane: model-driven vs
                            card-under-investigation)
  harness.py                   End-to-end eval vs Phase 0 exit-criteria gates
  federation.py                 3-institution federated simulation (model-sharing,
                            never data-sharing)
  p2p.py                        P2P channel slice (generator, features, model,
                            hold_funds decision tier) — red-teamed
  wire.py                       Wire channel slice (generator, BEC/ATO features,
                            per-dollar thresholds, human-release queue) — red-teamed
  experiments.py                 Run registry (data/experiments.jsonl)
data/                       Generated artifacts: transactions, features, models,
                            eval reports, alerts.db, experiment registry
.claude/agents/             The 11 role-agent definitions + _TEAM.md charter
```

## Governance model

**Owner (sole decision maker) → Team Lead (PM-of-record toward the owner) → 11 role
agents.** Role agents never decide owner-gated questions (cost ratios, autonomy
boundaries, scope, compliance posture) — they flag them and stop. The Product Manager
role drafts framing and owner-facing proposals; the Team Lead presents them; only the
owner decides (D-001, `.claude/agents/_TEAM.md`).

**`phase0/00_decisions_log.md` is law.** Every locked decision (D-001 through D-038 as
of this writing) is binding on all roles until the owner explicitly revises it. When
new work implies a decision or contradicts an old one, the Product Manager drafts the
log entry — nothing is presented as decided that isn't logged there.

House rules that shape everything in this repo (`_TEAM.md`): honest numbers only
(report regressions and failures verbatim, never tune on test labels), point-in-time
correctness is sacred, deterministic seeds with every run logged to the experiment
registry, and every agent report ends with a REPORT block (Task / What I did / Results /
Risks-flags / Needs-owner).
