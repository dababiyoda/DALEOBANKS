"""Crisis detection heuristics."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from services.crisis import CrisisService
from services.social_base import SocialPostResult


def test_keyword_triggers_crisis() -> None:
    service = CrisisService(sentiment_service=MagicMock())

    assert service.is_crisis("This is a major scandal unfolding now") is True


def test_negative_sentiment_triggers_crisis() -> None:
    sentiment = MagicMock()
    sentiment.analyze_sentiment.return_value = {"score": -0.9}

    service = CrisisService(sentiment_service=sentiment)

    assert service.is_crisis("Everything feels off") is True
    sentiment.analyze_sentiment.assert_called_once()


def test_positive_message_not_crisis() -> None:
    sentiment = MagicMock()
    sentiment.analyze_sentiment.return_value = {"score": 0.5}

    service = CrisisService(sentiment_service=sentiment)

    assert service.is_crisis("All systems stable") is False


def test_crisis_guard_blocks_runtime() -> None:
    service = CrisisService(sentiment_service=MagicMock())
    service.activate(reason="test")
    assert service.is_paused() is True
    assert service.guard(action="post") is False
    service.resolve(reason="ok")
    assert service.is_paused() is False
    assert service.guard(action="post") is True


def _run(coro):
    return asyncio.run(coro)


def test_signal_spike_triggers_pause_and_post() -> None:
    multiplexer = AsyncMock()
    multiplexer.publish.return_value = {
        "x": SocialPostResult(platform="x", post_id="123", dry_run=False, meta={"kind": "crisis_calm"})
    }
    service = CrisisService(signal_threshold=3.0, resume_threshold=1.0)

    _run(
        service.update_metrics(
            source="mentions",
            multiplexer=multiplexer,
            sentiment=-0.8,
            velocity=2.0,
            authority=2.0,
        )
    )

    assert service.is_paused() is True
    multiplexer.publish.assert_awaited_once()
    assert service.reason is not None and "mentions_signal" in service.reason

    _run(
        service.update_metrics(
            source="analytics",
            multiplexer=multiplexer,
            sentiment=0.2,
            velocity=0.5,
            authority=1.0,
        )
    )

    assert service.is_paused() is False


def test_pause_persists_until_receipts_validated() -> None:
    multiplexer = AsyncMock()
    multiplexer.publish.return_value = {
        "x": SocialPostResult(platform="x", post_id="dry", dry_run=True, meta={})
    }
    service = CrisisService(signal_threshold=2.0, resume_threshold=0.5)

    _run(
        service.update_metrics(
            source="mentions",
            multiplexer=multiplexer,
            sentiment=-1.0,
            velocity=1.5,
            authority=2.0,
        )
    )

    assert service.is_paused() is True
    assert service.last_signal > 0

    _run(
        service.update_metrics(
            source="mentions",
            multiplexer=multiplexer,
            sentiment=0.1,
            velocity=0.1,
            authority=1.0,
        )
    )

    assert service.is_paused() is True

    service.record_receipts({
        "x": SocialPostResult(platform="x", post_id="real", dry_run=False, meta={})
    })

    _run(
        service.update_metrics(
            source="analytics",
            multiplexer=multiplexer,
            sentiment=0.3,
            velocity=0.2,
            authority=1.0,
        )
    )

    assert service.is_paused() is False
