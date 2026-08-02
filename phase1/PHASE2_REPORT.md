# Phase 2 — Production-Readiness (running report)
*The single report for Phase 2 (one report per phase, per owner directive). Updated each
cycle; becomes the phase's end-of-phase report on close. Phase 1's report is
`PILOT_CLOSING_REPORT.md`.*

Phase 2 takes the proven pilot from "works in-process on synthetic data" to "deployable,"
without changing any model behavior (byte-identical results are a hard requirement) and
without waiting on external gates. Decisions: D-052.

---

## Cycle 18 — Config + Observability + API hardening
- **`finguard/config.py`**: every operational knob (paths, host/port, hold TTL, all three
  channels' cost constants, wire controls, alert caps) centralized and `FINGUARD_*`
  env-overridable; defaults exactly match the pilot. Secrets (Redis/Kafka/sanctions) are
  env-only, default `None`, never hardcoded. `scoring.py`/`train.py`/`p2p.py`/`wire.py`
  read from it.
- **Observability** on the scoring service: `/health`, `/ready` (503 until model loads),
  `/metrics` (scored total, decision counts, latency p50/p95/p99, queue depth), structured
  JSON logging.
- **Hardening**: bounded input validation (amount ≥ 0, score ∈ [0,1], parseable timestamp)
  → 422 not 500; missing/corrupt model → 503 not crash.
- **Verified**: env override live (`FINGUARD_HOLD_TTL_HOURS=24` changes engine behavior);
  **byte-identical** channel results (cards 0.8333, P2P 0.8443/0.8934, wire 0.9985 / miss
  $9,910); live server smoke of all endpoints. Tests 14 → 18.

## Cycle 19 — Real infrastructure path
- **`finguard/redis_store.py`**: `RedisFeatureStore` subclasses the in-process store and
  reuses its exact computation (load touched entities → parent logic → write back →
  evict). State lives in Redis (survives restart, shared across replicas); feature values
  identical **by construction**.
- **`finguard/kafka_consumer.py`**: one topic per institution
  (`finguard.transactions.<inst>`, D-006/D-012 boundary at ingest); reuses the same
  `ScoringEngine`; lazy broker import so it ships now.
- **`Dockerfile` + `docker-compose.yml`**: scoring service + Redis + Redpanda, pre-wired,
  `/ready` healthcheck, no secrets baked in.
- **`DEPLOYMENT.md`**: config/secrets, bring-up, the store swap, stream ingress, scaling,
  rollback, CI health gates.
- **Config**: `FINGUARD_FEATURE_STORE` (memory|redis) + `FINGUARD_BEHAVIORAL_RETENTION_DAYS`
  (D-008 TTL); default stays memory.
- **Verified**: **21 tests pass** (18 + 3) incl. a feature-for-feature equivalence test
  (Redis vs in-memory on a fraud-containing stream), cross-instance persistence, and TTL;
  both new modules import with no daemon/library present; default backend unchanged.
- **Honest flags**: cross-replica read-modify-write not yet atomic (fine at pilot
  throughput; native-Redis-structures upgrade is the pre-high-concurrency enhancement);
  new deps `redis` (lazy) + `fakeredis` (test) pinned; `confluent-kafka` deferred to
  stream go-live. Infra is code-complete but **not executed** (no Docker daemon here).

## Cycle 20 — MLOps + CI  *(pending)*
- Model versioning/rollback (registry + `current` pointer, building on `experiments.py`),
  drift-monitor hooks, CI running the test suite (Phase 0 gates as the regression wall).

---
*Phase 2 status: 2 of 3 cycles complete. No open owner decisions.*
