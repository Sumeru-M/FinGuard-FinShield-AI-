"""C20 (D-052): model versioning/rollback + drift monitor."""

import numpy as np
import pandas as pd

from finguard import drift, model_registry


def _bundle(tag):
    return {"model": tag, "calibrator": None, "t_challenge": 0.1, "t_block": 0.4,
            "features": ["a", "b"]}


def test_publish_versions_and_rollback(tmp_path):
    d = tmp_path / "models"
    v1 = model_registry.publish(_bundle("m1"), {"recall": 0.80}, {"seed": 1}, models_dir=d)
    v2 = model_registry.publish(_bundle("m2"), {"recall": 0.90}, {"seed": 2}, models_dir=d)
    assert v1 != v2
    assert model_registry.get_current(d) == v2          # newest is current
    # content-addressed: same params+metrics -> same version, not a duplicate
    v2b = model_registry.publish(_bundle("m2"), {"recall": 0.90}, {"seed": 2}, models_dir=d)
    assert v2b == v2

    versions = model_registry.list_versions(d)
    assert {x["version"] for x in versions} == {v1, v2}
    assert [x["is_current"] for x in versions if x["version"] == v2] == [True]

    # rollback repoints current at the prior version — no retrain
    model_registry.rollback(v1, models_dir=d)
    assert model_registry.get_current(d) == v1
    assert model_registry.current_path(d).endswith(f"{v1}.pkl")


def test_psi_flags_shift_but_not_noise():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    same = rng.normal(0, 1, 5000)
    shifted = rng.normal(2.5, 1, 5000)          # clear distribution shift
    assert drift.classify(drift.psi(ref, same)) == "stable"
    assert drift.classify(drift.psi(ref, shifted)) == "major"


def test_feature_drift_report_identifies_the_drifting_column():
    rng = np.random.default_rng(1)
    ref = pd.DataFrame({"stable": rng.normal(0, 1, 3000),
                        "drifting": rng.normal(0, 1, 3000)})
    live = pd.DataFrame({"stable": rng.normal(0, 1, 3000),
                         "drifting": rng.normal(3, 1, 3000)})
    rep = drift.feature_drift(ref, live, ["stable", "drifting"])
    assert rep["overall"] == "major"
    assert "drifting" in rep["drifting_features"]
    assert "stable" not in rep["drifting_features"]
