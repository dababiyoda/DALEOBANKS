"""With LIVE armed, likes, reposts, follows and DMs need a grant for the
exact tweet or user (and DM text). Refusals are ledgered and reported as
False — never the dry-run 'success' — and never reach the platform."""

import pytest

from config import get_config
from db.session import init_db
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.x_client import GOVERNED_WRITE_FAMILIES, XClient
from tests.grant_helpers import mint_write_grant


class Platform:
    def __init__(self):
        self.calls = []

    def like(self, tweet_id): self.calls.append(("like", tweet_id)); return {"ok": True}
    def unlike(self, tweet_id): self.calls.append(("unlike", tweet_id)); return {"ok": True}
    def retweet(self, tweet_id): self.calls.append(("repost", tweet_id)); return {"ok": True}
    def follow_user(self, user_id): self.calls.append(("follow", user_id)); return {"ok": True}

    def send_direct_message(self, recipient_id, text):
        self.calls.append(("send_dm", recipient_id, text)); return {"ok": True}


@pytest.fixture
def live_x(tmp_path, monkeypatch):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    config = get_config()
    for name in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET", "X_BEARER_TOKEN"):
        monkeypatch.setattr(config, name, "")
    for name in ("LIVE", "ENABLE_LIKES", "ENABLE_REPOSTS", "ENABLE_FOLLOWS", "ENABLE_DMS"):
        monkeypatch.setattr(config, name, True)
    client = XClient()
    client.client = Platform()
    yield client, ledger
    reset_shared_instances()


CALLS = {
    "like": lambda c, g=None: c.like("t-1", capability_grant_id=g),
    "unlike": lambda c, g=None: c.unlike("t-1", capability_grant_id=g),
    "repost": lambda c, g=None: c.repost("t-1", capability_grant_id=g),
    "follow": lambda c, g=None: c.follow("u-1", capability_grant_id=g),
    "send_dm": lambda c, g=None: c.send_dm("u-1", "thanks for the reply", capability_grant_id=g),
}
RESOURCE = {"like": "t-1", "unlike": "t-1", "repost": "t-1", "follow": "u-1", "send_dm": "u-1"}


def test_every_governed_family_has_a_case():
    assert set(CALLS) == set(GOVERNED_WRITE_FAMILIES)


@pytest.mark.parametrize("family", sorted(GOVERNED_WRITE_FAMILIES))
async def test_ungranted_live_write_is_refused_and_reported_false(live_x, family):
    client, ledger = live_x
    assert await CALLS[family](client) is False
    assert client.client.calls == []
    gated = ledger.replay("write_gated")
    assert gated and gated[-1]["payload"]["family"] == family
    assert gated[-1]["payload"]["reason"] == "no_capability_grant"


@pytest.mark.parametrize("family", sorted(GOVERNED_WRITE_FAMILIES))
async def test_granted_write_happens_once(live_x, family):
    client, _ = live_x
    content = "thanks for the reply" if family == "send_dm" else ""
    grant = mint_write_grant(family, RESOURCE[family], content=content)
    assert await CALLS[family](client, grant.id) is True
    assert await CALLS[family](client, grant.id) is False  # replay refused
    assert len(client.client.calls) == 1


async def test_grant_for_one_tweet_cannot_like_another(live_x):
    client, _ = live_x
    grant = mint_write_grant("like", "t-1")
    assert await client.like("t-2", capability_grant_id=grant.id) is False
    assert client.client.calls == []


async def test_grant_for_one_family_cannot_do_another(live_x):
    client, _ = live_x
    grant = mint_write_grant("like", "t-1")
    assert await client.repost("t-1", capability_grant_id=grant.id) is False
    assert client.client.calls == []


async def test_dm_text_must_match_the_approved_text(live_x):
    client, ledger = live_x
    grant = mint_write_grant("send_dm", "u-1", content="thanks for the reply")
    assert await client.send_dm("u-1", "buy my course", capability_grant_id=grant.id) is False
    assert grant.uses_consumed == 0
    assert ledger.replay("write_gated")[-1]["payload"]["reason"] == "content_outside_approved_intent"
    assert "buy my course" not in str(ledger.entries())


async def test_live_off_stays_a_plain_dry_run(live_x, monkeypatch):
    client, ledger = live_x
    monkeypatch.setattr(get_config(), "LIVE", False)
    assert await client.like("t-1") is True  # dry-run posture unchanged
    assert client.client.calls == [] and ledger.replay("write_gated") == []
