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


class MediaStubXClient:
    def __init__(self):
        self.uploads = []
        self.tweets = []

    async def upload_media(self, media_path: str, media_type: str = "image"):
        self.uploads.append((media_path, media_type))
        return "media123"

    async def create_tweet(self, text, quote_tweet_id=None, in_reply_to=None, media_ids=None, idempotency_key=None):
        self.tweets.append({
            "text": text,
            "quote_tweet_id": quote_tweet_id,
            "in_reply_to": in_reply_to,
            "media_ids": media_ids,
            "idempotency_key": idempotency_key,
        })
        return "tweet456"


@pytest.mark.asyncio
async def test_multiplexer_uploads_media_before_post(monkeypatch):
    config = get_config()
    previous_live = config.LIVE
    config.LIVE = True

    x_client = MediaStubXClient()

    multiplexer = SocialMultiplexer(
        config=config,
        x_client=x_client,
    )

    metadata = {
        "media": [{"path": "sample.png", "type": "image"}],
        "idempotency_key": "abc123",
    }

    results = await multiplexer.publish(
        "Testing media upload",
        kind="post",
        metadata=metadata,
    )

    config.LIVE = previous_live

    assert x_client.uploads == [("sample.png", "image")]
    assert x_client.tweets[0]["media_ids"] == ["media123"]
    assert results["x"].dry_run is False
    assert results["x"].post_id == "tweet456"
