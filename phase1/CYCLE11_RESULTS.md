# Cycle 11 Results — Wire Hardening v2 (maker-checker reviewed)
**To: Owner | Executed under D-034 | Date: 2026-07-20**
**Review gate:** Cybersecurity agent review (7 severity-ranked findings) applied before
publication; language below reflects their corrections.

## Headline (39-day held-out window, 233 fraud wires, $15.0M fraud value)

| Metric | Full model | Ablated (email + behavior + device dropped) |
|---|---|---|
| Recall by value | **99.8%** | **99.7%** |
| Recall by count | 98.7% | 98.3% |
| False holds/day | 23.6 | 23.2 |
| Expected loss vs naive | **0.110** | — |

## Per-variant recall (n's attached per review; None = no rows in eval window)

| Variant | n | Full | Ablated |
|---|---|---|---|
| bec_blatant | 29 | 100% | 100% |
| bec_evasive | 18 | 100% | 94.4% |
| bec_establish_test | 0 | — | — (all fell in train window; see F4 note) |
| bec_establish_strike | 37 | 100% | 100% |
| bec_establish_slow_test | 6 | 100% | 83.3% |
| **bec_establish_slow_strike** | 16 | **81.3%** | 87.5% |
| bec_fake_vendor | 20 | 100% | 100% |
| ato_blatant | 19 | 100% | 100% |
| ato_structuring | 60 | 100% | 100% |
| ato_structuring_slow | 28 | 100% | 100% |

## What this cycle established (with reviewer-corrected language)
1. **The ablation is consistent with low lab-tell dependence** — dropping all three
   suspected synthetic separators moves value-recall 0.1pt and leaves every structuring
   cell at 100%, so the load-bearing signals are structural (new-account velocity,
   unknown-supplier, tight-under-line amounts, account-history ratios). Per the review:
   this is strong evidence, not proof — the D-027 threshold is very permissive on large
   wires, which cushions ablation sensitivity.
2. **Structuring recall is against an incomplete evasion** (reviewer F2, verbatim
   caveat): the slow variant defeats the 24h window but not the 7d new-account
   counter — an attacker spacing accounts >7d apart and reusing one beneficiary is the
   un-run next iteration and would land in the frontier cell below.
3. **The honest frontier: slow-establishment strikes at 81.3%** (n=16, wide CI). The
   attack manufactures exactly the legitimacy the features measure. Reviewer and
   Cycle-10 analyst agree: the fix is a **process control** — cumulative-dollar cap /
   cooling-off on new beneficiary accounts until callback or Confirmation-of-Payee —
   not more features. This is wire's analogue of P2P's undetectable cell.
4. **Label-timing optimism noted (F4):** establishment test-payments train as labeled
   fraud, but in production they'd be unlabeled until after the strike — the 100%
   establish_strike cell is likely somewhat inflated. Next-cycle fix: delay
   establishment labels in training simulation.
5. **Registry hygiene fixed (F5):** wire runs were logging under tag "cycle9" with
   generator changes invisible to the params hash — corrected; variants + ablation set
   now recorded per run.
6. **Precision comparisons across cycles are partly mechanical (F6):** fraud counts
   grew this cycle, which raises precision by prevalence alone. False-holds/day is the
   honest comparable: 36.3 (C10) → 23.6 (C11).

## Needs-owner (flagged by review, not decided)
1. **New-beneficiary process control**: mandatory cooling-off/cumulative-cap until
   callback verification on any new beneficiary account — closes the 81.3% frontier
   cell but adds friction to every legitimate supplier change. Friction-vs-loss posture
   is yours to set.
2. **Release policy for held wires UNDER $100k** (D-028 family): currently undefined;
   the structuring variants target exactly that seam, and it intersects the
   analyst-poisoning surface (a hostile analyst could release sub-line structured
   wires). Options when you're ready: analyst-releasable with dual-control, or
   auto-expire holds with re-score.
3. Sanctions-feed authentication requirements before the real upstream integration
   (currently a trusting stub) — Cybersecurity backlog, needs prioritization.
