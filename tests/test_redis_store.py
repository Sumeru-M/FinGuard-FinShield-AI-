"""C19 (D-052): RedisFeatureStore is a behavior-equivalent drop-in for the in-process
store, proven against fakeredis (no daemon needed)."""

import fakeredis
import pytest

from finguard import datagen
from finguard.features import FEATURE_COLUMNS, InMemoryFeatureStore, LABEL_LATENCY
from finguard.redis_store import RedisFeatureStore


def _replay(store, df):
    """Same point-in-time replay the pipeline uses, parameterized by store."""
    out = []
    for t in df.sort_values("timestamp").itertuples(index=False):
        out.append(store.features_for(t))
        store.update(t)
        if t.label != "confirmed_legitimate":
            store.mark_confirmed_fraud(t.institution_id, t.timestamp + LABEL_LATENCY,
                                       device_id=t.device_id, card_id=t.card_id,
                                       merchant_id=t.merchant_id)
    return out


def test_redis_store_matches_inmemory_feature_for_feature():
    df = datagen.generate(n_cards=60, n_days=6, seed=7)   # includes fraud + label loop
    mem = _replay(InMemoryFeatureStore(), df)
    red = _replay(RedisFeatureStore(fakeredis.FakeStrictRedis()), df)
    assert len(mem) == len(red) > 0
    for i, (a, b) in enumerate(zip(mem, red)):
        for col in FEATURE_COLUMNS:
            assert a[col] == pytest.approx(b[col]), f"row {i} col {col}: {a[col]} != {b[col]}"


def test_redis_store_persists_across_instances():
    # State lives in Redis, not the process: a fresh store on the same client sees history.
    client = fakeredis.FakeStrictRedis()
    df = datagen.generate(n_cards=20, n_days=4, seed=3)
    rows = df.sort_values("timestamp")
    warm = RedisFeatureStore(client)
    for t in rows.itertuples(index=False):
        warm.features_for(t); warm.update(t)
    # brand-new store instance, same Redis -> a repeat txn is NOT treated as first-seen
    fresh = RedisFeatureStore(client)
    last = list(rows.itertuples(index=False))[-1]
    f = fresh.features_for(last)
    assert f["is_new_device_for_card"] == 0     # device already known from prior instance
    assert f["txn_count_24h"] >= 1 or f["device_observed_age_days"] >= 0


def test_ttl_is_applied_when_configured():
    client = fakeredis.FakeStrictRedis()
    store = RedisFeatureStore(client, ttl_seconds=3600)
    df = datagen.generate(n_cards=5, n_days=2, seed=1)
    t0 = df.sort_values("timestamp").iloc[0]
    store.update(t0)
    keys = client.keys("fs:*")
    assert keys, "expected feature-state keys written to redis"
    assert all(0 < client.ttl(k) <= 3600 for k in keys)
