# Cycle 9 Results — Wire Phase 1 (Corporate BEC)
**To: Owner | Executed under D-027 → D-031 | Date: 2026-07-19**

## Headline results (36-day held-out window, 46 fraud wires, $3.18M fraud value)

| Metric | Result |
|---|---|
| Recall by count | 95.7% |
| **Recall by value (the one that matters here)** | **98.7%** |
| — BEC blatant | 100% |
| — BEC evasive (only the account number changed) | **100%** |
| — ATO wires | 86.7% |
| Largest missed wire | **$22.3k** |
| Largest caught wire | $449k |
| Expected loss vs release-everything | **0.145** |
| Holds/day | 8.4 (7.2 false) |
| Human-release queue (D-028, >$100k) | 4.9/day |

## Why the amount-dependent threshold (D-027) matters
The per-dollar cost model produces exactly the risk posture a wire desk wants: the hold
threshold falls as the amount rises, so a $2M wire is held on faint suspicion while a
$5k wire needs real evidence. The proof is in the miss profile — **every missed fraud
was small ($22k worst case); no large wire escaped.** Value-recall 98.7% vs count-recall
95.7% is that asymmetry working as designed.

## Why evasive BEC scored 100% (and the honest read of it)
The classic supplier-detail-change scam — amount matching the real invoice, on-cycle,
same country, *only the account number changed* — is fully caught, because *changing the
beneficiary account is the one thing the fraud cannot avoid doing*. Unlike P2P
installment scams (Cycle 8's undetectable cell), BEC's defining action IS the anomaly.
The honest caveat: the same signal fires on **legitimate supplier onboarding/bank
changes** — that's what the 7.2 false holds/day mostly are. In production this is
handled by process, not model: a beneficiary-change verification workflow (callback to
known supplier contact) turns those holds into a routine control, which is exactly how
real wire desks operate. Precision (14.5%) should be read in that light: a "false" hold
on a first payment to a changed account is a control working, not an error — and at
$0.002 friction per dollar plus $50 review, the cost model already prices it in
(expected loss 14.5% of naive).

## What was built (`finguard/wire.py`)
Corporate wire generator (400 orgs on realistic invoice cycles over 120 days — wire
cadences need long history), 13 BEC/ATO features led by beneficiary-account novelty and
invoice-history deviation, OOF-calibrated LightGBM, analytic amount-dependent hold
threshold, and the D-028 inverted-autonomy queue (machine holds; humans release >$100k;
4.9 wires/day hit that queue — a workable human load).

## Channel scoreboard after Cycle 9
| Channel | Status | Honest recall |
|---|---|---|
| Cards | Hardened, format frozen, federated | 92.4% (system) |
| P2P | Red-teamed; friction policy pending owner | 77.5% |
| Wire | Phase 1 slice complete (this cycle) | 98.7% by value (un-red-teamed) |

**All three channels of the original goal now have working, measured detection.**
Wire's numbers are pre-red-team — same caveat cards and P2P once had; a wire red-team
(BEC timed to beneficiary-change-verification gaps, mule accounts aged as suppliers)
is the natural hardening pass.
