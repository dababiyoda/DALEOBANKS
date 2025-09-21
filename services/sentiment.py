"""
sentiment.py
-------------

This module exposes a very lightweight sentiment analysis service. It
uses simple word lists to score text on a scale from -1 (very
negative) to +1 (very positive). The service is intended as a safe
fallback when external API calls (such as to OpenAI or other NLP
providers) are unavailable. It deliberately avoids network requests
and heavyweight ML libraries.

The scoring algorithm counts occurrences of predefined positive and
negative words. The final sentiment score is the normalized difference
between positive and negative counts. Unknown words have no effect.
"""

from __future__ import annotations

from typing import Dict, List


class SentimentService:
    """Naïve sentiment analysis based on word lists."""

    def __init__(self):
        # A very small lexicon of positive and negative terms. In a real
        # system you would expand this list or integrate a proper NLP
        # library. These lists are purposefully short to keep the
        # implementation simple and deterministic.
        self.positive_words: List[str] = [
            "good",
            "great",
            "excellent",
            "positive",
            "benefit",
            "success",
            "growth",
            "improve",
            "happy",
            "win",
        ]
        self.negative_words: List[str] = [
            "bad",
            "terrible",
            "horrible",
            "negative",
            "loss",
            "decline",
            "fail",
            "problem",
            "sad",
            "anger",
        ]

    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Compute a simple sentiment score for the provided text.

        The algorithm counts occurrences of known positive and negative
        terms. The sentiment score is the difference between positive
        and negative counts divided by the total number of matches. If
        there are no matches, the score is zero.

        Args:
            text: The input text to analyse.

        Returns:
            A dictionary with the raw counts and a ``score`` field in
            ``[-1.0, 1.0]``. A score of +1.0 means all matches were
            positive; -1.0 means all matches were negative.
        """
        if not text:
            return {"positive": 0, "negative": 0, "score": 0.0}

        lowered = text.lower()
        pos_count = sum(word in lowered for word in self.positive_words)
        neg_count = sum(word in lowered for word in self.negative_words)
        total = pos_count + neg_count
        score = 0.0
        if total > 0:
            score = (pos_count - neg_count) / total
        return {"positive": pos_count, "negative": neg_count, "score": score}


__all__ = ["SentimentService"]