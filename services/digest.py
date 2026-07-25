"""Weekly state-of-the-mind digest.

One honest page answering "is this mind actually getting better?" — forecast
calibration, memory growth, relationship depth, measured revenue vs. the
legacy click estimate, safety history, and what is waiting on the operator.
Read-only: the digest computes and reports, it never changes behavior.

It also proposes bandit-space widenings as `ExperimentProposal`s — the
planner may suggest new arm values, but nothing reaches the optimizer until
a human approves it, mirroring the discovery/OKR gates.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any, Dict, List, Optional

from db.models import (
    ApprovalRequest, Conversion, DiscoveryProposal, ExperimentProposal,
    GoalProposal, MediaAssetDraft, Relationship, Tweet,
)
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)


class DigestService:
    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def build(self, session: Any, reception_predictor: Any = None) -> Dict[str, Any]:
        """Assemble the digest. Every number comes from stored state."""
        now = datetime.now(UTC)
        week_ago = now - timedelta(days=7)

        calibration: Dict[str, Any] = {}
        if reception_predictor is not None:
            try:
                calibration = reception_predictor.prediction_accuracy(session)
            except Exception as exc:
                logger.error(f"Digest calibration failed: {exc}")

        tweets = session.query(Tweet).all()
        recent_tweets = [t for t in tweets if t.created_at >= week_ago]
        conversions = session.query(Conversion).all()
        recent_revenue = sum(
            c.value for c in conversions if c.occurred_at >= week_ago
        )
        relationships = session.query(Relationship).all()
        deep = [r for r in relationships if r.interaction_count >= 3]

        pending = {
            "approvals": session.query(ApprovalRequest)
                .filter(lambda r: r.status == "pending").count(),
            "discoveries": session.query(DiscoveryProposal)
                .filter(lambda p: p.status == "pending").count(),
            "goals": session.query(GoalProposal)
                .filter(lambda p: p.status == "pending").count(),
            "experiments": session.query(ExperimentProposal)
                .filter(lambda p: p.status == "pending").count(),
            "media_drafts": session.query(MediaAssetDraft)
                .filter(lambda d: d.approval_status == "pending").count(),
        }

        digest = {
            "generated_at": now.isoformat(),
            "calibration": calibration or {"pairs": 0},
            "memory": self._memory_counts(),
            "activity": {
                "posts_this_week": len(recent_tweets),
                "posts_total": len(tweets),
                "mean_j_score_this_week": self._mean(
                    [t.j_score for t in recent_tweets if t.j_score is not None]
                ),
            },
            "relationships": {
                "known_accounts": len(relationships),
                "recurring_accounts": len(deep),
                "mean_sentiment": self._mean([r.sentiment_score for r in relationships]),
            },
            "revenue": {
                "measured_conversions": len(conversions),
                "measured_revenue_7d": round(recent_revenue, 2),
                "measured_revenue_total": round(sum(c.value for c in conversions), 2),
            },
            "safety": self._safety_history(),
            "pending_human_decisions": pending,
        }
        self.ledger.record("weekly_digest", {
            "calibration_pairs": digest["calibration"].get("pairs", 0),
            "posts_this_week": digest["activity"]["posts_this_week"],
            "pending": pending,
        })
        return digest

    def _memory_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for label, getter in (
            ("lessons", "services.semantic_index:get_semantic_index"),
            ("world_observations", "services.world_model:get_world_model"),
            ("evidence", "services.evidence_library:get_evidence_library"),
        ):
            try:
                module_name, func_name = getter.split(":")
                module = __import__(module_name, fromlist=[func_name])
                counts[label] = len(getattr(module, func_name)())
            except Exception as exc:
                logger.error(f"Digest memory count for {label} failed: {exc}")
                counts[label] = -1
        return counts

    def _safety_history(self) -> Dict[str, int]:
        history = {}
        for event in ("armed", "arm_refused", "breaker_tripped", "breaker_reset",
                      "constitution_tampered", "operator_sms_rejected"):
            try:
                history[event] = len(self.ledger.replay(event))
            except Exception:
                history[event] = -1
        return history

    @staticmethod
    def _mean(values: List[float]) -> Optional[float]:
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        return round(sum(clean) / len(clean), 4)

    # ------------------------------------------------------------------ #
    # Gated experiment proposals
    # ------------------------------------------------------------------ #
    def propose_experiments(self, session: Any, experiments_service: Any) -> List[ExperimentProposal]:
        """Propose new bandit arm values from observed performance.

        Topics that repeatedly earn strong J-scores but are not in the arm
        space become proposals. Approval is required before the optimizer
        may ever sample them."""
        proposals: List[ExperimentProposal] = []
        try:
            known_topics = set(experiments_service.arms.get("topic", []))
            scored = [t for t in session.query(Tweet).all()
                      if t.topic and t.j_score is not None]
            by_topic: Dict[str, List[float]] = {}
            for tweet in scored:
                by_topic.setdefault(tweet.topic, []).append(tweet.j_score)

            existing = {
                (p.dimension, p.value)
                for p in session.query(ExperimentProposal).all()
            }

            for topic, scores in by_topic.items():
                if topic in known_topics or len(scores) < 3:
                    continue
                mean_score = sum(scores) / len(scores)
                if mean_score < 0.5:
                    continue
                if ("topic", topic) in existing:
                    continue
                proposal = ExperimentProposal(
                    dimension="topic",
                    value=topic,
                    rationale=(
                        f"'{topic}' averaged J={mean_score:.2f} across {len(scores)} "
                        "posts but is not in the bandit's topic arms"
                    ),
                    evidence={"samples": len(scores), "mean_j": round(mean_score, 4)},
                )
                session.add(proposal)
                proposals.append(proposal)
                self.ledger.record("experiment_proposal", {
                    "id": proposal.id, "dimension": "topic", "value": topic,
                    "mean_j": round(mean_score, 4), "samples": len(scores),
                })
            if proposals:
                session.commit()
        except Exception as exc:
            logger.error(f"Experiment proposal generation failed: {exc}")
        return proposals

    def apply_approved_experiments(self, session: Any, experiments_service: Any) -> int:
        """Fold human-approved proposals into the arm space. Only approvals
        widen what the optimizer may explore."""
        applied = 0
        try:
            approved = (
                session.query(ExperimentProposal)
                .filter(lambda p: p.status == "approved")
                .all()
            )
            for proposal in approved:
                arm_values = experiments_service.arms.get(proposal.dimension)
                if arm_values is None or proposal.value in arm_values:
                    continue
                arm_values.append(proposal.value)
                experiments_service._arm_combinations = None  # invalidate cache
                applied += 1
            if applied:
                self.ledger.record("experiment_applied", {"count": applied})
        except Exception as exc:
            logger.error(f"Applying approved experiments failed: {exc}")
        return applied


_SHARED_DIGEST: Optional[DigestService] = None


def get_digest_service() -> DigestService:
    global _SHARED_DIGEST
    if _SHARED_DIGEST is None:
        _SHARED_DIGEST = DigestService()
    return _SHARED_DIGEST


__all__ = ["DigestService", "get_digest_service"]
