"""Tests for the arming ceremony: preflight-gated arm, unconditional disarm."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from config import get_config, update_config
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    set_shared_instances,
    reset_shared_instances,
)


@pytest.fixture
def arming_env(tmp_path, monkeypatch):
    """Isolated ledger + healthy defaults for every preflight input."""
    import app as app_module
    import runner

    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))

    monkeypatch.setattr(app_module.x_client, "verify_credentials", AsyncMock(return_value=True))
    monkeypatch.setattr(runner.heartbeat, "_breaker_tripped", False)
    monkeypatch.setattr(runner.heartbeat, "_failures", 0)

    previous_live = get_config().LIVE
    update_config(LIVE=False)
    yield app_module, runner, ledger
    update_config(LIVE=previous_live)
    reset_shared_instances()


async def test_arm_passes_preflight_and_is_ledgered(arming_env):
    app_module, _, ledger = arming_env

    response = await app_module.toggle_live_mode(app_module.ToggleRequest(live=True))

    assert response["live"] is True
    assert get_config().LIVE is True
    armed = ledger.replay("armed")
    assert len(armed) == 1
    assert armed[0]["payload"]["checks"] == {
        "ledger_chain": True,
        "breaker_clear": True,
        "x_credentials": True,
    }


async def test_arm_refused_without_credentials(arming_env):
    app_module, _, ledger = arming_env
    app_module.x_client.verify_credentials = AsyncMock(return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        await app_module.toggle_live_mode(app_module.ToggleRequest(live=True))

    assert exc_info.value.status_code == 409
    assert get_config().LIVE is False
    refused = ledger.replay("arm_refused")
    assert len(refused) == 1
    assert refused[0]["payload"]["checks"]["x_credentials"] is False


async def test_arm_refused_when_breaker_tripped(arming_env):
    app_module, runner_module, ledger = arming_env
    runner_module.heartbeat._breaker_tripped = True

    with pytest.raises(HTTPException) as exc_info:
        await app_module.toggle_live_mode(app_module.ToggleRequest(live=True))

    assert exc_info.value.status_code == 409
    assert get_config().LIVE is False
    assert ledger.replay("arm_refused")[0]["payload"]["checks"]["breaker_clear"] is False


async def test_disarm_is_unconditional(arming_env):
    app_module, runner_module, ledger = arming_env
    # Even with every preflight input failing, disarm must succeed.
    app_module.x_client.verify_credentials = AsyncMock(return_value=False)
    runner_module.heartbeat._breaker_tripped = True
    update_config(LIVE=True)

    response = await app_module.toggle_live_mode(app_module.ToggleRequest(live=False))

    assert response["live"] is False
    assert get_config().LIVE is False


async def test_breaker_reset_endpoint_does_not_rearm(arming_env):
    app_module, runner_module, _ = arming_env
    runner_module.heartbeat._breaker_tripped = True
    update_config(LIVE=False)

    result = await app_module.reset_heartbeat_breaker(None)

    assert result["breaker_tripped"] is False
    assert result["live"] is False
