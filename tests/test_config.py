"""C18 (D-052): config defaults + env override."""

import importlib
import os


def test_defaults_match_pilot_values():
    from finguard import config
    c = config.reload()
    assert c.card_cost_fn == 5.0            # D-010
    assert c.p2p_cost_fn == 10.0            # D-017
    assert c.wire_per_wire_floor == 10_000.0  # D-047
    assert c.hold_ttl_hours == 48.0
    assert c.port == 8100
    assert c.redis_url is None              # secret: env-only, no hardcoded default


def test_env_override_is_live():
    from finguard import config
    os.environ["FINGUARD_HOLD_TTL_HOURS"] = "24"
    os.environ["FINGUARD_PORT"] = "9000"
    try:
        c = config.reload()
        assert c.hold_ttl_hours == 24.0
        assert c.port == 9000
    finally:
        del os.environ["FINGUARD_HOLD_TTL_HOURS"]
        del os.environ["FINGUARD_PORT"]
        config.reload()   # restore defaults for other tests


def test_secret_read_from_env_only():
    from finguard import config
    os.environ["FINGUARD_REDIS_URL"] = "redis://secret-host:6379"
    try:
        c = config.reload()
        assert c.redis_url == "redis://secret-host:6379"
    finally:
        del os.environ["FINGUARD_REDIS_URL"]
        config.reload()
