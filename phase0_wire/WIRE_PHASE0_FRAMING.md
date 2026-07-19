# Phase 0 Framing — Wire / Bank Transfers
**Role: Product Manager (#11) | Status: FRAMING DRAFT for owner review — no decisions locked**
Last channel in the D-003 sequence. Runs its own Phase 0 per D-002.

## How wire differs from both prior channels
- **Volume/value inversion**: thousands of times fewer transactions than cards, each
  orders of magnitude larger ($10k–$10M+). One missed fraud can exceed a year of card
  losses; one false block on a legitimate corporate payroll wire is a serious business
  incident. Both error costs are extreme — the cost ratio debate is qualitatively
  different, not just a bigger number.
- **Latency is not the constraint**: wires settle in hours (domestic) to days (SWIFT
  cross-border). Minutes of scoring time are acceptable; deep enrichment (beneficiary
  history, sanctions screening, cross-referencing invoices) can run IN-LINE, unlike cards.
  The 100ms discipline doesn't apply — a deliberate review window is a feature.
- **The dominant fraud is BEC (business email compromise) / invoice manipulation**: a
  finance employee is deceived into wiring to an attacker-controlled account (fake
  invoice, "urgent CEO request", supplier bank-detail change). Like APP scams, the
  authorized party sends willingly — but the victim is an *organization*, and the tells
  live in payment-instruction anomalies: beneficiary account changed recently, first
  payment to this beneficiary bank/country, amount/timing off-cycle vs the supplier's
  invoice history.
- **Hard AML adjacency**: wires are the most heavily regulated payment rail
  (SWIFT/correspondent banking, sanctions screening obligations, travel rule). More than
  P2P, wire fraud detection and AML compliance overlap; the D-019 pattern (fraud here,
  AML in its own phase) needs an explicitly drawn boundary to avoid scope bleed.

## Draft taxonomy for wire v1
1. `wire_bec` — deceived insider sends to attacker account (fake invoice, exec
   impersonation, supplier detail change). The channel's defining problem.
2. `wire_ato` — compromised online-banking session initiates the wire (our ATO signal
   set transfers directly).
Out of scope for v1: sanctions evasion, trade-based laundering (AML phase), internal
fraud by genuine employees (insider-threat program, different discipline).

## Success-criteria deltas to decide (owner input needed eventually)
| Dimension | Cards | P2P | Wire (draft) |
|---|---|---|---|
| Cost ratio | 5:1 | 10:1 | Per-dollar, not per-event: expected-loss-weighted scoring (a $2M wire ≠ a $10k wire) — proposal: cost = ratio x amount |
| Latency | 100ms | ~500ms | Minutes; in-line enrichment allowed; mandatory review window for first-time high-value beneficiaries is on the table |
| Autonomy | txn block | + delayed settlement | Draft: system may HOLD any wire autonomously; RELEASE of a held wire above a threshold (e.g. $100k) requires human sign-off — inverts the autonomy question: machine can stop, only humans can un-stop big ones |
| Alert lane | 200/day | 100/day | Tiny volume: every held wire is reviewed; cap is not the binding constraint, reviewer SLA is (hold windows expire) |
| Explainability | frozen format | same | Same format + beneficiary-change evidence (what changed, when, requested by whom) |

## Signals inventory (for the eventual model)
Beneficiary novelty/change recency (the BEC tell), amount vs invoice/payroll cycle
history, beneficiary bank country vs supplier's historical country, request channel
metadata (where observable: email-initiated vs portal-initiated), session/device for ATO,
counterparty reputation across institutions (a federation-layer natural fit — attacker
beneficiary accounts hit many victim organizations).

## Open questions for owner (before wire Phase 1)
1. Per-dollar (expected-loss) cost model vs per-event ratio — approve the per-dollar draft?
2. The inverted autonomy rule (machine holds anything; human releases above $100k) — approve?
3. Corporate vs retail wires in v1 scope — BEC is corporate; retail wire scams (romance,
   investment) behave more like P2P APP. Both, or corporate-first?
4. AML boundary: confirm sanctions screening stays OUT (existing bank systems own it) and
   we only consume its verdict as a feature.

## Reuse from existing stack
Point-in-time replay pattern, OOF calibration, analytic thresholds (adapted to per-dollar
cost), hold-state mechanism (wire holds are first-class here), alert queue + dashboard,
experiment registry, federation design (counterparty reputation is wire's killer app for it).
