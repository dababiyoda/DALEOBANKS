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

from typing import Any, Dict, Iterable, List, Mapping, Optional, TYPE_CHECKING

from services.sentiment import SentimentService
from services.logging_utils import get_logger
from services.social_base import SocialPostResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from services.multiplexer import SocialMultiplexer

logger = get_logger(__name__)


class CrisisService:
    """Detects crisis signals in text based on sentiment and keywords."""

    def __init__(
        self,
        *,
        sentiment_service: SentimentService | None = None,
        signal_threshold: float = 12.0,
        resume_threshold: Optional[float] = None,
    ):
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
        self.signal_threshold: float = float(signal_threshold)
        self.resume_threshold: float = float(resume_threshold) if resume_threshold is not None else float(signal_threshold) / 2
        self._active: bool = False
        self._reason: Optional[str] = None
        self._metrics: Dict[str, float] = {"sentiment": 0.0, "velocity": 0.0, "authority": 1.0}
        self._last_signal: float = 0.0
        self._last_receipts: Dict[str, SocialPostResult] = {}
        self._receipts_validated: bool = False
        self._calming_message: str = (
            "We are aware of heightened concerns and are pausing outgoing updates while we verify details."
        )

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
        self._receipts_validated = False

    def resolve(self, *, reason: str = "monitor_clear") -> None:
        """Exit crisis mode and log a calming statement."""

        if self._active:
            logger.info("crisis_state=NORMAL reason=%s", reason)
        self._active = False
        self._reason = None
        self._reset_after_resolution()

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

    @property
    def last_signal(self) -> float:
        return self._last_signal

    def record_receipts(self, receipts: Mapping[str, SocialPostResult]) -> bool:
        """Record receipts from a calming message publication."""

        valid = self._validate_receipts(receipts)
        if valid:
            self._last_receipts = dict(receipts)
            self._receipts_validated = True
        return valid

    async def update_metrics(
        self,
        *,
        source: str,
        multiplexer: "SocialMultiplexer" | None,
        sentiment: Optional[float] = None,
        velocity: Optional[float] = None,
        authority: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Update crisis metrics and evaluate whether to escalate or recover."""

        if sentiment is not None:
            self._metrics["sentiment"] = float(sentiment)
        if velocity is not None:
            self._metrics["velocity"] = max(0.0, float(velocity))
        if authority is not None:
            self._metrics["authority"] = max(0.0, float(authority))

        signal = self._compute_signal()
        self._last_signal = signal

        logger.info(
            "crisis_signal_update",
            extra={
                "source": source,
                "signal": round(signal, 2),
                "metrics": dict(self._metrics),
                "active": self._active,
            },
        )

        if self._should_escalate(signal):
            await self._escalate(signal=signal, source=source, multiplexer=multiplexer, metadata=metadata)
        else:
            await self._maybe_recover(signal=signal, source=source)

        return signal

    async def evaluate_mentions(
        self,
        mentions: Iterable[Mapping[str, Any]],
        *,
        multiplexer: "SocialMultiplexer" | None,
        velocity: Optional[float] = None,
        authority_hint: Optional[float] = None,
    ) -> float:
        """Compute metrics from mentions and feed them into the crisis signal."""

        mention_list = [mention for mention in mentions if isinstance(mention, Mapping)]
        texts: List[str] = [str(mention.get("text", "")) for mention in mention_list]

        sentiment_scores = [self.sentiment_service.analyze_sentiment(text).get("score", 0.0) for text in texts if text]
        sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

        computed_velocity = velocity if velocity is not None else float(len(texts))
        authority_candidates = [self._metrics.get("authority", 1.0)]
        if isinstance(authority_hint, (int, float)):
            authority_candidates.append(float(authority_hint))
        authority_candidates.append(self._estimate_authority(mention_list))
        computed_authority = max(value for value in authority_candidates if isinstance(value, (int, float)))

        return await self.update_metrics(
            source="mentions",
            multiplexer=multiplexer,
            sentiment=sentiment,
            velocity=computed_velocity,
            authority=computed_authority,
            metadata={"samples": len(texts)},
        )

    def _compute_signal(self) -> float:
        sentiment = self._metrics.get("sentiment", 0.0)
        if sentiment >= 0:
            return 0.0
        velocity = self._metrics.get("velocity", 0.0)
        authority = max(self._metrics.get("authority", 0.0), 0.0)
        if velocity <= 0 or authority <= 0:
            return 0.0
        return abs(sentiment) * velocity * authority

    async def _escalate(
        self,
        *,
        signal: float,
        source: str,
        multiplexer: "SocialMultiplexer" | None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._active:
            reason = f"{source}_signal_{signal:.2f}"
            self.activate(reason=reason)
            receipts: Dict[str, SocialPostResult] = {}
            if multiplexer is not None:
                try:
                    receipts = await multiplexer.publish(
                        self._calming_message,
                        kind="post",
                        metadata={
                            "kind": "crisis_calm",
                            "source": source,
                            "signal": signal,
                            **(metadata or {}),
                        },
                    )
                except Exception as exc:  # pragma: no cover - logging path
                    logger.error("crisis_calm_publish_failed", extra={"error": str(exc)})
            if receipts:
                self.record_receipts(receipts)
            else:
                self._receipts_validated = False

    async def _maybe_recover(self, *, signal: float, source: str) -> None:
        if not self._active:
            return
        if signal <= self.resume_threshold:
            if self._receipts_validated:
                self.resolve(reason=f"{source}_signal_clear")
            else:
                logger.info(
                    "crisis_waiting_receipts",
                    extra={"signal": round(signal, 2), "source": source},
                )

    def _estimate_authority(self, mentions: Iterable[Mapping[str, Any]]) -> float:
        best = 1.0
        for mention in mentions:
            if not isinstance(mention, Mapping):
                continue
            scores: List[float] = []
            authority = mention.get("authority")
            if isinstance(authority, (int, float)):
                scores.append(float(authority))
            author = mention.get("author") or mention.get("author_info") or mention.get("author_metrics")
            if isinstance(author, Mapping):
                followers = author.get("followers_count") or author.get("followers") or author.get("follower_count")
                if isinstance(followers, (int, float)):
                    scores.append(float(followers) / 1000.0)
                verified = author.get("verified") or author.get("is_verified") or author.get("blue")
                if isinstance(verified, bool) and verified:
                    scores.append(3.0)
            if isinstance(mention.get("author_verified"), bool) and mention.get("author_verified"):
                scores.append(3.0)
            public_metrics = mention.get("public_metrics")
            if isinstance(public_metrics, Mapping):
                engagement = 0.0
                for key in ("like_count", "retweet_count", "reply_count", "quote_count"):
                    value = public_metrics.get(key)
                    if isinstance(value, (int, float)):
                        engagement += float(value)
                if engagement > 0:
                    scores.append(engagement / 10.0)
            if scores:
                best = max(best, max(scores))
        return best

    def _validate_receipts(self, receipts: Mapping[str, SocialPostResult]) -> bool:
        for result in receipts.values():
            if isinstance(result, SocialPostResult) and not result.dry_run:
                return True
        return False

    def _should_escalate(self, signal: float) -> bool:
        return signal >= self.signal_threshold

    def _reset_after_resolution(self) -> None:
        self._last_signal = 0.0
        self._last_receipts = {}
        self._receipts_validated = False
        self._metrics.update({"sentiment": 0.0, "velocity": 0.0})


__all__ = ["CrisisService"]
