"""Cycle 19 (D-052): Redis-backed feature store — the production swap for the
in-process store, behind the identical interface.

Design choice (equivalence-by-construction, not a re-implementation): RedisFeatureStore
SUBCLASSES InMemoryFeatureStore and reuses its exact feature-computation and update
logic. Per transaction it loads only the touched entities' rolling state from Redis into
the inherited dicts, runs the parent's `features_for`/`update`, writes those entities
back to Redis, and evicts them from local memory. So:
  - feature values are guaranteed identical to the pilot store (same code path — proven
    by the equivalence test in tests/test_redis_store.py), and
  - state actually lives in Redis: it survives process restart and is shared across
    horizontally-scaled scoring replicas (the whole point of the swap).

The client is duck-typed (get/set/delete/pipeline) so `fakeredis` drives the tests with
no daemon, and real `redis.Redis` drives production unchanged. Per-entity values are
small; we pickle each and store one Redis key per (attribute, entity). A native-Redis-
structures optimization (sorted sets + ZREMRANGEBYSCORE for windows) is a future perf
enhancement — not needed for correctness or the pilot's throughput.

Retention: optional `ttl_seconds` sets an expiry on every written key, aligning the
store with the D-008 behavioral-data retention rule when desired.
"""

from __future__ import annotations

import pickle

from finguard.features import InMemoryFeatureStore

# State attributes grouped by which entity key indexes them.
_CARD_ATTRS = ["card_times", "card_amounts", "card_devices", "card_merchants",
               "card_countries", "card_amt_stats", "card_hour_vec", "card_amt_sq",
               "card_fraud_marks"]
_MERCH_ATTRS = ["merchant_times", "merchant_stats", "merchant_fraud_marks"]
_DEV_ATTRS = ["device_cards", "device_first_seen", "device_all_cards",
              "device_fraud_marks"]
_PAIR_ATTRS = ["pair_first_seen"]


class RedisFeatureStore(InMemoryFeatureStore):
    def __init__(self, client, ttl_seconds: int | None = None, prefix: str = "fs:"):
        super().__init__()
        self.r = client
        self.ttl = ttl_seconds
        self.prefix = prefix

    # --- key plumbing -------------------------------------------------------
    def _rk(self, attr: str, dictkey) -> str:
        # pair keys are tuples (device_key, card_id) -> flatten deterministically
        if isinstance(dictkey, tuple):
            dictkey = "|".join(dictkey)
        return f"{self.prefix}{attr}:{dictkey}"

    def _touched(self, ck=None, mk=None, dk=None, pk=None, only=None):
        """Yield (attr, dictkey) pairs for the entities this op touches.
        `only` restricts to a subset of attributes (used by mark_confirmed_fraud)."""
        groups = [(_CARD_ATTRS, ck), (_MERCH_ATTRS, mk), (_DEV_ATTRS, dk),
                  (_PAIR_ATTRS, pk)]
        for attrs, key in groups:
            if key is None:
                continue
            for attr in attrs:
                if only is None or attr in only:
                    yield attr, key

    def _load(self, pairs):
        pairs = list(pairs)
        if not pairs:
            return
        vals = self.r.mget([self._rk(a, k) for a, k in pairs])
        for (attr, dictkey), raw in zip(pairs, vals):
            if raw is not None:
                getattr(self, attr)[dictkey] = pickle.loads(raw)

    def _save_and_evict(self, pairs):
        pairs = list(pairs)
        if not pairs:
            return
        pipe = self.r.pipeline()
        for attr, dictkey in pairs:
            d = getattr(self, attr)
            if dictkey in d:
                rk = self._rk(attr, dictkey)
                pipe.set(rk, pickle.dumps(d[dictkey]))
                if self.ttl:
                    pipe.expire(rk, self.ttl)
                del d[dictkey]     # evict: keep this process's memory bounded
        pipe.execute()

    # --- interface (identical semantics to the in-memory store) -------------
    def _keys(self, t):
        ck = self._k(t.institution_id, t.card_id)
        mk = self._k(t.institution_id, t.merchant_id)
        dk = self._k(t.institution_id, t.device_id)
        return ck, mk, dk, (dk, t.card_id)

    def features_for(self, t) -> dict:
        ck, mk, dk, pk = self._keys(t)
        self._load(self._touched(ck, mk, dk, pk))
        try:
            return super().features_for(t)
        finally:
            # features_for is read-only; evict what we loaded without rewriting
            for attr, dictkey in self._touched(ck, mk, dk, pk):
                getattr(self, attr).pop(dictkey, None)

    def update(self, t) -> None:
        ck, mk, dk, pk = self._keys(t)
        self._load(self._touched(ck, mk, dk, pk))
        super().update(t)
        self._save_and_evict(self._touched(ck, mk, dk, pk))

    def mark_confirmed_fraud(self, institution_id, ts, device_id=None, card_id=None,
                             merchant_id=None):
        ck = self._k(institution_id, card_id) if card_id else None
        mk = self._k(institution_id, merchant_id) if merchant_id else None
        dk = self._k(institution_id, device_id) if device_id else None
        only = {"card_fraud_marks", "merchant_fraud_marks", "device_fraud_marks"}
        touched = list(self._touched(ck, mk, dk, only=only))
        self._load(touched)
        super().mark_confirmed_fraud(institution_id, ts, device_id=device_id,
                                     card_id=card_id, merchant_id=merchant_id)
        self._save_and_evict(touched)
