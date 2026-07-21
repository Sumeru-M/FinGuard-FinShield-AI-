"""Cycle 14 (D-046 track b): output-level DP mitigation for the Cycle 6 federation
leakage caveat.

Cycle 6 (`finguard/federation.py`) proved federation helps every institution, but
flagged a real leak: the artifact that crosses the institution boundary is the raw
LightGBM model, and tree split thresholds can encode real training-data values
(e.g. "amount > 1042.37" is a fact about someone's real transaction). D-006 is
absolute — no raw data, no features, no store state ever crosses institutions —
and an un-mitigated model exchange violates its spirit even though no *rows* move.

This module never shares a raw institution model. It shares two things instead,
both safe under D-006:

1. A **surrogate model distilled on a public, synthetic, non-institution probe
   set.** Every institution scores the same shared probe set (generated once,
   below, owned by nobody) and every OTHER institution fits a small model that
   predicts THOSE probe scores. The surrogate's split thresholds are therefore
   facts about the probe set, not about any real transaction ever seen by any
   institution — the Cycle 6 leak path is structurally closed, not just
   obscured.
2. Those probe scores are additionally perturbed with calibrated Laplace noise
   before release (epsilon-DP on the [0,1]-bounded probability, sensitivity=1),
   so even the numeric answers ("this probe transaction scored 0.83") don't
   pin down a peer's exact decision surface.

Honesty note on the DP accounting: this is a single-release, per-coordinate
Laplace mechanism against a *bounded output* (probabilities in [0,1], so
sensitivity=1 for a single record's answer). It is NOT a full composed
per-institution epsilon across a lifetime of releases — that requires a
privacy accountant and a real deployment cadence (see the orchestration doc's
"Future hardening" section). Treat epsilon here as a per-round dial, not a
lifetime budget.

Imports INSTITUTIONS / build_institution / fed_score's sibling pieces from
finguard.federation — this module is additive, federation.py is untouched.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from finguard import datagen
from finguard.features import FEATURE_COLUMNS, build_feature_frame
from finguard.federation import INSTITUTIONS, build_institution, train_local, evaluate
from finguard.train import COST_FN
import hashlib


def _seed_for(*parts) -> int:
    """Deterministic seed from arbitrary parts — Python's built-in hash() on
    strings is randomized per-process (PYTHONHASHSEED) and would break the
    fixed-seed house rule, so this uses a stable hash instead."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)

# A probe set nobody owns: distinct seed from every institution in INSTITUTIONS,
# generated once and shared identically with all parties out-of-band (this is
# public/synthetic exactly like the rest of the pilot's data — no real records
# ever populate it in a real deployment; a consortium would agree a fixed
# non-sensitive reference set instead).
PROBE_CFG = {"cards": 600, "days": 30, "seed": 90210, "evasive_share": 0.55}


# NOTE on this choice: sensitivity here is 1 over a [0,1]-bounded output, i.e.
# the "sensitizing range" already equals the whole answer range. That is a
# much harsher setting than the typical DP tutorial example (large-range
# numeric queries), so epsilon=1 style values that "sound standard" are
# actually enormous relative to the signal and destroy it outright (measured
# below). The sweep below deliberately spans from utility-preserving to
# utility-destroying so the transition is visible rather than picking one
# flattering point.
EPSILONS = [50.0, 20.0, 10.0, 5.0, 1.0]  # smaller epsilon = more noise = more privacy
SURROGATE_PARAMS = dict(n_estimators=60, num_leaves=7, max_depth=3, learning_rate=0.1)


def build_probe_set() -> pd.DataFrame:
    df = datagen.generate(PROBE_CFG["cards"], PROBE_CFG["days"], 0.002,
                          PROBE_CFG["seed"], PROBE_CFG["evasive_share"])
    ff = build_feature_frame(df)
    return ff[FEATURE_COLUMNS]


def dp_noise(rng: np.random.Generator, n: int, epsilon: float | None) -> np.ndarray:
    """Laplace mechanism, sensitivity=1 (probabilities bounded to [0,1]).
    epsilon=None means no noise (distillation-only variant, for isolating the
    distillation cost from the noise cost)."""
    if epsilon is None:
        return np.zeros(n)
    return rng.laplace(loc=0.0, scale=1.0 / epsilon, size=n)


def share_probe_predictions(artifact: dict, X_probe: pd.DataFrame,
                            epsilon: float | None, seed: int) -> np.ndarray:
    """What actually crosses the institution boundary: a noisy probability
    vector over the shared probe set. Never the model, never real rows."""
    from finguard.core import score_calibrated
    raw = score_calibrated(artifact["model"], artifact["calibrator"], X_probe)
    rng = np.random.default_rng(seed)
    noisy = raw + dp_noise(rng, len(raw), epsilon)
    return np.clip(noisy, 0.0, 1.0)


def distill_surrogate(X_probe: pd.DataFrame, noisy_probe_scores: np.ndarray, seed: int):
    """Fits a small regressor that maps probe features -> a peer's (noisy)
    scores. This is the only object standing in for the peer model locally;
    its splits are facts about the shared probe set only."""
    import lightgbm as lgb
    reg = lgb.LGBMRegressor(random_state=seed, verbose=-1, **SURROGATE_PARAMS)
    reg.fit(X_probe, noisy_probe_scores)
    return reg


def fed_score_dp(own_artifact: dict, peer_surrogates: list, X: pd.DataFrame) -> np.ndarray:
    """Ensemble analogue of federation.fed_score: own real calibrated score,
    averaged with every peer's DISTILLED surrogate score (never their raw
    model) evaluated on local features. Local features never leave the
    institution — only the surrogate's .predict runs locally against them."""
    from finguard.core import score_calibrated
    own_score = score_calibrated(own_artifact["model"], own_artifact["calibrator"], X)
    peer_scores = [np.clip(s.predict(X), 0.0, 1.0) for s in peer_surrogates]
    return np.mean([own_score] + peer_scores, axis=0)


def run_round(insts, artifacts, X_probe, epsilon: float | None) -> dict:
    """One full DP-mitigated federation round: every institution shares noisy
    probe predictions, every OTHER institution distills a surrogate from them,
    every institution re-scores its own local test set with the mitigated
    ensemble."""
    from finguard.core import score_calibrated
    probe_shares = {
        iid: share_probe_predictions(art, X_probe, epsilon, seed=_seed_for(iid, epsilon))
        for iid, art in artifacts.items()
    }
    surrogates = {
        iid: distill_surrogate(X_probe, scores, seed=_seed_for(iid, "surrogate"))
        for iid, scores in probe_shares.items()
    }
    noise_magnitude = {
        iid: float(np.mean(np.abs(
            probe_shares[iid] -
            score_calibrated(artifacts[iid]["model"], artifacts[iid]["calibrator"], X_probe))))
        for iid in artifacts
    }

    report = {}
    for inst in insts:
        iid = inst["id"]
        te = inst["test"]
        X, y = te[FEATURE_COLUMNS], te["y"].values
        own = artifacts[iid]
        peer_surrogates = [s for pid, s in surrogates.items() if pid != iid]

        fed_dp_score = fed_score_dp(own, peer_surrogates, X)
        report[iid] = {
            "test_rows": len(te),
            "federated_dp": evaluate(y, fed_dp_score, own["t_chal"], own["t_block"]),
            "mean_abs_probe_noise": round(noise_magnitude[iid], 4),
        }
    return report


CYCLE6_BASELINE = {
    # From phase1/CYCLE6_RESULTS.md — raw-model federation, no mitigation.
    "inst_001": {"recall_local": 0.404, "recall_fed": 0.808, "cost_fed": 0.310},
    "inst_002": {"recall_local": 0.563, "recall_fed": 0.938, "cost_fed": 0.143},
    "inst_003": {"recall_local": 0.333, "recall_fed": 0.500, "cost_fed": 0.603},
}


def main():
    insts = [build_institution(c) for c in INSTITUTIONS]
    artifacts = {i["id"]: train_local(i) for i in insts}
    X_probe = build_probe_set()

    all_results = {}
    # distill_only = surrogate distillation with epsilon=None (no DP noise) —
    # isolates "cost of distilling instead of using the raw model" from
    # "cost of adding privacy noise on top of that".
    for label, eps in [("distill_only", None)] + [(f"epsilon_{e}", e) for e in EPSILONS]:
        all_results[label] = run_round(insts, artifacts, X_probe, eps)

    summary_table = []
    for iid in artifacts:
        base = CYCLE6_BASELINE[iid]
        row = {"institution": iid, "cycle6_recall_local": base["recall_local"],
               "cycle6_recall_fed_raw_model": base["recall_fed"],
               "cycle6_cost_fed_raw_model": base["cost_fed"]}
        for label in all_results:
            m = all_results[label][iid]["federated_dp"]
            row[f"{label}_recall"] = m["recall"]
            row[f"{label}_precision"] = m["precision"]
            row[f"{label}_cost"] = m["cost_vs_naive"]
            row[f"{label}_mean_abs_noise"] = all_results[label][iid]["mean_abs_probe_noise"]
        summary_table.append(row)

    print(json.dumps({"per_round": all_results, "summary": summary_table}, indent=2))
    with open("data/federation_dp_report.json", "w") as f:
        json.dump({"per_round": all_results, "summary": summary_table}, f, indent=2)

    from finguard.experiments import log_run
    log_run("federation_dp",
            params={"institutions": INSTITUTIONS, "probe_cfg": PROBE_CFG,
                    "epsilons": EPSILONS, "surrogate_params": SURROGATE_PARAMS},
            metrics={"per_round": all_results, "cycle6_baseline": CYCLE6_BASELINE},
            tag="cycle14_fed_dp")


if __name__ == "__main__":
    main()
