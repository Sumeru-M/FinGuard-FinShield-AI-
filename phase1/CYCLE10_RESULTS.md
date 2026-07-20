# Cycle 10 Results — Wire Red Team (+ first multi-agent team cycle)
**To: Owner | Executed under D-032/D-033 | Date: 2026-07-20**

## Process note: the team structure worked
This cycle ran under the new 11-agent org (D-033). The Fraud Analyst agent's review of
the first red-team run **caught a flaw the Team Lead was about to publish**: the eval
window contained zero legitimate supplier-onboarding or bank-change events, so the
initial "precision improved to 79.8%" headline was measured in a world where no honest
customer ever changes an account number. The generator was fixed on their finding
(mid-stream supplier onboarding, ~15% legit bank changes, email-initiation on legit
wires raised to a realistic 55%, structuring amounts tightened to just-under-the-line)
and everything below is from the honest re-run.

## Honest results (37-day held-out window, 85 fraud wires, $6.0M fraud value)

| Metric | Cycle 9 (pre-red-team) | Cycle 10 (red-teamed + honest legit population) |
|---|---|---|
| Recall by value | 98.7% | **99.8%** |
| Recall by count | 95.7% | 97.7% |
| Largest missed wire | $22.3k | **$7.9k** |
| Precision | 14.5% | **5.8%** |
| Holds/day | 8.4 | 38.5 (36.3 false) |
| Human-release queue | 4.9/day | 3.0/day |
| Expected loss vs naive | 0.145 | 0.136 |

Per-variant recall (with cell sizes — small cells, wide error bars, per analyst):
bec_blatant 100% (n≈12) · bec_evasive 91.7% (n≈19) · bec_establish 93.3% (n≈16) ·
bec_fake_vendor 100% (n≈10) · ato_blatant 100% (n≈6) · ato_structuring 100% (n≈22).

## The structural finding (this cycle's real deliverable)
**BEC detection and onboarding friction are the same signal.** A fraudulent
beneficiary change and a legitimate one look identical at wire time — the model
correctly holds both. The 36 false holds/day are not model failure; they are the
beneficiary-change population that real wire desks route into a **callback-verification
control** (phone the supplier on an independently sourced number, Confirmation-of-Payee
matching, dual approval + cooling-off on first payments to new vendors). Per the
analyst: the model's job is to route wires into that workflow, not to win alone.
Expected loss still lands at 0.136 of naive with the review costs priced in.

## Red-team variants (attacker tradecraft per Cybersecurity/Analyst validation)
Account-establishment BEC (test invoice → wait a cycle → strike), fake-vendor
onboarding (hides in legit onboarding), structuring ATO (wires sized 88–99k to duck the
$100k human-release line). Counter-features: payer new-account velocity, 24h dollar
aggregation, amount-vs-account-history ratio.

## Open items from the analyst's report (next wire cycle's backlog)
1. **Ablation**: drop `is_email_initiated` + `session_behavior_score` and re-measure —
   quantifies how much recall is real structure vs remaining lab tells
2. **Window attacks**: red-team the counter-features' fixed 7d/24h windows (space new
   accounts >7d apart; spread wires >24h)
3. **Split establishment recall** into test-payment vs strike-payment (catching the
   strike is what matters)
4. Grow fraud injection counts so per-variant cells exceed ~50 rows
5. Missing playbook entries: supplier-aged mules, lookalike-name vendors, payroll-
   diversion BEC

## Channel scoreboard after Cycle 10
| Channel | Honest recall | Red-teamed |
|---|---|---|
| Cards | 92.4% system | Yes (Cycles 2–4) |
| P2P | 77.5% | Yes (Cycle 8) |
| Wire | 99.8% by value | Yes (this cycle) |
