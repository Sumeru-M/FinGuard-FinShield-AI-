# Cycle 15 Results — Controls Backlog, Privacy Accountant, Card Red-Team 2
**To: Owner | Executed under D-047 → D-049 | Date: 2026-07-23**
Three parallel tracks. Team Lead track test-covered (14/14 green); both agent tracks
independently produced and self-reporting under house rules (maker-checker inherent in
the split); no separate adversarial review ran this cycle — noted, not hidden.

## Track A — Controls backlog (Team Lead)
1. **D-047 per-wire floor ($10k) implemented.** Any wire above $10k to an unverified
   beneficiary is held regardless of cumulative. `bec_evasive` back to **100%**; the
   largest possible control-covered miss is now structurally bounded at **$9.9k**
   (just under the floor — measured, the worst miss in eval). Expected loss best-ever
   **0.107**.
2. **Escalation/override path.** Accounts whose callback fails get a manual
   verification review after 14 days (legit clears 90%, fraud 2%). The ~3% of legit
   suppliers formerly capped forever now have a route back. False holds **dropped to
   16.2/day** (C14: 18.6). Known residual: the 2% fraud-escalation-pass, documented.
3. **Disposition audit trail + role auth** (`scoring.py`). Every disposition requires
   an analyst identity; append-only audit table with prior-disposition visibility
   (overrides traceable); `/alerts/audit` endpoint; dashboard prompts once and handles
   401. Closes the Cycle-4 label-loop poisoning surface at pilot scale. New regression
   test; suite now 14 tests.

## Track B — Federation DP privacy accountant (DistSys agent)
`finguard/privacy_accountant.py`: basic + advanced (DRV10) composition; measured (not
extrapolated) pipeline utility at the composed per-round epsilons a 52-round year
implies under lifetime budgets of 10/50/100.
**The honest headline: weekly federation does not survive DP composition under ANY
tested lifetime budget** — utility collapses 43–68x at every composed per-round epsilon.
Viable paths, quantified: quarterly/semi-annual cadence buys ~5–10 total rounds over
2.5–5 years at eps_total=100; or a tighter accounting mechanism (RDP/moments — future
work); or a budget too large to mean much. Advanced composition is *worse* than basic
in the utility-relevant range (its correction term degenerates for eps0 ≥ ~1) — a
genuine technical finding. `FEDERATION_ORCHESTRATION.md` updated with the budget table.

## Track C — Card red-team round 2 (Data Science agent)
Four new variants with cross-channel tradecraft (opt-in in `datagen.py`; federation
callers unaffected). Per-variant recall (n, Wilson 95% CI):

| Variant | What it mimics | n | Recall |
|---|---|---|---|
| label_latency_ring | ring compressed inside the 24h label window | 53 | **100%** (real-time velocity features fire even when the label loop can't) |
| bust_out_synthetic | classic issuer bust-out (tenure gaming) | 55 | 92.7% |
| low_slow_profile | RAT on victim's own device, in-profile amounts/hours | 45 | 86.7% |
| **sleeper_device** | device with 20–40 days GENUINE history, then pivots | 52 | **61.5% (CI 48–74%)** |

Full-system: recall 85.6%, alerts 79.5/day (cap 200 PASS), latency p99 1.4ms (PASS),
cost 0.469 vs naive (PASS). Bias review clean (ratios 0.9–2.0).

**The finding that matters: `sleeper_device` beats the Cycle-4 reputation defense** —
a device with genuine legitimate history looks trusted because it *was* trusted. 20 of
52 sleeper frauds were approved outright. This is cards' analogue of P2P sleeper mules
and wire slow-establishment: tenure alone is not trust. Candidate counter-feature for
Cycle 16: cross-card diversity checks (a trusted device suddenly touching many new
cards is the pivot signal, regardless of its age).

**Statistical honesty (agent's own caveats):** blatant cell collapsed to n=8 this run
(prevalence rebalancing) — its 100% is not meaningful; sleeper's exact 61.5% has a wide
CI but the qualitative gap is solid. Methodology note recorded: scaling the dataset 4x
silently underfit the fixed-capacity model (AUC 0.99→0.66) — caught and avoided;
anyone growing the data must check in-sample AUC first.

## Needs-owner
1. **Federation cadence/budget** (from Track B): change round cadence to
   quarterly/semi-annual per the accountant's numbers, pursue RDP accounting first, or
   accept a weak-privacy large budget. This decides whether/how real federation runs.
2. **delta=1e-5** in the DP guarantee is a policy choice (acceptable failure chance of
   the epsilon guarantee) — rubber-stamp or set differently.
3. (Team-Lead-decidable, surfaced for visibility): prioritize the sleeper-device
   counter-feature (cross-card diversity) as Cycle 16's card work.
