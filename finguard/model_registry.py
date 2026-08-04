"""Cycle 20 (D-052): model versioning, a `current` pointer, and rollback.

The pilot wrote a single `data/model_v0.pkl` — no history, no rollback. This registry
gives each trained bundle an immutable, content-addressed version and a movable `current`
pointer that the scoring service reads. Rollback is repointing `current` at any prior
version — no retraining, no redeploy of code.

Layout under models/ (configurable):
    models/
      v_<hash>.pkl        immutable bundle (model + calibrator + thresholds + features)
      v_<hash>.json       its metrics + params (sidecar, human-readable)
      current             a one-line pointer file naming the active version

Content-addressing: the version id is a hash of the bundle's params + metrics, so the
same training run is the same version and a changed run is a new one — reproducibility
and the experiment registry (`experiments.py`) stay consistent.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

from finguard.experiments import content_hash

MODELS_DIR = Path("models")


def _dir(models_dir=None) -> Path:
    d = Path(models_dir) if models_dir else MODELS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def publish(bundle: dict, metrics: dict, params: dict, models_dir=None,
            make_current: bool = True) -> str:
    """Write an immutable versioned bundle; optionally move `current` to it.
    Returns the version id."""
    d = _dir(models_dir)
    version = "v_" + content_hash(params, metrics)
    with open(d / f"{version}.pkl", "wb") as f:
        pickle.dump(bundle, f)
    with open(d / f"{version}.json", "w") as f:
        json.dump({"version": version, "params": params, "metrics": metrics},
                  f, indent=2, default=str)
    if make_current:
        set_current(version, models_dir)
    return version


def set_current(version: str, models_dir=None) -> None:
    d = _dir(models_dir)
    if not (d / f"{version}.pkl").exists():
        raise FileNotFoundError(f"no such version {version} in {d}")
    (d / "current").write_text(version + "\n")


def get_current(models_dir=None) -> str | None:
    p = _dir(models_dir) / "current"
    return p.read_text().strip() if p.exists() else None


def current_path(models_dir=None) -> str | None:
    """Absolute path to the currently-pointed bundle, or None if unset — this is what
    the scoring service loads."""
    v = get_current(models_dir)
    return str(_dir(models_dir) / f"{v}.pkl") if v else None


def list_versions(models_dir=None) -> list[dict]:
    d = _dir(models_dir)
    cur = get_current(models_dir)
    out = []
    for j in sorted(d.glob("v_*.json")):
        meta = json.loads(j.read_text())
        out.append({"version": meta["version"], "is_current": meta["version"] == cur,
                    "metrics": meta.get("metrics", {})})
    return out


def rollback(to_version: str, models_dir=None) -> str:
    """Repoint `current` at a prior version. No retraining, no code redeploy."""
    set_current(to_version, models_dir)
    return to_version
