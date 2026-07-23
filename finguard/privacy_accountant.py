"""Cycle 15 (D-049 track b): formal privacy accountant for the federation DP layer.

Cycle 14 (`finguard/federation_dp.py`) built a per-round Laplace mechanism and its
own honesty note flagged the gap this module closes: "epsilon here is a per-round
dial, not a lifetime budget... a real deployment needs a privacy accountant before
rounds run indefinitely." This module supplies that accounting and then MEASURES
(re-running the Cycle 14 pipeline, not extrapolating) whether federation survives it.

Two composition methods are implemented for a lifetime budget eps_total spent over
`k` independent per-round Laplace releases, each spending eps0 (pure eps-DP, no
per-mechanism delta since Laplace releases here are pure-DP):

1. Basic (linear/sequential) composition — exact, no assumptions:
       eps_total = k * eps0        =>   eps0 = eps_total / k
   This is the textbook worst-case bound and always valid.

2. Advanced ("strong") composition — Dwork, Rothblum, Vadhan 2010, Theorem III.3
   (k-fold adaptive composition of eps0-DP mechanisms is (eps', delta')-DP for any
   delta' > 0, with
       eps' = eps0 * sqrt(2 k ln(1/delta')) + k * eps0 * (exp(eps0) - 1)
   ). We fix a target delta' (default 1e-5, standard "cryptographically small"
   choice, i.e. much smaller than 1/(number of institutions) so a single-institution
   privacy failure is not "expected" over the deployment horizon) and invert this
   monotonically-increasing-in-eps0 function numerically (binary search) to find the
   largest eps0 whose exact bound does not exceed eps_total. This is looser than
   basic composition for small k and tighter (permits larger eps0) once k grows,
   which is the whole point of using it — the honesty tradeoff is a nonzero delta'
   (a small probability the epsilon' guarantee doesn't hold) instead of composition's
   free lunch.

Both are reported side by side; advanced composition is optimistic (bigger eps0,
less noise) and basic is the conservative floor. Neither is "the" DP accountant used
by mature libraries (e.g. RDP/moments-accountant style, which would do better still)
— that's flagged as future work below, not built here, because the honest finding
(section 3) makes it moot: even the optimistic bound collapses utility at realistic
lifetime budgets and cadences.
"""

from __future__ import annotations

import json
import math

DEFAULT_DELTA = 1e-5  # standard small-delta choice for strong composition


# ---------------------------------------------------------------------------
# 1. Composition accounting
# ---------------------------------------------------------------------------

def basic_composition_eps0(eps_total: float, k: int) -> float:
    """Exact, no assumptions: eps_total = k * eps0."""
    if k <= 0:
        raise ValueError("k must be positive")
    return eps_total / k


def _strong_composition_bound(eps0: float, k: int, delta: float) -> float:
    """The exact DRV10 bound: total eps' spent by k adaptive eps0-DP releases,
    at slack delta. Monotonically increasing in eps0 for eps0 >= 0."""
    return eps0 * math.sqrt(2 * k * math.log(1.0 / delta)) + k * eps0 * (math.exp(eps0) - 1.0)


def advanced_composition_eps0(eps_total: float, k: int, delta: float = DEFAULT_DELTA) -> float:
    """Invert the strong composition bound for the largest eps0 such that k
    adaptive eps0-DP releases stay within eps_total total (at slack delta).
    Binary search: the bound is 0 at eps0=0 and strictly increasing, so this is
    a straightforward monotone root-find."""
    if k <= 0:
        raise ValueError("k must be positive")
    lo, hi = 0.0, eps_total  # eps0 can never need to exceed eps_total itself
    # widen hi until the bound overshoots eps_total (guards tiny-k / huge-budget cases)
    while _strong_composition_bound(hi, k, delta) < eps_total:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if _strong_composition_bound(mid, k, delta) <= eps_total:
            lo = mid
        else:
            hi = mid
    return lo


def rounds_for_target_eps0(eps_total: float, eps0_target: float,
                           delta: float = DEFAULT_DELTA, method: str = "advanced") -> float:
    """Inverse question: given a lifetime budget and a per-round epsilon you
    actually need for utility, how many rounds can you afford before the
    composed budget is exhausted? Real-valued (caller floors for a round count).
    """
    if method == "basic":
        return eps_total / eps0_target
    # advanced: find largest k such that _strong_composition_bound(eps0_target, k, delta) <= eps_total
    lo, hi = 0.0, 1.0
    while _strong_composition_bound(eps0_target, int(hi), delta) < eps_total:
        hi *= 2
        if hi > 1e9:
            break
    for _ in range(100):
        mid = (lo + hi) / 2
        if _strong_composition_bound(eps0_target, max(int(mid), 1), delta) <= eps_total:
            lo = mid
        else:
            hi = mid
    return lo


# ---------------------------------------------------------------------------
# 2. Budget table: eps_total x horizon(rounds) -> per-round eps0 under each method
# ---------------------------------------------------------------------------

EPS_TOTALS = [10.0, 50.0, 100.0]
HORIZONS_ROUNDS = [26, 52, 104]  # weekly cadence: ~6mo / 1yr / 2yr
CADENCE_LABEL = {26: "26 rounds (weekly x 6mo)",
                 52: "52 rounds (weekly x 1yr)",
                 104: "104 rounds (weekly x 2yr)"}


def build_budget_table(eps_totals=EPS_TOTALS, horizons=HORIZONS_ROUNDS,
                       delta: float = DEFAULT_DELTA) -> list[dict]:
    rows = []
    for eps_total in eps_totals:
        for k in horizons:
            basic = basic_composition_eps0(eps_total, k)
            advanced = advanced_composition_eps0(eps_total, k, delta)
            rows.append({
                "eps_total": eps_total, "rounds": k, "cadence": CADENCE_LABEL[k],
                "delta": delta,
                "basic_eps0": round(basic, 4),
                "advanced_eps0": round(advanced, 4),
            })
    return rows


# ---------------------------------------------------------------------------
# 3. Utility measurement at the implied per-round epsilons
# ---------------------------------------------------------------------------

def measure_utility_at_eps0(eps0_values: list[float]) -> dict:
    """Actually runs the Cycle 14 pipeline (federation_dp.run_round) at each
    given per-round epsilon — MEASURED, not interpolated from the Cycle 14
    report's discrete sweep (which used 50/20/10/5/1, not these composed values).
    """
    from finguard.federation_dp import (INSTITUTIONS, build_institution, train_local,
                                        build_probe_set, run_round)
    insts = [build_institution(c) for c in INSTITUTIONS]
    artifacts = {i["id"]: train_local(i) for i in insts}
    X_probe = build_probe_set()

    results = {}
    for eps0 in eps0_values:
        key = f"eps0_{eps0:.4f}"
        results[key] = run_round(insts, artifacts, X_probe, eps0)
    return results


def main():
    delta = DEFAULT_DELTA
    table = build_budget_table(delta=delta)
    print("Per-round epsilon implied by a lifetime budget (weekly cadence)")
    print(f"{'eps_total':>10} {'rounds':>7} {'basic_eps0':>12} {'advanced_eps0':>14}")
    for row in table:
        print(f"{row['eps_total']:>10.0f} {row['rounds']:>7} "
              f"{row['basic_eps0']:>12.4f} {row['advanced_eps0']:>14.4f}")

    # --- Utility measurement at the 52-round (1yr, weekly) horizon for every
    # budget, both composition methods. These are the exact eps0 values a real
    # weekly-cadence, 1-year deployment would have to run at. ---
    year_rows = [r for r in table if r["rounds"] == 52]
    eps0_to_measure = sorted(set(
        [r["basic_eps0"] for r in year_rows] + [r["advanced_eps0"] for r in year_rows]))
    print(f"\nMeasuring Cycle-14 pipeline utility at composed eps0 values: {eps0_to_measure}")
    measured = measure_utility_at_eps0(eps0_to_measure)

    # Cycle 14's own sweep found eps>=20 preserves near-baseline precision, eps=10
    # already visibly degrades precision for the large institution, eps<=5
    # destroys precision entirely (0.006-0.011). Use eps0=20 and eps0=10 as the
    # "utility-preserving" and "marginal" reference thresholds respectively when
    # asking the inverse question below.
    UTILITY_THRESHOLDS = {"utility_preserving": 20.0, "marginal": 10.0}

    # --- Inverse question: what cadence (round count) or what budget makes a
    # eps0=10 or eps0=20 per-round spend affordable, for each candidate lifetime
    # budget, under advanced composition (the optimistic bound)? ---
    cadence_answers = []
    for eps_total in EPS_TOTALS:
        for label, eps0_target in UTILITY_THRESHOLDS.items():
            k_adv = rounds_for_target_eps0(eps_total, eps0_target, delta, method="advanced")
            k_basic = rounds_for_target_eps0(eps_total, eps0_target, delta, method="basic")
            cadence_answers.append({
                "eps_total": eps_total, "eps0_target": eps0_target, "target_label": label,
                "max_rounds_advanced": round(k_adv, 2),
                "max_rounds_basic": round(k_basic, 2),
                "weekly_cadence_equiv_years_advanced": round(k_adv / 52, 3),
            })

    print("\nInverse: rounds affordable at a utility-preserving/marginal per-round eps0")
    print("  NOTE: at eps0=10-20 the DRV10 strong-composition bound's second term")
    print("  k*eps0*(exp(eps0)-1) is enormous (exp(10)~22000) and dominates the bound")
    print("  even at k=1 -- the 'advanced' method is only tighter than basic for")
    print("  small eps0 (roughly eps0 << 1/sqrt(k)); at utility-relevant eps0 it is")
    print("  DEGENERATE (reports ~0 affordable rounds) and basic composition is the")
    print("  only usable accounting tool. This is itself a finding, not a bug.")
    for row in cadence_answers:
        print(f"  eps_total={row['eps_total']:>5.0f}  target={row['target_label']:>18} "
              f"(eps0={row['eps0_target']:>4.1f})  "
              f"max_rounds(advanced)={row['max_rounds_advanced']:>7.2f}  "
              f"max_rounds(basic)={row['max_rounds_basic']:>7.2f}")

    out = {
        "delta": delta,
        "budget_table": table,
        "eps0_values_measured": eps0_to_measure,
        "measured_utility": measured,
        "cadence_inverse": cadence_answers,
        "utility_reference_thresholds": UTILITY_THRESHOLDS,
        "advanced_composition_degeneracy_note": (
            "At utility-relevant eps0 (10-20), the DRV10 strong composition "
            "bound's exp(eps0) term dominates and the bound already exceeds "
            "small/medium lifetime budgets at k=1 -- 'advanced' composition is "
            "only an improvement over basic for small eps0 (roughly eps0 << "
            "1/sqrt(k)); at eps0=10-20 it is degenerate (reports ~0 affordable "
            "rounds) and basic composition is the only usable accounting tool "
            "for the cadence-viability question below."
        ),
        "cycle14_reference_sweep_note": (
            "Cycle 14 (data/federation_dp_report.json) swept eps in "
            "[50, 20, 10, 5, 1] per round with NO composition (single-release "
            "framing). eps>=20 ~ near-baseline precision; eps=10 already visibly "
            "degrades precision for the largest institution (0.36-0.70 vs "
            "0.40-0.88 unnoised); eps<=5 destroys precision (0.006-0.044, "
            "cost_vs_naive 5x-70x worse than naive)."
        ),
    }
    with open("data/privacy_accountant_report.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    from finguard.experiments import log_run
    log_run("privacy_accountant",
            params={"eps_totals": EPS_TOTALS, "horizons_rounds": HORIZONS_ROUNDS,
                    "delta": delta, "eps0_values_measured": eps0_to_measure,
                    "utility_reference_thresholds": UTILITY_THRESHOLDS},
            metrics={"budget_table": table, "measured_utility": measured,
                     "cadence_inverse": cadence_answers},
            tag="cycle15_privacy")

    print("\nWrote data/privacy_accountant_report.json, logged to experiment registry "
          "(tag=cycle15_privacy).")


if __name__ == "__main__":
    main()
