# Cycle 8 Results — P2P Red Team + Wire Framing
**To: Owner | Executed under D-026 | Date: 2026-07-19**

## C8-1: P2P red team — the honest numbers

| Metric | Cycle 7 (easy data) | Red-teamed | + counter-features |
|---|---|---|---|
| Recall | 93.8% | 76.7% | 77.5% |
| — APP blatant | — | 87.1% | 90.3% |
| — APP evasive (installments→sleepers) | — | 68.1% | **69.6%** |
| — ATO blatant | — | 100% | 100% |
| — ATO evasive (session hijack) | — | 100% | 66.7%* |
| Precision | 89.4% | 21.5% | 23.4% |
| Alerts/day | 8.5 | 39.6 | 36.8 (cap 100) |
| False blocks | 0 | 7 | 5 |
| Cost vs naive (10:1) | 0.089 | 0.326 | 0.309 |

*\*tiny cell (~6 rows) — treat as noise, not a real regression.*

**Evasions added:** installment coaching (payments inside the victim's normal band,
spread over days), sleeper mules (ordinary personal accounts with months of real history
— defeats account-age and fan-in heuristics), and session-hijack ATO (no device
mismatch, mildly-off biometrics).

**Counter-features added** (pair-cumulative amounts, coached-cadence counts, recipient
inbound acceleration vs own history) recovered only ~1.5pts on the evasive cell.

## The finding that matters (reported, not spun)
**Installment-coached APP scams to sleeper mules are largely undetectable from transfer
metadata alone.** Each payment is individually indistinguishable from the victim's
normal behavior, and the recipient looks like a normal account because it *was* one.
This is consistent with real-world experience — it is why the industry's answer to APP
fraud is increasingly friction UX (confirmation-of-payee, scam-warning interstitials,
cooling-off periods for new payees) and regulatory reimbursement (UK PSR-style), not
pure detection. Recommendation for P2P v1.1: pair the model with mandatory
delayed-settlement + confirmation prompts for first-time-recipient payments above a
sender-relative threshold — turning the 69.6% detection cell into a friction-mitigated
cell rather than chasing an unwinnable pure-ML target.

## C8-2: Wire-transfer Phase 0 framing (docs only) — `phase0_wire/`
Last channel's framing drafted: BEC/invoice-manipulation as the defining fraud,
per-dollar (expected-loss) cost model proposal, inverted autonomy draft (machine may
hold any wire; human sign-off to RELEASE above $100k), latency constraint dissolves
(minutes acceptable, in-line enrichment allowed), hard AML boundary drawn. **Four open
questions for owner** listed in the pack — wire Phase 1 blocked on them by design.

## Sample-size caveat
Variant cells are 6–45 rows; directions are consistent but exact percentages carry wide
error bars. Bigger simulations before trusting cell-level differences under ~5pts.
