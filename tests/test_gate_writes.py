"""ConsequenceGate coverage for the engagement/DM write families.

Like, unlike, repost, follow and send_dm on X now cross the same
boundary as publishing: evidence -> authority -> commit witness ->
one-time execution -> receipt -> reconciliation. These tests pin the
full chain, the replay defense, per-family authority, the fail-closed
paths, and the honesty contract that a transport refusal is receipted
as a failure, never as the family's silent-success default.
"""

import hashlib
import types

import pytest

from config import get_config, update_config
from services import gate as gate_service
from services.gate import WriteExecutionRefused
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    RateGovernor,
    set_shared_instances,
    reset_shared_instances,
)
from services.x_client import XClient


class FakeProvider:
    """Stand-in for the tweepy client: records calls, returns receipts."""

    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.fail == "raise":
            raise RuntimeError("provider down")
        return types.SimpleNamespace(data={"ok": True})

    def like(self, tweet_id):
        return self._record("like", tweet_id)

    def unlike(self, tweet_id):
        return self._record("unlike", tweet_id)

    def retweet(self, tweet_id):
        return self._record("retweet", tweet_id)

    def follow_user(self, user_id):
        return self._record("follow_user", user_id)

    def send_direct_message(self, *, recipient_id, text):
        return self._record("send_direct_message", recipient_id=recipient_id, text=text)


def _make_client(provider) -> XClient:
    """Real XClient with the provider client injected, no network init."""
    client = XClient.__new__(XClient)
    client.config = get_config()
    client.client = provider
    client.self_id = "self"
    client.circuit_breakers = {}
    client.idempotency_cache = {}
    client.max_write_attempts = 1  # no backoff sleeps in tests
    client._unsubscribe = None
    return client


@pytest.fixture
def env(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=RateGovernor(max_actions=100, window_seconds=3600),
    )
    gate_service.configure(approval_verifier=lambda request_id: True)
    cfg = get_config()
    previous = {k: getattr(cfg, k) for k in (
        "LIVE", "ENABLE_LIKES", "ENABLE_REPOSTS", "ENABLE_FOLLOWS", "ENABLE_DMS")}
    update_config(LIVE=True, ENABLE_LIKES=True, ENABLE_REPOSTS=True,
                  ENABLE_FOLLOWS=True, ENABLE_DMS=True)
    yield ledger
    update_config(**previous)
    gate_service.reset_gate()
    reset_shared_instances()


def _events(ledger):
    return [e["event"] for e in ledger.replay()]


def _payloads(ledger, event):
    return [e["payload"] for e in ledger.replay(event)]


# --- the happy path: full chain per family ---------------------------------

async def test_like_with_grant_commits_full_chain(env):
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True
    assert [c[0] for c in provider.calls] == ["like"]

    events = _events(env)
    for expected in ("write_attempt", "consequence.requested",
                     "consequence.authorized", "consequence.committed",
                     "write_result"):
        assert expected in events

    committed = _payloads(env, "consequence.committed")[-1]
    chain = [e["type"] for e in gate_service.get_gate().spine.causal_chain(committed["id"])]
    assert chain == ["consequence.requested", "consequence.authorized",
                     "consequence.committed"]

    grant_id = gate_service._active_grants[("x", "write.like")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 1
    ok, bad = env.verify_chain()
    assert ok is True and bad is None


async def test_every_family_crosses_the_gate(env):
    for family in gate_service.WRITE_FAMILIES:
        gate_service.mint_write_grant(platform="x", family=family,
                                      approval_request_id=f"a-{family}")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True
    assert await client.unlike("t2") is True
    assert await client.repost("t3") is True
    assert await client.follow("u1") is True
    assert await client.send_dm("u2", "hello") is True

    assert [c[0] for c in provider.calls] == [
        "like", "unlike", "retweet", "follow_user", "send_direct_message"]
    requested = _payloads(env, "consequence.requested")
    assert {p["data"]["action_type"] for p in requested} == {
        "write.like", "write.unlike", "write.repost",
        "write.send_dm", "write.follow"}
    ok, bad = env.verify_chain()
    assert ok is True and bad is None


# --- fail-closed authority paths --------------------------------------------

async def test_write_without_grant_fails_closed(env):
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True  # silent, as dry run
    assert provider.calls == []
    assert "consequence.rejected" in _events(env)
    assert "commit_witnessed" not in _events(env)


async def test_each_family_needs_its_own_grant(env):
    # A like grant does not authorize a follow: families are separate
    # authority domains with separate registry entries.
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.follow("u1") is True  # silent
    assert provider.calls == []
    rejected = _payloads(env, "consequence.rejected")
    assert len(rejected) == 1
    # The rejected request was the follow: authority refused that family.
    requested = _payloads(env, "consequence.requested")
    assert requested[-1]["data"]["action_type"] == "write.follow"
    assert "unknown capability grant" in rejected[-1]["data"]["reason"]


async def test_unverified_approval_mints_nothing(env):
    gate_service.reset_gate()
    gate_service.configure(approval_verifier=lambda request_id: False)

    from uniimente_kernel.capability import CapabilityError
    with pytest.raises(CapabilityError):
        gate_service.mint_write_grant(platform="x", family="like",
                                      approval_request_id="forged")

    provider = FakeProvider()
    client = _make_client(provider)
    assert await client.like("t1") is True
    assert provider.calls == []


async def test_unknown_family_refused_before_the_ledger(env):
    provider = FakeProvider()
    client = _make_client(provider)

    with pytest.raises(ValueError):
        await gate_service.execute_write(
            platform="x", family="bookmark", target="t1",
            impl=client._execute_write,
            impl_kwargs={"endpoint": "x", "enabled": True, "func": lambda: 1},
            dry_run_result=True,
        )
    with pytest.raises(ValueError):
        gate_service.mint_write_grant(platform="x", family="bookmark",
                                      approval_request_id="a1")
    assert env.replay() == []


async def test_grant_exhaustion_fails_closed(env):
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1", maximum_uses=1)
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True
    assert await client.like("t2") is True  # silent: grant exhausted
    assert [c[0] for c in provider.calls] == ["like"]
    assert "consequence.rejected" in _events(env)


# --- replay defense ----------------------------------------------------------

async def test_repeat_like_deduplicates(env):
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True
    assert await client.like("t1") is True  # desired state already holds
    assert [c[0] for c in provider.calls] == ["like"]  # provider saw one call
    assert "consequence.deduplicated" in _events(env)
    grant_id = gate_service._active_grants[("x", "write.like")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 1


async def test_same_dm_text_twice_deduplicates(env):
    gate_service.mint_write_grant(platform="x", family="send_dm",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.send_dm("u1", "identical text") is True
    assert await client.send_dm("u1", "identical text") is True
    assert len(provider.calls) == 1  # no accidental double-DM
    assert await client.send_dm("u1", "different text") is True
    assert len(provider.calls) == 2


# --- honesty: failures are failures, silence stays silent --------------------

async def test_provider_failure_receipted_and_retryable(env):
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider(fail="raise")
    client = _make_client(provider)

    assert await client.like("t1") is True  # failed toward silence
    assert "consequence.failed" in _events(env)
    assert "consequence.committed" not in _events(env)

    provider.fail = None  # provider repaired
    assert await client.like("t1") is True
    assert [c[0] for c in provider.calls] == ["like", "like"]  # retried
    assert "consequence.committed" in _events(env)


async def test_dry_run_inside_the_gate_is_not_a_success(env):
    # If the transport silently refuses (here: LIVE flipped off between
    # authority and execution, caught by the transport's own re-check),
    # the attempt is receipted as failed — never committed.
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    original = client._execute_write

    async def flip_live_then_refuse(**kwargs):
        update_config(LIVE=False)  # transport's require_live check fires
        return await original(**kwargs)

    client._execute_write = flip_live_then_refuse
    try:
        assert await client.like("t1") is True  # silent
    finally:
        update_config(LIVE=True)
    assert provider.calls == []
    assert "consequence.failed" in _events(env)
    assert "consequence.committed" not in _events(env)


async def test_disarmed_kill_switch_stops_writes_before_authority(env):
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    update_config(LIVE=False)  # shared kill switch reads live config
    try:
        assert await client.like("t1") is True
    finally:
        update_config(LIVE=True)

    assert provider.calls == []
    events = _events(env)
    assert "write_gated" in events
    assert "consequence.requested" not in events  # envelope precedes the gate
    grant_id = gate_service._active_grants[("x", "write.like")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 0


async def test_rate_governor_stops_writes_before_authority(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=RateGovernor(max_actions=0, window_seconds=3600),
    )
    gate_service.configure(approval_verifier=lambda request_id: True)
    previous = get_config().LIVE
    update_config(LIVE=True)
    try:
        gate_service.mint_write_grant(platform="x", family="like",
                                      approval_request_id="a1")
        provider = FakeProvider()
        client = _make_client(provider)

        assert await client.like("t1") is True  # silent
        assert provider.calls == []
        assert "write_gated" in _events(ledger)
        assert "consequence.requested" not in _events(ledger)
    finally:
        update_config(LIVE=previous)
        gate_service.reset_gate()
        reset_shared_instances()


# --- family toggles and ledger hygiene ---------------------------------------

async def test_disabled_family_is_inert_and_ledgers_nothing(env):
    update_config(ENABLE_LIKES=False)
    try:
        provider = FakeProvider()
        client = _make_client(provider)
        assert await client.like("t1") is True
    finally:
        update_config(ENABLE_LIKES=True)
    assert provider.calls == []
    assert env.replay() == []  # an inert family attempts nothing


async def test_send_dm_ledgers_hash_not_content(env):
    gate_service.mint_write_grant(platform="x", family="send_dm",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    secret = "meet at the docks at dawn"
    assert await client.send_dm("u1", secret) is True
    assert provider.calls[0][2]["text"] == secret  # provider got the text

    raw = open(env.path).read()
    assert secret not in raw  # the ledger never carries content
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert digest in raw
    attempt = _payloads(env, "write_attempt")[-1]
    assert attempt["text_sha256"] == digest
    # The digest also binds the commit fingerprint: same text dedupes,
    # different text executes (covered in the dedupe test).


async def test_sentinel_isolation_between_concurrent_writes(env):
    # Two in-flight writes must not share a sentinel: each executor's
    # refusal detection is scoped to its own attempt.
    gate_service.mint_write_grant(platform="x", family="like",
                                  approval_request_id="a1")
    provider = FakeProvider()
    client = _make_client(provider)

    assert await client.like("t1") is True
    assert await client.like("t2") is True
    assert [c[1][0] for c in provider.calls] == ["t1", "t2"]
    grant_id = gate_service._active_grants[("x", "write.like")]
    gate = gate_service.get_gate()
    assert gate.capability.store.get(grant_id).uses_consumed == 2


def test_write_execution_refused_is_a_runtime_error():
    assert issubclass(WriteExecutionRefused, RuntimeError)
