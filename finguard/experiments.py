"""C2: Minimal experiment registry (D-015) — JSON-lines, no external services.

Every training/eval run appends one record so any two runs can be compared
reproducibly. Deliberately tiny; replaced by real MLOps tooling when that
workstream activates.

CLI:  python -m finguard.experiments list
      python -m finguard.experiments diff <run_id_a> <run_id_b>
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REGISTRY = Path("data/experiments.jsonl")


def content_hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:12]


def log_run(kind: str, params: dict, metrics: dict, tag: str = "") -> str:
    run_id = f"{kind}_{time.strftime('%Y%m%d_%H%M%S')}"
    rec = {"run_id": run_id, "kind": kind, "tag": tag,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "params_hash": content_hash(params), "params": params, "metrics": metrics}
    REGISTRY.parent.mkdir(exist_ok=True)
    with REGISTRY.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return run_id


def load_runs() -> list[dict]:
    if not REGISTRY.exists():
        return []
    return [json.loads(l) for l in REGISTRY.read_text().splitlines() if l.strip()]


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def diff(a_id: str, b_id: str):
    runs = {r["run_id"]: r for r in load_runs()}
    a, b = runs.get(a_id), runs.get(b_id)
    if not a or not b:
        print(f"unknown run id(s); known: {list(runs)}")
        return
    fa, fb = _flat(a["metrics"]), _flat(b["metrics"])
    keys = sorted(set(fa) | set(fb))
    w = max(len(k) for k in keys) + 2
    print(f"{'metric':<{w}}{a_id:>22}{b_id:>22}")
    for k in keys:
        va, vb = fa.get(k, "—"), fb.get(k, "—")
        fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)
        marker = "  *" if va != vb else ""
        print(f"{k:<{w}}{fmt(va):>22}{fmt(vb):>22}{marker}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        for r in load_runs():
            print(f"{r['run_id']}  kind={r['kind']}  tag={r['tag']}  params={r['params_hash']}")
    elif len(sys.argv) == 4 and sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
