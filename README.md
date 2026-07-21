# FinGuard (FraudShield AI)

Real-time, explainable, **federated-ready** fraud detection across three payment
channels — **cards**, **P2P transfers**, and **wire/bank transfers** — so multiple
institutions can improve detection together without ever sharing raw customer data.

> **Status: synthetic-data pilot.** Everything is built, run, and verified locally
> against generated data, red-teamed with adversarial variants per channel. No real
> customer data has touched this system. Numbers below are the honest, most-recent
> figures — including the unflattering ones.

## How it works

Each transaction is scored by a calibrated fraud model → a decision is set by an
**analytic, cost-model-derived threshold** (never tuned on test labels) → anything but a
clean approve goes to an investigator queue with an explainable payload (top features +
transaction context). Analyst dispositions feed back into the feature store (the "label
loop"). Decisions are graduated and scoped to the single transaction — no account-level
action without a human.

## Channel status (honest headline numbers)

| Channel | Recall | Notes |
|---|---|---|
| **Cards** | 92.4% system | Format frozen, federation-proven, 5 cycles hardened |
| **P2P** | 89.3% (with CoP friction) | 84.4% model-only; installment-scam tail closed by friction, not ML |
| **Wire** | 99.5% by value | Per-dollar cost model; verification-completion control on new beneficiaries |

Full per-cycle detail: [`phase1/CYCLE*_RESULTS.md`](phase1/) · architecture:
[`ARCHITECTURE.md`](ARCHITECTURE.md) · decisions (law): [`phase0/00_decisions_log.md`](phase0/00_decisions_log.md)

**Honest finding worth knowing:** two channels have a structurally hard fraud cell that
pure ML can't close — P2P installment scams to sleeper mules, and slow-establishment
BEC. Both are addressed with **process controls** (confirmation-of-payee, cooling-off +
verification), not by chasing an unwinnable model target.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# each channel is a self-contained pipeline (generate → featurize → train → evaluate)
.venv/bin/python -m finguard.datagen && .venv/bin/python -m finguard.features \
  && .venv/bin/python -m finguard.train && .venv/bin/python -m finguard.harness   # cards
.venv/bin/python -m finguard.p2p          # P2P
.venv/bin/python -m finguard.wire         # wire
.venv/bin/python -m finguard.federation   # 3-institution federated simulation
.venv/bin/pytest                          # 13-test suite (gates, contracts, regressions)

# investigator dashboard + live scoring API
.venv/bin/python -m finguard.scoring      # http://127.0.0.1:8100/dashboard
```

## Repo map

```
finguard/
  core.py         Shared training/threshold library (calibration + analytic thresholds)
  datagen/features/train/scoring/harness.py   Card pipeline + FastAPI service + dashboard
  p2p.py, wire.py                             P2P and wire channel slices (red-teamed)
  federation.py, federation_dp.py             Federated simulation + DP hardening
  experiments.py                              Run registry (data/experiments.jsonl)
phase0/          Framing packs + 00_decisions_log.md (D-001…, binding law)
phase1/          Cycle-by-cycle results reports (all channels)
.claude/agents/  11 role-agent definitions + _TEAM.md charter
tests/           pytest suite
```

## Governance

**Owner (sole decision maker) → Team Lead → 11 role agents.** Agents flag owner-gated
questions (cost ratios, autonomy, scope, compliance) and stop — they never decide them.
`phase0/00_decisions_log.md` is binding law. House rules: honest numbers only,
point-in-time correctness, deterministic seeds, every run logged. See
[`.claude/agents/_TEAM.md`](.claude/agents/_TEAM.md).
