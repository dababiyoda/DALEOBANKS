"""
crisis.py
------------

This module defines a lightweight crisis detection service for the
DaLeoBanks agent. The purpose of this service is to monitor
incoming content for signs of emerging crises, such as scandals,
emergencies, or highly negative sentiment. When a potential crisis is
detected, downstream systems can adjust behaviour—slowing posting
cadence, switching into monitoring mode, or escalating to human
operators.

The implementation intentionally avoids heavy dependencies and does not
perform any network requests. Instead, it relies on a simple keyword
watch list and a basic sentiment score supplied by the
``SentimentService``. This makes it suitable for environments where
external API access is restricted or costly.
"""

from __future__ import annotations

from typing import List, Dict, Optional

from services.sentiment import SentimentService
from services.logging_utils import get_logger

logger = get_logger(__name__)


class CrisisService:
    """Detects crisis signals in text based on sentiment and keywords."""

    def __init__(self, sentiment_service: SentimentService | None = None):
        # Allow dependency injection for testing
        self.sentiment_service = sentiment_service or SentimentService()
        # Keywords that often indicate crisis situations. Add more as needed.
        self.crisis_keywords: List[str] = [
            "crisis",
            "scandal",
            "emergency",
            "bankrupt",
            "fail",
            "collapse",
            "fraud",
            "default",
            "lawsuit",
            "investigation",
        ]
        # Sentiment threshold below which content is considered highly negative
        self.sentiment_threshold: float = -0.5
        self._active: bool = False
        self._reason: Optional[str] = None

    def is_crisis(self, text: str) -> bool:
        """Return True if the given text appears to describe a crisis.

        The heuristic combines a negative sentiment score with the presence
        of one or more crisis keywords. Either condition on its own will
        trigger crisis mode; requiring both simultaneously would be too
        conservative and might miss urgent issues.

        Args:
            text: Arbitrary natural language input to analyse.

        Returns:
            True when a crisis is detected, False otherwise.
        """
        if not text:
            return False

        # Check for keywords
        lowered = text.lower()
        if any(keyword in lowered for keyword in self.crisis_keywords):
            return True

        # Fallback to sentiment analysis
        sentiment = self.sentiment_service.analyze_sentiment(text)
        return sentiment.get("score", 0.0) < self.sentiment_threshold

    def activate(self, *, reason: str) -> None:
        """Enter crisis mode and log the transition."""

        if not self._active:
            logger.warning("crisis_state=PAUSED reason=%s", reason)
            logger.info("calm_statement=Holding fire until signals stabilize")
        self._active = True
        self._reason = reason

    def resolve(self, *, reason: str = "monitor_clear") -> None:
        """Exit crisis mode and log a calming statement."""

        if self._active:
            logger.info("crisis_state=NORMAL reason=%s", reason)
        self._active = False
        self._reason = None

    def is_paused(self) -> bool:
        return self._active

    def guard(self, *, action: str) -> bool:
        """Return False when crisis mode blocks the outbound action."""

        if self._active:
            logger.info("crisis_guard_blocked action=%s", action)
            return False
        return True

    @property
    def reason(self) -> Optional[str]:
        return self._reason


__all__ = ["CrisisService"]