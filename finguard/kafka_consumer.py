"""Cycle 19 (D-052): Kafka/Redpanda transaction consumer — the production ingress.

In the pilot, transactions arrive via the HTTP /score endpoint. In production the
high-volume path is a stream: a Kafka (or Redpanda — Kafka-API-compatible) topic per
institution feeds this consumer, which scores each message and emits any alert.

This module is written and import-safe with NO broker and NO kafka library installed
(the import is lazy, inside run()), so it ships now and runs the day a broker exists —
consistent with the D-052 "code-complete, daemon-free" scope. It is intentionally thin:
the scoring logic is the exact same ScoringEngine used by the HTTP service, so there is
one code path for both ingress modes.

Institution scoping (D-006/D-012): one topic per institution, so an institution's raw
stream never mixes with another's — the federated-ready boundary holds at ingest.

Run (when a broker is available):
    FINGUARD_KAFKA_BROKERS=localhost:9092 python -m finguard.kafka_consumer inst_001
"""

from __future__ import annotations

import json
import sys

from finguard.config import cfg


def _topic(institution_id: str) -> str:
    return f"finguard.transactions.{institution_id}"


def run(institution_id: str, brokers: str | None = None):
    brokers = brokers or cfg.kafka_brokers
    if not brokers:
        raise RuntimeError("no Kafka brokers configured (set FINGUARD_KAFKA_BROKERS)")

    # lazy imports so the module is safe to import without these installed
    from confluent_kafka import Consumer  # type: ignore
    from finguard.scoring import AlertQueue, ScoringEngine, _T, TxnIn

    engine = ScoringEngine()
    queue = AlertQueue()
    consumer = Consumer({
        "bootstrap.servers": brokers,
        "group.id": f"finguard-scorer-{institution_id}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })
    consumer.subscribe([_topic(institution_id)])
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue
            try:
                txn = TxnIn(**json.loads(msg.value()))
                result = engine.score(_T(txn))
                if "alert" in result:
                    queue.push(result["alert"])
            except Exception:  # noqa: BLE001 - a poison message must not kill the consumer
                # production: route to a dead-letter topic + increment an error metric
                continue
    finally:
        consumer.close()


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "inst_001"
    run(inst)
