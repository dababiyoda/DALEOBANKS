"""ConsequenceGate adoption: the publishing family is 100% mediated.

Every live outbound post crosses evidence -> authority -> commit witness
-> execution -> receipt -> reconciliation. These tests pin the full
chain, the replay defense, the fail-closed rejection paths, and the
disarm-on-divergence doctrine.
"""

import pytest

from config import get_config, update_config
from services import gate as gate_service
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    RateGovernor,
    set_shared_instances,
    reset_shared_instances,
)
from services.social_base import BaseSocialClient, SocialPostResult


class LiveClient(BaseSocialClient):
    platform = "testnet"

    def __init__(self, *, post_id="live_1", fail=None):
        super().__init__(enabled=True, live=True)
        self.post_id = post_id
        self.fail = fail
        self.calls = []

    async def _publish_impl(self, *, content, kind="post", in_reply_to=None,
                            quote_to=None, intensity=1, metadata=None):
        self.calls.append(content)
        if self.fail == "raise":
            raise RuntimeError("provider down")
        if self.fail == "fake_dry":
            # Provider pretended success but returned no live receipt.
            return SocialPostResult(platform=self.platform, post_id="", dry_run=True)
        return SocialPostResult(platform=self.platform, post_id=self.post_id,
                                dry_run=False, meta=metadata)


@pytest.fixture
def env(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=RateGovernor(max_actions=100, window_seconds=3600),
    )
    gate_service.configure(approval_verifier=lambda request_id: True)
    previous_live = get_config().LIVE
    update_config(LIVE=True)
    yield ledger
    update_config(LIVE=previous_live)
    gate_service.reset_gate()
    reset_shared_instances()


def _events(ledger):
    return [e["event"] for e in ledger.replay()]


async def test_live_publish_closes_the_full_chain(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    client = LiveClient(post_id="live_9")

    result = await client.publish(content="hello world", kind="post")

    assert result.dry_run is False
    assert result.post_id == "live_9"
    assert client.calls == ["hello world"]

    events = _events(env)
    for expected in ("consequence.requested", "consequence.authorized",
                     "consequence.committed"):
        assert expected in events
    # Causal chain replays request -> authorized -> committed in order.
    committed = env.replay("consequence.committed")[-1]["payload"]
    chain = [e["type"] for e in gate_service.get_gate().spine.causal_chain(committed["id"])]
    assert chain == ["consequence.requested", "consequence.authorized",
                     "consequence.committed"]
    # Exactly one grant use consumed.
    grant_id = gate_service._active_grants[("testnet", "post")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 1
    ok, bad = env.verify_chain()
    assert ok is True and bad is None


async def test_retried_publish_never_double_posts(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    client = LiveClient()

    first = await client.publish(content="same text", kind="post")
    second = await client.publish(content="same text", kind="post")

    assert first.dry_run is False
    assert second.dry_run is False
    assert second.post_id == first.post_id  # idempotent read-back
    assert client.calls == ["same text"]  # provider saw exactly one call

    assert "consequence.deduplicated" in _events(env)
    grant_id = gate_service._active_grants[("testnet", "post")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 1


async def test_different_content_is_a_new_action(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    client = LiveClient()

    await client.publish(content="text a", kind="post")
    await client.publish(content="text b", kind="post")

    assert client.calls == ["text a", "text b"]


async def test_unapproved_platform_fails_closed(env):
    # No grant minted for (testnet, post): authority refuses, no execution.
    client = LiveClient()

    result = await client.publish(content="hello", kind="post")

    assert result.dry_run is True
    assert client.calls == []
    assert "consequence.rejected" in _events(env)
    assert "commit_witnessed" not in _events(env)


async def test_unverified_approval_mints_nothing(env):
    gate_service.reset_gate()
    gate_service.configure(approval_verifier=lambda request_id: False)

    from uniimente_kernel.capability import CapabilityError
    with pytest.raises(CapabilityError):
        gate_service.mint_publish_grant(platform="testnet",
                                        approval_request_id="forged")

    client = LiveClient()
    result = await client.publish(content="hello", kind="post")
    assert result.dry_run is True
    assert client.calls == []


async def test_provider_failure_receipted_and_retryable(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    client = LiveClient(fail="raise")

    first = await client.publish(content="hello", kind="post")
    assert first.dry_run is True  # failed toward silence
    assert "consequence.failed" in _events(env)

    client.fail = None  # provider repaired
    second = await client.publish(content="hello", kind="post")
    assert second.dry_run is False
    assert client.calls == ["hello", "hello"]  # retry executed, not deduped


async def test_fake_success_disarms_the_organ(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    client = LiveClient(fail="fake_dry")

    result = await client.publish(content="hello", kind="post")

    assert result.dry_run is True
    # Postcondition failed: reconciliation opened and the organ went silent.
    assert "reconciliation_opened" in _events(env)
    assert "consequence.reconciliation_opened" in _events(env)
    assert get_config().LIVE is False

    # The attempt is recorded as executed-but-unverified; after the
    # operator repairs and re-arms, a restarted gate must not blindly
    # re-execute the same fingerprint.
    update_config(LIVE=True)
    gate_service.configure(approval_verifier=lambda request_id: True)
    client2 = LiveClient()
    again = await client2.publish(content="hello", kind="post")
    assert client2.calls == []
    assert "consequence.deduplicated" in _events(env)
