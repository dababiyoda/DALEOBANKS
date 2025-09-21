import asyncio

import sys
import types

sys.modules.setdefault("tweepy", types.SimpleNamespace(TooManyRequests=Exception))

import pytest

from config import get_config
from services.multiplexer import SocialMultiplexer
from services.linkedin_client import LinkedInClient
from services.mastodon_client import MastodonClient


class StubXClient:
    async def create_tweet(self, *args, **kwargs):
        return "dry_run_tweet_id"


@pytest.mark.asyncio
async def test_multiplexer_returns_dry_run_ids(monkeypatch):
    config = get_config()
    config.ENABLE_LINKEDIN = True
    config.ENABLE_MASTODON = True
    config.PLATFORM_MODE = "broadcast"
    config.PLATFORM_WEIGHTS = {"x": 1.0, "linkedin": 1.0, "mastodon": 1.0}
    config.LIVE = False

    multiplexer = SocialMultiplexer(
        config=config,
        x_client=StubXClient(),
        linkedin_client=LinkedInClient(enabled=True, live=False),
        mastodon_client=MastodonClient(enabled=True, live=False),
    )

    results = await multiplexer.publish("Hello world", kind="post", intensity=1)

    assert set(results.keys()) == {"x", "linkedin", "mastodon"}
    assert results["x"].dry_run is True
    assert results["x"].post_id.startswith("x:post/md_dry_")
    assert results["linkedin"].dry_run is True
    assert results["linkedin"].post_id.startswith("linkedin:post/md_dry_")
    assert results["mastodon"].dry_run is True
    assert results["mastodon"].post_id.startswith("mastodon:post/md_dry_")
