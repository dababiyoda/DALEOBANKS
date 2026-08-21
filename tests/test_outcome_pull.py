"""Outcome pull: committed publishes get their outcomes chained.

An executed action without its outcome blocks autonomy promotion; zero
response is a negative result, never an absence. These tests pin the
receipt chain, the honest eligibility window, idempotency, and the
mechanical result classification.
"""

import pytest

from services import gate as gate_service
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    RateGovernor,
    set_shared_instances,
    reset_shared_instances,
)
from services.outcome_pull import classify, pull_publish_outcomes
from services.social_base import SocialPostResult
from config import get_config, update_config


class FakeMetricsClient:
    """Stand-in for XClient.metrics_for: batched read, canned metrics."""

    def __init__(self, metrics):
        self.metrics = {str(k): v for k, v in metrics.items()}
        self.queries = []

    async def metrics_for(self, ids):
        self.queries.append([str(i) for i in ids])
        return {i: self.metrics[i] for i in map(str, ids) if i in self.metrics}


@pytest.fixture
def env(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=RateGovernor(max_actions=100, window_seconds=3600),
    )
    gate_service.configure(approval_verifier=lambda request_id: True)
    previous = get_config().LIVE
    update_config(LIVE=True)
    yield ledger
    update_config(LIVE=previous)
    gate_service.reset_gate()
    reset_shared_instances()


def _events(ledger):
    return [e["event"] for e in ledger.replay()]


def _payloads(ledger, event):
    return [e["payload"] for e in ledger.replay(event)]


async def _commit_publish(*, content="hello", post_id="p1"):
    """One gated publish commit on a fake adapter."""
    async def impl(**kwargs):
        return SocialPostResult(platform="testnet", post_id=post_id, dry_run=False)

    async def dry(**kwargs):
        return SocialPostResult(platform="testnet", post_id="", dry_run=True)

    return await gate_service.publish_post(
        platform="testnet", kind="post", content=content,
        impl=impl, impl_kwargs={}, dry_run=dry,
    )


async def test_committed_publish_chains_receipt(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")

    receipts = _payloads(env, "consequence.receipt")
    assert len(receipts) == 1
    committed = _payloads(env, "consequence.committed")[-1]
    assert receipts[0]["causal_parent"] == committed["id"]
    assert receipts[0]["data"]["post_id"] == "p1"


async def test_pull_records_outcome_chained_to_commit(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    client = FakeMetricsClient({"p1": {"like_count": 3, "retweet_count": 1}})

    summary = await pull_publish_outcomes(client, min_age_hours=0)

    assert summary == {"pending": 1, "recorded": 1, "skipped": 0}
    assert client.queries == [["p1"]]  # one batched read

    outcomes = _payloads(env, "consequence.outcome")
    assert len(outcomes) == 1
    data = outcomes[0]["data"]
    assert data["result_class"] == "positive"
    assert data["validation_status"] == "externally_verified"

    # The full chain replays: request -> authorized -> committed -> outcome.
    chain = [e["type"] for e in
             gate_service.get_gate().spine.causal_chain(outcomes[0]["id"])]
    assert chain == ["consequence.requested", "consequence.authorized",
                     "consequence.committed", "consequence.outcome"]
    ok, bad = env.verify_chain()
    assert ok is True and bad is None


async def test_zero_engagement_is_recorded_as_zero_response(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    client = FakeMetricsClient({"p1": {"like_count": 0, "retweet_count": 0,
                                       "reply_count": 0, "quote_count": 0}})

    summary = await pull_publish_outcomes(client, min_age_hours=0)

    assert summary["recorded"] == 1
    outcome = _payloads(env, "consequence.outcome")[-1]
    assert outcome["data"]["result_class"] == "zero_response"


async def test_pull_is_idempotent(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    client = FakeMetricsClient({"p1": {"like_count": 5}})

    first = await pull_publish_outcomes(client, min_age_hours=0)
    second = await pull_publish_outcomes(client, min_age_hours=0)

    assert first["recorded"] == 1
    assert second == {"pending": 0, "recorded": 0, "skipped": 0}
    assert len(_payloads(env, "consequence.outcome")) == 1


async def test_missing_metrics_skipped_not_recorded(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    client = FakeMetricsClient({})  # platform returned nothing for p1

    summary = await pull_publish_outcomes(client, min_age_hours=0)

    assert summary == {"pending": 1, "recorded": 0, "skipped": 1}
    assert "consequence.outcome" not in _events(env)
    # Absence of observation is not evidence of absence: next pull retries.
    client.metrics["p1"] = {"like_count": 2}
    retry = await pull_publish_outcomes(client, min_age_hours=0)
    assert retry["recorded"] == 1


async def test_young_receipt_is_not_eligible(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    client = FakeMetricsClient({"p1": {"like_count": 0}})

    summary = await pull_publish_outcomes(client)  # default 6h window

    assert summary == {"pending": 0, "recorded": 0, "skipped": 0}
    assert client.queries == []  # never even read
    assert "consequence.outcome" not in _events(env)


async def test_deduped_publish_does_not_double_receipt(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(content="same", post_id="p1")
    await _commit_publish(content="same", post_id="p1")  # deduplicated

    assert len(_payloads(env, "consequence.receipt")) == 1
    client = FakeMetricsClient({"p1": {"like_count": 1}})
    summary = await pull_publish_outcomes(client, min_age_hours=0)
    assert summary["recorded"] == 1
    assert len(_payloads(env, "consequence.outcome")) == 1


async def test_record_outcome_for_unknown_commit_refused(env):
    with pytest.raises(KeyError):
        gate_service.record_outcome_for(
            "no-such-event",
            external_observation="{}",
            result_class="positive",
            expected_vs_actual="n/a",
        )


async def test_invalid_result_class_refused(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(post_id="p1")
    committed = _payloads(env, "consequence.committed")[-1]

    from uniimente_kernel.gate import GateError
    with pytest.raises(GateError):
        gate_service.record_outcome_for(
            committed["id"],
            external_observation="{}",
            result_class="great",
            expected_vs_actual="n/a",
        )


async def test_two_posts_one_batched_read(env):
    gate_service.mint_publish_grant(platform="testnet", approval_request_id="a1")
    await _commit_publish(content="a", post_id="p1")
    await _commit_publish(content="b", post_id="p2")
    client = FakeMetricsClient({"p1": {"like_count": 1}, "p2": {"like_count": 0}})

    summary = await pull_publish_outcomes(client, min_age_hours=0)

    assert summary == {"pending": 2, "recorded": 2, "skipped": 0}
    assert len(client.queries) == 1
    assert sorted(client.queries[0]) == ["p1", "p2"]
    classes = {o["data"]["result_class"]
               for o in _payloads(env, "consequence.outcome")}
    assert classes == {"positive", "zero_response"}


def test_classify_is_mechanical():
    assert classify({"like_count": 1}) == "positive"
    assert classify({"like_count": 0, "impression_count": 0}) == "zero_response"
    assert classify({}) == "zero_response"
