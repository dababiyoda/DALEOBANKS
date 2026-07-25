"""Safety-posture tests: a fresh checkout must be incapable of touching the
outside world, and /api/health must say so plainly."""

from config import get_config


async def test_health_reports_safe_defaults():
    import app as app_module

    health = await app_module.health_check()

    assert health["ok"] is True
    assert health["live"] is False  # LIVE=false is the default
    assert health["x_credentials_configured"] is False  # no keys in test env
    assert health["dry_run"] is True  # therefore nothing can post
    assert health["crisis_state"] in ("NORMAL", "PAUSED")
    assert health["breaker_tripped"] is False
    assert health["ledger_chain_ok"] is True


def test_live_defaults_false_without_env():
    # config reads LIVE from the environment with a "false" default; the
    # test environment sets no LIVE, so the safe default must hold.
    assert get_config().LIVE is False


async def test_dry_run_stays_true_even_when_armed_without_credentials():
    """Arming without credentials still cannot produce a real post: the
    publish gate dry-runs, and health reports it."""
    from config import update_config
    import app as app_module

    update_config(LIVE=True)
    try:
        health = await app_module.health_check()
        assert health["live"] is True
        assert health["x_credentials_configured"] is False
        assert health["dry_run"] is True  # no keys -> still no outbound writes
    finally:
        update_config(LIVE=False)
