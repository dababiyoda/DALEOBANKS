"""Execution Card evidence for the publish path: with LIVE armed, only a
human-approved grant for this exact draft, platform and text publishes;
every other case falls back to a dry run, is ledgered, and never reaches
the platform."""

from datetime import datetime, timedelta, UTC

import pytest

from config import get_config, update_config
from db.session import get_db_session, init_db
from services.capability import get_capability_service
from services.ledger import DecisionLedger, KillSwitch, RateGovernor, set_shared_instances, reset_shared_instances
from services.social_base import BaseSocialClient, SocialPostResult
from tests.grant_helpers import grant_metadata, mint_publish_grant

TEXT = "Financial independence is not selfish. (Educational only — not financial advice.)"


class Platform(BaseSocialClient):
    platform = "x"

    def __init__(self):
        super().__init__(enabled=True, live=True)
        self.sent = []

    async def _publish_impl(self, *, content, kind="post", in_reply_to=None,
                            quote_to=None, intensity=1, metadata=None):
        self.sent.append(content)
        return SocialPostResult(platform=self.platform, post_id=f"live_{len(self.sent)}",
                                dry_run=False, meta=metadata)


@pytest.fixture
def live(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger, kill_switch=KillSwitch(ledger=ledger),
                         governor=RateGovernor(max_actions=100, window_seconds=3600))
    previous = get_config().LIVE
    update_config(LIVE=True)
    yield ledger
    update_config(LIVE=previous)
    reset_shared_instances()


def _reasons(ledger):
    return [e["payload"]["reason"] for e in ledger.replay("publish_gated")]


async def test_approved_grant_publishes_exactly_once(live):
    client = Platform()
    grant = mint_publish_grant("x", TEXT)
    first = await client.publish(content=TEXT, metadata=grant_metadata(grant))
    replay = await client.publish(content=TEXT, metadata=grant_metadata(grant))
    assert first.dry_run is False and replay.dry_run is True
    assert client.sent == [TEXT]  # replay never reached the platform
    assert grant.uses_consumed == 1


async def test_armed_live_without_a_grant_is_silent(live):
    client = Platform()
    result = await client.publish(content=TEXT)
    assert result.dry_run is True and client.sent == []
    assert _reasons(live) == ["no_capability_grant"]


@pytest.mark.parametrize("case", ["wrong_draft", "wrong_platform", "wrong_text", "forged_grant"])
async def test_anything_wider_than_the_approval_fails_closed(live, case):
    client = Platform()
    grant = mint_publish_grant("x", TEXT)
    metadata, content = grant_metadata(grant), TEXT
    if case == "wrong_draft":
        metadata = grant_metadata(grant, draft_id="draft-other")
    elif case == "wrong_platform":
        client.platform = "mastodon"
    elif case == "wrong_text":
        content = TEXT + " Buy now."
    elif case == "forged_grant":
        metadata = {"capability_grant_id": "not-a-grant", "draft_id": "draft-1"}

    result = await client.publish(content=content, metadata=metadata)
    assert result.dry_run is True and client.sent == []
    if case == "wrong_text":
        assert _reasons(live) == ["content_outside_approved_intent"]
        assert grant.uses_consumed == 0  # refused before any use was spent
    else:
        assert _reasons(live)[0].startswith("capability_rejected")


async def test_expired_and_revoked_grants_fail_closed(live):
    client = Platform()
    expired = mint_publish_grant("x", TEXT, draft_id="d-exp")
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    revoked = mint_publish_grant("x", TEXT, draft_id="d-rev")
    with get_db_session() as session:
        get_capability_service().revoke(session, revoked.id, reason="founder changed mind")

    for grant, draft in ((expired, "d-exp"), (revoked, "d-rev")):
        result = await client.publish(content=TEXT, metadata=grant_metadata(grant, draft))
        assert result.dry_run is True
    assert client.sent == []


async def test_disarmed_switch_spends_no_authority(live):
    update_config(LIVE=False)
    client = Platform()
    grant = mint_publish_grant("x", TEXT)
    result = await client.publish(content=TEXT, metadata=grant_metadata(grant))
    assert result.dry_run is True and client.sent == []
    assert grant.uses_consumed == 0


async def test_refusals_are_ledgered_with_the_text_fingerprint_not_the_text(live):
    client = Platform()
    await client.publish(content=TEXT)
    gated = live.replay("publish_gated")[0]["payload"]
    assert len(gated["content_sha256"]) == 64
    assert TEXT not in str(live.replay("publish_gated"))
    assert live.verify_chain()[0] is True
