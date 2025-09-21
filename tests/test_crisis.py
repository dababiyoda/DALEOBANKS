"""Crisis detection heuristics."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.crisis import CrisisService


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
