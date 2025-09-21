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

from typing import List, Dict

from services.sentiment import SentimentService


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


__all__ = ["CrisisService"]