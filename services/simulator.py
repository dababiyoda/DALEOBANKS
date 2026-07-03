"""Internal simulator: predict audience reception before posting.

Before an outbound proposal is published, the predictor estimates its
J-score from the agent's own history - shrinkage-weighted means by topic
and posting hour, pulled toward the global mean when evidence is thin, so
sparse data cannot produce confident nonsense.

The prediction is advisory in this version: it is recorded in the decision
ledger next to the publish attempt (so predicted vs. actual reception can
be audited and a learned predictor can replace the heuristic later), but it
never blocks a post. Blocking on a heuristic's guess would let thin data
silence the agent; the gates that can block remain the ethics/critic ones.
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

from db.models import Tweet
from services.logging_utils import get_logger

logger = get_logger(__name__)


class ReceptionPredictor:
    """Heuristic J-score prediction from topic and hour history."""

    def __init__(self, min_samples: int = 5, shrinkage: float = 3.0) -> None:
        self.min_samples = min_samples
        self.shrinkage = shrinkage

    def predict(
        self,
        session: Any,
        *,
        topic: Optional[str],
        hour: Optional[int],
    ) -> Dict[str, Any]:
        """Predict reception. predicted_j is None while history is thin."""
        scored: List[Tweet] = (
            session.query(Tweet)
            .filter(lambda t: t.j_score is not None)
            .all()
        )
        if len(scored) < self.min_samples:
            return {
                "predicted_j": None,
                "confidence": 0.0,
                "basis": "insufficient_history",
                "samples": len(scored),
            }

        global_mean = mean(t.j_score for t in scored)

        topic_scores = [t.j_score for t in scored if topic and t.topic == topic]
        hour_scores = [t.j_score for t in scored if hour is not None and t.hour_bin == hour]

        topic_estimate = self._shrunk_mean(topic_scores, global_mean)
        hour_estimate = self._shrunk_mean(hour_scores, global_mean)
        predicted = 0.6 * topic_estimate + 0.4 * hour_estimate

        evidence = len(topic_scores) + len(hour_scores)
        confidence = round(min(evidence / 20.0, 1.0), 3)

        return {
            "predicted_j": round(predicted, 3),
            "confidence": confidence,
            "basis": "topic_hour_history",
            "samples": {
                "total_scored": len(scored),
                "topic": len(topic_scores),
                "hour": len(hour_scores),
            },
            "global_mean": round(global_mean, 3),
        }

    def _shrunk_mean(self, scores: List[float], global_mean: float) -> float:
        """Sample mean pulled toward the global mean when evidence is thin."""
        if not scores:
            return global_mean
        weight = len(scores) / (len(scores) + self.shrinkage)
        return weight * mean(scores) + (1 - weight) * global_mean


__all__ = ["ReceptionPredictor"]
