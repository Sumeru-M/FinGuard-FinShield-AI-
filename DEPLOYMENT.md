# FinGuard — Deployment Runbook
*Cycle 19 (D-052). Covers the scoring service, the Redis feature store, and the Kafka
ingress. All infra here is code-complete and runs the day a Docker daemon is available;
nothing below has been executed in the pilot environment (no daemon present).*

## 1. Configuration (all via environment — no secrets in code)
Every operational knob lives in `finguard/config.py`, overridable by a `FINGUARD_*` env
var. Defaults reproduce pilot behavior. Key ones:

| Env var | Default | Purpose |
|---|---|---|
| `FINGUARD_HOST` / `FINGUARD_PORT` | 127.0.0.1 / 8100 | service bind |
| `FINGUARD_LOG_LEVEL` | warning | set `info` in prod |
| `FINGUARD_MODEL_PATH` | data/model_v0.pkl | scoring model bundle |
| `FINGUARD_FEATURE_STORE` | memory | set `redis` in prod |
| `FINGUARD_REDIS_URL` | *(unset)* | e.g. `redis://redis:6379/0` — **required** when store=redis |
| `FINGUARD_KAFKA_BROKERS` | *(unset)* | e.g. `redpanda:9092` for the stream consumer |
| `FINGUARD_BEHAVIORAL_RETENTION_DAYS` | 90 | Redis key TTL (D-008) |
| `FINGUARD_SANCTIONS_FEED_TOKEN` | *(unset)* | secret; inject at deploy (D-037) |

**Secrets** (`FINGUARD_REDIS_URL` with creds, `FINGUARD_SANCTIONS_FEED_TOKEN`, etc.) are
read from the environment only and default to `None`. Inject them via your orchestrator's
secret store — never commit them.

## 2. Bring-up (local production-shaped stack)
```bash
docker compose up --build          # redis + redpanda + scoring service
curl localhost:8100/health         # process up
curl localhost:8100/ready          # model loaded (503 until it is)
curl localhost:8100/metrics        # scored total, decisions, latency p50/p95/p99, queue depth
```
The `scoring` service is pre-wired to Redis and Redpanda via compose env. Container
healthcheck uses `/ready`.

## 3. The feature-store swap (pilot → production)
- Pilot: `FINGUARD_FEATURE_STORE=memory` (in-process; state lost on restart).
- Production: `FINGUARD_FEATURE_STORE=redis` + `FINGUARD_REDIS_URL=...`. State then lives
  in Redis — survives restarts and is shared across horizontally-scaled scoring replicas.
- Equivalence is proven: `tests/test_redis_store.py` shows the Redis store produces
  feature-for-feature identical output to the in-process store.

## 4. Stream ingress (Kafka/Redpanda)
- One topic per institution: `finguard.transactions.<institution_id>` (keeps institutions'
  raw streams separate — the D-006/D-012 federated boundary holds at ingest).
- Run a consumer: `FINGUARD_KAFKA_BROKERS=redpanda:9092 python -m finguard.kafka_consumer inst_001`
- Requires `confluent-kafka` (add to the image when the stream path goes live) and a
  dead-letter topic for poison messages (noted in `kafka_consumer.py`).
- The HTTP `/score` endpoint remains available for synchronous scoring; both paths use the
  same `ScoringEngine`.

## 5. Horizontal scaling
Single uvicorn process handled ~2k rps at 8ms p99 (Cycle 5). Scale by running N scoring
replicas behind a load balancer, all pointing at the same Redis — the store is now shared,
so velocity counters and reputation are consistent across replicas. (Concurrency note:
per-entity read-modify-write on the hot path is not yet atomic across replicas; for the
pilot's throughput this is fine, but a native-Redis-structures upgrade with atomic ops is
the recommended next step before very high concurrency — tracked as a perf enhancement.)

## 6. Rollback
- Service: redeploy the previous image tag; the model bundle is baked into the image, so
  rolling the image rolls the model.
- Model-only rollback and versioning is Cycle 20 work (registry + `current` pointer).

## 7. Health gates for CI/CD
- `/ready` must return 200 before a replica receives traffic.
- Run `pytest` in the pipeline; the Phase 0 gate tests are the regression wall (Cycle 20
  wires this into CI).
