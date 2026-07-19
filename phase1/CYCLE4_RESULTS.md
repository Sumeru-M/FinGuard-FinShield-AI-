# Cycle 4 Results — Label Loop + Investigator Dashboard
**To: Owner | Executed under D-020 | Date: 2026-07-19**

## Full-system comparison (adversarial v2 data, same 10-day held-out window)

| Metric | Cycle 3 | Cycle 4 | Direction |
|---|---|---|---|
| Recall (system) | 89.4% | **92.4%** | best yet |
| — evasive variants | 85.1% | **89.4%** | up |
| — evasive CNP by type (the target) | 71.4% | **90.5%** | **+19pts** |
| Precision | 48.8% | 46.2% | ~flat |
| Alerts/day | 12.1 | 13.2 | ~flat (cap 200) |
| False hard-blocks (10 days) | 1 | 2 | ~flat |
| Cost vs naive | 0.183 | **0.172** | best yet |
| Latency p99 | 0.42ms | 0.44ms | flat |

All Phase 0 exit gates PASS. Model-only (before hold-flooring): recall 83.3%,
precision 93.2%.

## What Cycle 4 changed
1. **Label-loop reputation features** (`finguard/features.py`, now 26 features): analyst
   confirmations become model features — device/card/merchant links to confirmed fraud.
   Point-in-time correct with a 24h label latency (a confirmation is invisible to scoring
   until a day after the fraud event; no oracle labels). This was the lever that finally
   cracked evasive CNP: a fraudster can mimic a victim's spending, but the device that
   defrauded one card yesterday is reputation-poisoned when it touches the next card.
2. **Live loop wired** (`finguard/scoring.py`): dashboard/API dispositions of
   `confirmed_fraud_*` mark reputation in the running feature store immediately;
   `confirmed_legitimate` clears the card's investigation hold. The loop is closed in
   both directions.
3. **Investigator dashboard** (`/dashboard`, `finguard/static/dashboard.html`): dual-lane
   queue per the Cycle 2 recommendation — full-review lane for model-driven alerts,
   lighter-touch lane for hold-floored activity on already-flagged cards. Each alert
   renders the D-011 payload (risk score, decision badge, ranked top-features with
   contribution bars) and one-click dispositions. Verified end-to-end in a live browser:
   click → API → SQLite → reputation store.

## Honest caveats
- **Offline simulation is optimistic about label coverage**: the feature build assumes
  every fraud row is confirmed within 24h; in production only alerted/disputed fraud gets
  a disposition, so reputation coverage will be thinner. The live path only marks what
  analysts actually confirm — the gap is in the offline training simulation, and closing
  it (train-time simulation of alert-conditional labeling) is future work.
- **Reputation features create a poisoning surface**: a hostile/compromised analyst
  account could mark legitimate devices as fraud-linked. Fine at pilot scale; needs
  disposition audit-trail + role auth before real deployment (Cybersecurity backlog item).
- Precision (46.2%) is still hold-flooring-dominated — by design, pending the D-011
  analyst-format review which now has a real interface to review against.

## D-011 trigger now actionable
The alert format can finally be reviewed on a real interface at `/dashboard`
(`python -m finguard.scoring`, then open http://127.0.0.1:8100/dashboard). Owner may act
as the Fraud Analyst reviewer or defer — format freeze awaits that pass.
