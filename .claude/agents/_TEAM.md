# FinGuard Team Charter (shared context — every agent reads this first)

## Hierarchy
Owner (sole decision maker) → Team Lead (the main Claude session, PM-of-record) → the 11
role agents below. Agents NEVER decide owner-gated questions (cost ratios, autonomy
boundaries, scope, compliance posture) — they flag them in their report and stop.

## Binding project law
- `phase0/00_decisions_log.md` — D-001…D-032 are locked decisions; cite them, never
  contradict them. Notable: 100ms card latency (D-004), autonomy bounds (D-005, D-018,
  D-028), federated no-raw-data rule (D-006/D-012), cost models (D-010 5:1 cards,
  D-017 10:1 P2P, D-027 per-dollar wire), alert caps (D-007, D-023), frozen alert
  format (D-011 + `phase0/03_explainability_spec.md`).

## Code map (all Python, venv at `.venv/`)
- `finguard/datagen.py` — card synthetic data (adversarial variants)
- `finguard/features.py` — card feature store + point-in-time replay (26 features)
- `finguard/train.py` — card model: OOF isotonic calibration, analytic thresholds
- `finguard/scoring.py` — engine, FastAPI service, hold-state, alert queue
- `finguard/static/dashboard.html` — investigator UI (dual-lane)
- `finguard/harness.py` — end-to-end eval vs Phase 0 gates
- `finguard/federation.py` — 3-institution federated simulation
- `finguard/p2p.py` — P2P channel slice (red-teamed)
- `finguard/wire.py` — wire channel slice (red-teamed)
- `finguard/experiments.py` — run registry (`data/experiments.jsonl`)
- Cycle reports: `phase1/CYCLE*_RESULTS.md`

## House rules
1. Honest numbers only — report regressions and failures verbatim; never tune on test
   labels; point-in-time correctness is sacred (features read state BEFORE update).
2. Stay in your lane; if the task needs another role, say so in the report rather than
   improvising outside your expertise.
3. Determinism: seeds fixed; log every train/eval run to the experiment registry.
4. Report format (mandatory, ends every task):
   **REPORT** — Task / What I did / Results (numbers) / Risks-flags / Needs-owner (if any).
