# Cycle 12 Results — Consolidation
**To: Owner | Executed under D-035 → D-038 | Date: 2026-07-20**
First cycle with the full agent team running in parallel lanes.

## What was delivered

### 1. Shared core library (`finguard/core.py`) — Team Lead
The training recipe that existed in FOUR near-identical copies (cards, P2P, wire,
federation) now lives once: `train_calibrated` (GBT → 5-fold OOF → isotonic),
`score_calibrated`, `graduated_thresholds` (the analytic dual-threshold algebra), and
`apply_alert_cap`. All four call sites refactored onto it.
**Verification — outputs are bit-identical pre/post refactor:**
- Cards: recall 83.3% / precision 93.2% / cost 0.179 / thresholds 0.0698, 0.4118 ✓
- P2P: recall 77.5% / precision 23.4% / cost 0.309 / thresholds 0.0217, 0.4444 ✓
- Wire: count 98.7% / value 99.8% / precision 20.0% / loss 0.110 ✓

### 2. Test suite (`tests/`, 13 tests, ~2s) — Team Lead
- `test_core.py` — threshold algebra pinned to the Cycle 3/7 derivations; calibrated
  training sanity on synthetic data
- `test_point_in_time.py` — the sacred discipline as executable law: features see
  state BEFORE the transaction; label feedback respects the 24h latency
- `test_engine_and_contract.py` — Cycle 2's repetition-attack regression (never decays
  to approve), hold TTL/clear behavior, and the FROZEN D-011 alert contract (required
  fields, removed `confidence` stays removed, 3–7 attributions on model alerts, none
  on hold-floored)
- `test_phase0_gates.py` — the exit gates as regression tests against published eval
  artifacts (latency, caps, beats-naive, wire's no-big-wire-escapes posture)
All 13 pass. `pytest` from the repo root is now the pre-commit check.

### 3. Docs — Product Manager agent
`README.md` (honest per-channel state, what is NOT built, quickstart, governance
model) and `ARCHITECTURE.md` (scoring path, per-channel deltas, hold/label-loop
mechanisms, federation design, known-debts table). Team Lead review caught one
staleness (sub-$100k policy written as "undefined" pre-D-036) — corrected to
dual-control-decided/implementation-pending.

### 4. Sanctions-feed auth spec — Cybersecurity agent (D-037)
`phase0_wire/SANCTIONS_FEED_AUTH_SPEC.md`: threat model (spoof/replay/suppress paths,
severity-ranked), mTLS + per-verdict signing + replay/freshness requirements,
**fail-closed recommended** as default posture, audit logging, and six verification
checks gating the stub's replacement at integration time.

## Needs-owner (carried from the Cybersecurity spec — new items)
1. Whether a bounded fail-open exception should exist for ordinary vendor outages
   (spec default: none — full fail-closed), and its dollar/duration bounds if so
2. Audit-log retention for the AML/compliance side (security baseline D-008 may be
   shorter than regulator/dispute windows require)
3. Vendor-selection criterion: upstream must state a list-update SLA (sizes the
   verdict freshness window)

## Debt retired vs debt remaining
Retired: recipe quadruplication, zero-test state, undocumented repo, registry
mislabeling (Cycle 11 F5), doc-vs-decision staleness.
Remaining (tracked in ARCHITECTURE.md's debt table): Docker-gated infra swap, DP
hardening for federation, wire label-timing fix (F4), D-035/D-036 friction-control
implementation, disposition audit-trail/role auth, P2P friction implementation.
