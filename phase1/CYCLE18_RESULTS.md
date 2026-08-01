# Cycle 18 Results — Config + Observability + API Hardening
**To: Owner | Phase 2, D-052 | Date: 2026-07-24** | Team Lead solo, zero new dependencies

First cycle of Phase 2 (production-readiness). Goal: make the proven system operable and
shippable without changing any model behavior. Byte-identical results were a hard
requirement and are verified.

## Delivered
1. **`finguard/config.py`** — single source for every operational knob (service host/port,
   paths, hold TTL, all three channels' cost constants, wire cooling/floor/verify params,
   alert caps). Each overridable by a `FINGUARD_*` env var; defaults exactly match the
   pilot literals. `scoring.py`, `train.py`, `p2p.py`, `wire.py` now read from it.
   **Secrets policy enforced:** secret-bearing values (Redis URL, Kafka brokers, sanctions
   token) are env-only, default to `None`, never hardcoded.
2. **Observability on the scoring service** — `/health` (process up), `/ready` (model
   loaded, 503 if not), `/metrics` (scored total, decision counts, latency p50/p95/p99,
   alert-queue depth), and structured JSON request logging.
3. **API hardening** — bounded validation on every input field (amount ≥ 0, behavior
   score ∈ [0,1], timestamp parseable, id lengths); malformed input now returns 422, not
   a 500. Missing/corrupt model bundle degrades to a 503-not-ready service instead of
   crashing at startup.
4. **Tests** — suite grew 14 → 18: config defaults + live env override + secret-from-env,
   and a service test covering `/health`/`/ready`/`/metrics` + four hardening rejections.

## Verification (all green)
- `pytest`: **18 passed**.
- **Config is live, not cosmetic:** `FINGUARD_HOLD_TTL_HOURS=24` → engine's `HOLD_TTL`
  becomes 24h.
- **Byte-identical behavior confirmed** (the hard requirement): cards recall_at_alert
  0.8333, P2P 0.8443/0.8934, wire value-recall 0.9985 / largest-miss $9,910 — all
  unchanged from pre-refactor.
- **Live server smoke:** `/health`→ok, `/ready`→ready, `/metrics`→structured snapshot.

## Notes
- No new runtime dependencies (uses stdlib `logging` + existing FastAPI/pydantic; the
  test client rides the already-present httpx).
- One deprecation warning surfaced (Starlette TestClient/httpx) — cosmetic, noted, not
  addressed this cycle.

## Phase 2 remaining (roadmap, each re-proposed on completion)
- **Cycle 19** — real infra path: `RedisFeatureStore` (fakeredis-tested), Kafka consumer,
  docker-compose + Dockerfiles, `DEPLOYMENT.md`.
- **Cycle 20** — MLOps: model versioning/rollback, drift-monitor hooks, CI running the suite.

No new owner decisions required this cycle.
