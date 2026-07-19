# Cycle 7 Results — P2P Phase 1 Vertical Slice
**To: Owner | Executed under D-025 (with D-017/018/019/023/024) | Date: 2026-07-19**

## Headline results (10-day held-out window, 81 fraud transfers)

| Metric | Result | Constraint |
|---|---|---|
| Recall | **93.8%** | — |
| — APP scam (the hard one) | **92.9%** | — |
| — ATO transfer | **100%** | — |
| Precision | **89.4%** | — |
| Alerts/day | 8.5 | ≤ 100 (D-023 separate lane) — PASS |
| False blocks | **0** | — |
| Cost vs naive | **0.089** | 10:1 model (D-017) |
| Delayed-settlement tier used | **YES** — 2.9 holds/day vs 5.6 blocks/day | D-018 |

**The three-tier decision system finally lives.** On cards, the soft tier only fired via
investigation-holds; P2P has genuine intermediate uncertainty, and the analytic
thresholds (hold at p > 0.022, block at p > 0.444 under the 10:1 cost model) put ~35% of
alerted transfers into delayed settlement rather than outright blocks. Zero legitimate
transfers were hard-blocked.

## Why APP-scam detection works despite clean device/behavior signals
As framed in Phase 0: the victim authorizes the transfer, so device and biometric
signals read normal. Detection instead leans on:
- **Sender context**: first-time recipient + amount far above the sender's norm
- **Recipient reputation (D-024)**: mule accounts are young, have high fan-in, and a
  high share of first-time senders — visible to the institution without any new data
  collection (it's all transfer metadata the institution already processes)
The model catches 92.9% of APP scams this way — validating the Phase 0 bet that
recipient-side features are the decisive signal for this channel.

## What was built (`finguard/p2p.py`)
Self-contained P2P slice reusing the card stack's method: event-order point-in-time
feature replay, OOF isotonic calibration, analytic cost-model thresholds — but with
channel-specific everything: 13 P2P features (5 recipient-side), 10:1 cost model,
approve/hold_funds/block decisions, 100/day separate lane, D-019 scope (mule accounts
are a *feature source*, not a detection target — that stays in the AML phase).

## Honest caveats
- Same synthetic-data caveat as cards pre-Cycle-2: this generator's scam patterns are
  written by the same hand as the features. A P2P red-team pass (coached victims paying
  in smaller installments to established-looking mules, aged mule accounts) is the
  natural next hardening step before trusting these numbers.
- Recipient-reputation features remain **gated on the data-minimization review (D-024)**
  before any real data touches them.
- Delayed-settlement UX (notification to sender, auto-release timing) is product design
  debt, not modeled here.

## Channel status per D-002/D-003
- **Cards**: Phase 1 hardened through 5 cycles, format frozen, federation proven
- **P2P**: Phase 1 vertical slice COMPLETE (this cycle)
- **Wire/bank transfers**: Phase 0 framing not yet started — last channel in the sequence
