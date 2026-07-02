"""Tests for the inherited publish gate in BaseSocialClient."""

import pytest

from config import get_config, update_config
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    RateGovernor,
    set_shared_instances,
    reset_shared_instances,
)
from services.social_base import BaseSocialClient, SocialPostResult


class RecordingClient(BaseSocialClient):
    platform = "testnet"

    def __init__(self):
        super().__init__(enabled=True, live=True)
        self.impl_calls = 0

    async def _publish_impl(self, *, content, kind="post", in_reply_to=None,
                            quote_to=None, intensity=1, metadata=None):
        self.impl_calls += 1
        return SocialPostResult(
            platform=self.platform, post_id="live_123", dry_run=False, meta=metadata
        )


@pytest.fixture
def gate(tmp_path):
    """Isolated ledger/kill-switch/governor wired into the shared gate."""
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    governor = RateGovernor(max_actions=2, window_seconds=3600)
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=governor,
    )
    previous_live = get_config().LIVE
    yield ledger
    update_config(LIVE=previous_live)
    reset_shared_instances()


async def test_disarmed_kill_switch_forces_dry_run(gate):
    update_config(LIVE=False)
    client = RecordingClient()

    result = await client.publish(content="hello", kind="post")

    assert result.dry_run is True
    assert client.impl_calls == 0

    events = [e["event"] for e in gate.replay()]
    assert "publish_attempt" in events
    assert "publish_result" in events


async def test_armed_switch_delegates_to_impl(gate):
    update_config(LIVE=True)
    client = RecordingClient()

    result = await client.publish(content="hello", kind="post")

    assert result.dry_run is False
    assert result.post_id == "live_123"
    assert client.impl_calls == 1

    results = gate.replay("publish_result")
    assert results[-1]["payload"]["dry_run"] is False


async def test_rate_governor_gates_excess_publishes(gate):
    update_config(LIVE=True)
    client = RecordingClient()

    first = await client.publish(content="one")
    second = await client.publish(content="two")
    third = await client.publish(content="three")

    assert first.dry_run is False
    assert second.dry_run is False
    assert third.dry_run is True
    assert client.impl_calls == 2

    gated = gate.replay("publish_gated")
    assert len(gated) == 1
    assert gated[0]["payload"]["reason"] == "rate_governor"


async def test_every_attempt_is_ledgered_and_chain_verifies(gate):
    update_config(LIVE=False)
    client = RecordingClient()

    for i in range(3):
        await client.publish(content=f"msg {i}")

    assert len(gate.replay("publish_attempt")) == 3
    ok, bad = gate.verify_chain()
    assert ok is True and bad is None
