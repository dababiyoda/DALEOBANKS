"""Analytics service for mission-aligned impact measurement."""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, UTC
import statistics
import re

from db.models import (
    Tweet,
    FollowersSnapshot,
    Redirect,
    Action,
    PilotAcceptance,
    ArtifactFork,
    CoalitionPartner,
    Citation,
    HelpfulnessFeedback,
)
from services.logging_utils import get_logger

logger = get_logger(__name__)

class AnalyticsService:
    """Comprehensive analytics for the AI agent.

    The analytics service aggregates social metrics, revenue proxies
    and authority signals into a set of higher‑level KPIs. It also
    computes an objective score (J score) using configurable weightings
    defined in the application configuration. An optional impact
    metric combines growth and authority into a single measure.
    """

    def __init__(self):
        from config import get_config
        # Load configuration once for weight lookups
        self.config = get_config()
        self.engagement_weights = {
            "likes": 1.0,
            "rts": 2.0,
            "replies": 1.5,
            "quotes": 1.5
        }
        default_signal_weights = {
            "pilots": 0.3,
            "artifacts": 0.2,
            "coalitions": 0.2,
            "citations": 0.15,
            "helpfulness": 0.15,
        }
        impact_signal_weights = self.config.GOAL_WEIGHTS.get("IMPACT_SIGNALS", {})
        merged_weights = {**default_signal_weights, **impact_signal_weights}
        self.signal_weights = self._normalize_weight_map(merged_weights)
        self.signal_targets = {
            "pilots": 3,
            "artifacts": 5,
            "coalitions": 4,
            "citations": 6,
            "helpfulness": 5,
        }
    
    async def pull_and_update_metrics(self, session: Any, x_client) -> Dict[str, Any]:
        """Pull latest metrics from X API and update database.

        The method is ``async`` because the underlying X client uses
        asynchronous calls for fetching tweet metrics. This keeps the
        scheduler coroutine-friendly and prevents blocking the event
        loop while waiting on network operations.
        """
        try:
            # Get recent tweets that need metric updates
            cutoff = datetime.now(UTC) - timedelta(hours=6)
            tweets_to_update = (
                session.query(Tweet)
                .filter(lambda tweet: tweet.created_at >= cutoff)
                .all()
            )
            
            if not tweets_to_update or not x_client:
                return {"updated_count": 0}
            
            # Get tweet IDs
            tweet_ids = [tweet.id for tweet in tweets_to_update]
            
            # Fetch metrics from X API
            metrics = await x_client.metrics_for(tweet_ids)
            
            updated_count = 0
            penalty_recent = self.calculate_penalty_score(session, days=1)
            impact_snapshot = self.calculate_impact_score(session, days=7)
            mission_alignment = impact_snapshot["impact_score"] / 100 if impact_snapshot else 0.0
            for tweet in tweets_to_update:
                if tweet.id in metrics:
                    tweet_metrics = metrics[tweet.id]

                    # Update metrics
                    tweet.likes = tweet_metrics.get("like_count", 0)
                    tweet.rts = tweet_metrics.get("retweet_count", 0)
                    tweet.replies = tweet_metrics.get("reply_count", 0)
                    tweet.quotes = tweet_metrics.get("quote_count", 0)
                    
                    # Calculate authority-weighted engagement
                    tweet.authority_score = self._calculate_authority_score(tweet_metrics)

                    # Calculate J-score with mission alignment from structured signals
                    tweet.j_score = self._calculate_j_score(
                        tweet,
                        penalty=penalty_recent,
                        mission_alignment=mission_alignment,
                    )
                    
                    updated_count += 1
            
            session.commit()
            logger.info(f"Updated metrics for {updated_count} tweets")

            weekly_impact = impact_snapshot["impact_score"]
            revenue_today = self.calculate_revenue_per_day(session)
            authority_week = self.calculate_authority_signals(session, days=7)
            fame_week = self.calculate_fame_score(session, days=7)["fame_score"]
            penalty_week = self.calculate_penalty_score(session, days=7)
            j_score = self.calculate_goal_aligned_j_score(
                impact=weekly_impact,
                revenue=revenue_today,
                authority=authority_week,
                fame=fame_week,
                penalty=penalty_week,
            )

            return {
                "updated_count": updated_count,
                "j_score": j_score,
                "impact": weekly_impact,
                "revenue": revenue_today,
                "authority": authority_week,
                "fame": fame_week,
                "penalty": penalty_week,
            }
            
        except Exception as e:
            logger.error(f"Metrics update failed: {e}")
            session.rollback()
            return {"error": str(e)}
    
    def calculate_fame_score(self, session: Any, days: int = 1) -> Dict[str, float]:
        """Calculate Fame Score using engagement proxy and follower growth"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        
        # Get tweets in period
        tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= cutoff)
            .all()
        )
        
        if not tweets:
            return {"fame_score": 0.0, "engagement_proxy": 0.0, "follower_delta": 0.0}
        
        # Calculate engagement proxy
        total_engagement = 0
        for tweet in tweets:
            engagement = (
                self.engagement_weights["likes"] * (tweet.likes or 0) +
                self.engagement_weights["rts"] * (tweet.rts or 0) +
                self.engagement_weights["replies"] * (tweet.replies or 0) +
                self.engagement_weights["quotes"] * (tweet.quotes or 0)
            )
            total_engagement += engagement
        
        # Get follower growth
        follower_delta = self._get_follower_delta(session, days)
        
        # Z-score normalization (simplified)
        # In production, you'd maintain rolling statistics
        engagement_z = self._simple_z_score(total_engagement, mean=100, std=50)
        follower_z = self._simple_z_score(follower_delta, mean=10, std=20)
        
        # Fame Score = z(engagement_proxy) + z(Δfollowers)
        fame_score = engagement_z + follower_z
        
        return {
            "fame_score": round(fame_score, 2),
            "engagement_proxy": total_engagement,
            "follower_delta": follower_delta,
            "engagement_z": round(engagement_z, 2),
            "follower_z": round(follower_z, 2)
        }
    
    def calculate_revenue_per_day(self, session: Any) -> float:
        """Calculate revenue per day from tracked redirects"""
        # Get all redirects and their click data
        redirects = session.query(Redirect).all()
        
        total_revenue = 0.0
        for redirect in redirects:
            # Revenue = clicks × revenue per click
            revenue_per_click = 0.05  # Default $0.05 per click
            redirect_revenue = redirect.clicks * revenue_per_click
            total_revenue += redirect_revenue
        
        return round(total_revenue, 2)
    
    def calculate_authority_signals(self, session: Any, days: int = 1) -> float:
        """Calculate authority signals from verified/high-follower interactions"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        
        tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= cutoff)
            .all()
        )
        
        total_authority = sum(tweet.authority_score or 0 for tweet in tweets)
        
        # Normalize to reasonable range
        return round(min(total_authority / 10, 100), 2)
    
    def calculate_penalty_score(self, session: Any, days: int = 1) -> float:
        """Calculate penalty score from rate limits, violations, etc."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        
        # Count rate limit strikes
        recent_actions = (
            session.query(Action)
            .filter(lambda action: action.created_at >= cutoff)
            .all()
        )

        rate_limit_actions = sum(
            1 for action in recent_actions
            if action.kind and "rate_limit" in action.kind
        )

        penalty_action_kinds = {"mute_detected", "block_detected", "ethics_violation"}
        penalty_actions = sum(
            1 for action in recent_actions
            if action.kind in penalty_action_kinds
        )

        penalty_score = rate_limit_actions * 2 + penalty_actions * 5

        return float(penalty_score)

    def record_pilot_acceptance(
        self,
        session: Any,
        *,
        pilot_name: str,
        accepted_by: Optional[str] = None,
        scope: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        accepted_at: Optional[datetime] = None,
    ) -> None:
        """Persist a pilot acceptance signal."""

        record = PilotAcceptance(
            pilot_name=pilot_name,
            accepted_by=accepted_by,
            scope=scope,
            accepted_at=accepted_at or datetime.now(UTC),
            metadata=metadata or {},
        )
        session.add(record)

    def record_artifact_fork(
        self,
        session: Any,
        *,
        artifact_name: str,
        source_url: Optional[str] = None,
        platform: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        forked_at: Optional[datetime] = None,
    ) -> None:
        """Persist an artifact fork signal."""

        record = ArtifactFork(
            artifact_name=artifact_name,
            source_url=source_url,
            platform=platform,
            forked_at=forked_at or datetime.now(UTC),
            metadata=metadata or {},
        )
        session.add(record)

    def record_coalition_partner(
        self,
        session: Any,
        *,
        partner_name: str,
        partner_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        joined_at: Optional[datetime] = None,
    ) -> None:
        """Persist a coalition partner signal."""

        record = CoalitionPartner(
            partner_name=partner_name,
            partner_type=partner_type,
            joined_at=joined_at or datetime.now(UTC),
            metadata=metadata or {},
        )
        session.add(record)

    def record_citation(
        self,
        session: Any,
        *,
        source_title: str,
        url: Optional[str] = None,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cited_at: Optional[datetime] = None,
    ) -> None:
        """Persist a citation signal."""

        record = Citation(
            source_title=source_title,
            url=url,
            context=context,
            cited_at=cited_at or datetime.now(UTC),
            metadata=metadata or {},
        )
        session.add(record)

    def record_helpfulness_feedback(
        self,
        session: Any,
        *,
        channel: str,
        rating: float,
        comment: Optional[str] = None,
        reference_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        captured_at: Optional[datetime] = None,
    ) -> None:
        """Persist helpfulness feedback."""

        record = HelpfulnessFeedback(
            channel=channel,
            rating=rating,
            comment=comment,
            reference_id=reference_id,
            captured_at=captured_at or datetime.now(UTC),
            metadata=metadata or {},
        )
        session.add(record)

    def record_structured_outcome(
        self,
        session: Any,
        kind: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist structured outcome signals derived from action metadata."""

        if not metadata:
            return

        pilots = self._iterify(metadata.get("pilot_acceptances") or metadata.get("pilots_accepted"))
        for entry in pilots:
            if isinstance(entry, dict):
                self.record_pilot_acceptance(
                    session,
                    pilot_name=entry.get("pilot_name") or entry.get("name") or kind,
                    accepted_by=entry.get("accepted_by"),
                    scope=entry.get("scope"),
                    metadata={"source": kind, **{k: v for k, v in entry.items() if k not in {"pilot_name", "name", "accepted_by", "scope"}}},
                    accepted_at=entry.get("accepted_at"),
                )
            else:
                self.record_pilot_acceptance(
                    session,
                    pilot_name=str(entry) if entry is not None else kind,
                    metadata={"source": kind},
                )

        forks = self._iterify(metadata.get("artifact_forks") or metadata.get("forks"))
        for entry in forks:
            if isinstance(entry, dict):
                self.record_artifact_fork(
                    session,
                    artifact_name=entry.get("artifact_name") or entry.get("name") or kind,
                    source_url=entry.get("url") or entry.get("source_url"),
                    platform=entry.get("platform"),
                    metadata={"source": kind, **{k: v for k, v in entry.items() if k not in {"artifact_name", "name", "url", "source_url", "platform"}}},
                    forked_at=entry.get("forked_at"),
                )
            else:
                self.record_artifact_fork(
                    session,
                    artifact_name=str(entry) if entry is not None else kind,
                    metadata={"source": kind},
                )

        partners = self._iterify(metadata.get("coalition_partners") or metadata.get("partners"))
        for entry in partners:
            if isinstance(entry, dict):
                self.record_coalition_partner(
                    session,
                    partner_name=entry.get("partner_name") or entry.get("name") or kind,
                    partner_type=entry.get("partner_type") or entry.get("type"),
                    metadata={"source": kind, **{k: v for k, v in entry.items() if k not in {"partner_name", "name", "partner_type", "type"}}},
                    joined_at=entry.get("joined_at"),
                )
            else:
                self.record_coalition_partner(
                    session,
                    partner_name=str(entry) if entry is not None else kind,
                    metadata={"source": kind},
                )

        citations = self._iterify(metadata.get("citations") or metadata.get("receipts"))
        for entry in citations:
            if isinstance(entry, dict):
                self.record_citation(
                    session,
                    source_title=entry.get("source_title") or entry.get("title") or (entry.get("url") or kind),
                    url=entry.get("url"),
                    context=entry.get("context"),
                    metadata={"source": kind, **{k: v for k, v in entry.items() if k not in {"source_title", "title", "url", "context"}}},
                    cited_at=entry.get("cited_at"),
                )
            else:
                self.record_citation(
                    session,
                    source_title=str(entry) if entry is not None else kind,
                    url=str(entry) if isinstance(entry, str) and entry.startswith("http") else None,
                    metadata={"source": kind},
                )

        feedback_entries = self._iterify(metadata.get("helpfulness_feedback") or metadata.get("feedback"))
        for entry in feedback_entries:
            if isinstance(entry, dict):
                rating = float(entry.get("rating", 0.0))
                if rating <= 0 and "sentiment" in entry:
                    sentiment = entry.get("sentiment", "neutral")
                    rating = 4.0 if sentiment == "positive" else 2.0 if sentiment == "neutral" else 1.0
                self.record_helpfulness_feedback(
                    session,
                    channel=entry.get("channel") or entry.get("source") or "unknown",
                    rating=rating,
                    comment=entry.get("comment"),
                    reference_id=entry.get("reference_id"),
                    metadata={"source": kind, **{k: v for k, v in entry.items() if k not in {"channel", "source", "rating", "comment", "reference_id", "sentiment"}}},
                    captured_at=entry.get("captured_at"),
                )
            elif entry is not None:
                self.record_helpfulness_feedback(
                    session,
                    channel="unknown",
                    rating=float(entry) if isinstance(entry, (int, float)) else 0.0,
                    metadata={"source": kind},
                )

    def derive_structured_outcome_from_text(
        self,
        *,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Heuristically derive structured outcome signals from generated text."""

        context = context or {}
        lowered = content.lower()
        signals: Dict[str, Any] = {}

        if "pilot accepted" in lowered or "signed the pilot" in lowered:
            signals["pilot_acceptances"] = [
                {
                    "pilot_name": context.get("topic", "pilot"),
                    "accepted_by": context.get("audience"),
                    "scope": context.get("scope"),
                }
            ]

        if "fork" in lowered or "clone" in lowered:
            signals["artifact_forks"] = [
                {
                    "artifact_name": context.get("artifact", context.get("topic", "artifact")),
                    "platform": "github" if "github" in lowered else None,
                }
            ]

        if "coalition" in lowered or "partner" in lowered or "ally" in lowered:
            signals["coalition_partners"] = [
                {
                    "partner_name": context.get("partner") or context.get("topic", "partner"),
                    "partner_type": context.get("partner_type"),
                }
            ]

        citations = self.extract_citations_from_text(content)
        if citations:
            signals["citations"] = [
                {"url": url, "source_title": url, "context": context.get("topic")}
                for url in citations
            ]

        if any(word in lowered for word in ["thank you", "appreciate", "super helpful", "that helps"]):
            signals["helpfulness_feedback"] = [
                {
                    "channel": context.get("channel", "x"),
                    "rating": 4.5,
                    "comment": "Positive acknowledgement detected",
                }
            ]

        return signals

    def extract_citations_from_text(self, content: str) -> List[str]:
        """Extract citation-like URLs from text."""

        if not content:
            return []

        pattern = re.compile(r"https?://[^\s)]+")
        return pattern.findall(content)

    def _iterify(self, value: Any) -> List[Any]:
        """Ensure the provided value is treated as a list."""

        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (set, tuple)):
            return list(value)
        return [value]

    def _normalize_weight_map(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normalize a weight mapping so the values sum to 1."""

        positive_weights = {k: max(v, 0.0) for k, v in weights.items()}
        total = sum(positive_weights.values())
        if total <= 0:
            count = len(weights) or 1
            return {key: 1.0 / count for key in weights} if weights else {}
        return {key: value / total for key, value in positive_weights.items()}

    def calculate_impact_score(self, session: Any, days: int = 1) -> Dict[str, Any]:
        """Calculate mission-aligned impact from structured outcomes."""

        cutoff = datetime.now(UTC) - timedelta(days=days)

        pilots = (
            session.query(PilotAcceptance)
            .filter(lambda record: record.accepted_at >= cutoff)
            .all()
        )
        forks = (
            session.query(ArtifactFork)
            .filter(lambda record: record.forked_at >= cutoff)
            .all()
        )
        partners = (
            session.query(CoalitionPartner)
            .filter(lambda record: record.joined_at >= cutoff)
            .all()
        )
        citations = (
            session.query(Citation)
            .filter(lambda record: record.cited_at >= cutoff)
            .all()
        )
        feedback_entries = (
            session.query(HelpfulnessFeedback)
            .filter(lambda record: record.captured_at >= cutoff)
            .all()
        )

        pilot_count = len(pilots)
        fork_count = len(forks)
        partner_count = len(partners)
        citation_count = len(citations)
        helpfulness_count = len(feedback_entries)
        helpfulness_avg = (
            statistics.fmean(entry.rating for entry in feedback_entries)
            if feedback_entries
            else 0.0
        )

        normalized = {
            "pilots": min(pilot_count / max(self.signal_targets["pilots"], 1), 1.0),
            "artifacts": min(fork_count / max(self.signal_targets["artifacts"], 1), 1.0),
            "coalitions": min(partner_count / max(self.signal_targets["coalitions"], 1), 1.0),
            "citations": min(citation_count / max(self.signal_targets["citations"], 1), 1.0),
            "helpfulness": min(helpfulness_avg / max(self.signal_targets["helpfulness"], 1), 1.0)
            if helpfulness_count
            else 0.0,
        }

        weighted_sum = sum(
            self.signal_weights.get(key, 0.0) * normalized.get(key, 0.0)
            for key in self.signal_weights
        )

        impact_score = round(weighted_sum * 100, 2)

        components = {
            "pilots": {"count": pilot_count, "normalized": round(normalized["pilots"], 3)},
            "artifacts": {"count": fork_count, "normalized": round(normalized["artifacts"], 3)},
            "coalitions": {"count": partner_count, "normalized": round(normalized["coalitions"], 3)},
            "citations": {"count": citation_count, "normalized": round(normalized["citations"], 3)},
            "helpfulness": {
                "count": helpfulness_count,
                "average_rating": round(helpfulness_avg, 2),
                "normalized": round(normalized["helpfulness"], 3),
            },
        }

        return {
            "impact_score": impact_score,
            "components": components,
            "weights": self.signal_weights,
        }

    def calculate_goal_aligned_j_score(
        self,
        *,
        impact: float,
        revenue: float,
        authority: float,
        fame: float,
        penalty: float = 0.0,
    ) -> float:
        """Calculate a global J-score using configured weights and penalties."""

        weights = {
            "impact": self.config.WEIGHTS_IMPACT.get("alpha", 0.4),
            "revenue": self.config.WEIGHTS_REVENUE.get("alpha", 0.3),
            "authority": self.config.WEIGHTS_AUTHORITY.get("alpha", 0.2),
            "fame": self.config.WEIGHTS_FAME.get("alpha", 0.1),
        }

        goal_mode = (
            self.config.GOAL_MODE.upper()
            if isinstance(self.config.GOAL_MODE, str)
            else "IMPACT"
        )
        penalty_weight = self.config.GOAL_WEIGHTS.get(
            goal_mode,
            {"lambda": 0.1},
        ).get("lambda", 0.1)

        if impact < self.config.IMPACT_WEEKLY_FLOOR:
            weights["revenue"] *= 0.5

        total_weight = sum(weights.values()) or 1.0
        normalized_weights = {k: v / total_weight for k, v in weights.items()}

        normalized_metrics = {
            "impact": max(0.0, min(impact / max(self.config.IMPACT_WEEKLY_FLOOR, 1), 1.0)),
            "revenue": max(0.0, min(revenue / 100.0, 1.0)),
            "authority": max(0.0, min(authority / 100.0, 1.0)),
            "fame": max(0.0, min(fame / 100.0, 1.0)),
        }
        penalty_normalized = max(0.0, min(penalty / 10.0, 1.0))

        score = sum(
            normalized_weights[key] * normalized_metrics[key]
            for key in normalized_weights
        ) - penalty_weight * penalty_normalized
        return round(max(score, 0.0), 3)
    
    def get_analytics_summary(self, session: Any) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        # Today's metrics
        today_fame = self.calculate_fame_score(session, days=1)
        today_revenue = self.calculate_revenue_per_day(session)
        today_authority = self.calculate_authority_signals(session, days=1)
        today_penalty = self.calculate_penalty_score(session, days=1)
        today_impact = self.calculate_impact_score(session, days=1)

        # Yesterday's metrics for comparison
        yesterday_fame = self.calculate_fame_score(session, days=2)
        yesterday_impact = self.calculate_impact_score(session, days=2)
        yesterday_revenue = 0.0  # Simplified for now; could be computed similarly

        # Determine weight set based on current goal mode
        goal_mode = self.config.GOAL_MODE.upper() if isinstance(self.config.GOAL_MODE, str) else "IMPACT"
        weights = self.config.GOAL_WEIGHTS.get(goal_mode, {
            "alpha": 0.4,
            "beta": 0.3,
            "gamma": 0.2,
            "lambda": 0.1,
        })
        alpha = weights.get("alpha", 0.4)
        beta = weights.get("beta", 0.3)
        gamma = weights.get("gamma", 0.2)
        lambda_penalty = weights.get("lambda", 0.1)

        # Select primary metric based on goal mode
        if goal_mode == "IMPACT":
            primary = today_impact["impact_score"]
        elif goal_mode == "REVENUE" or goal_mode == "MONETIZE":
            primary = today_revenue
        elif goal_mode == "AUTHORITY":
            primary = today_authority
        else:  # FAME and all others
            primary = today_fame["fame_score"]

        # Compose objective score. We include fame_score and authority_signals as
        # secondary metrics for most modes except where the primary overlaps.
        objective_score = (
            alpha * primary +
            beta * today_revenue +
            gamma * today_authority -
            lambda_penalty * today_penalty
        )

        # Get follower count
        latest_follower_snapshot = (
            session.query(FollowersSnapshot)
            .order_by(lambda snapshot: snapshot.ts, descending=True)
            .first()
        )
        follower_count = latest_follower_snapshot.follower_count if latest_follower_snapshot else 0

        # Recent activity
        recent_tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= datetime.now(UTC) - timedelta(hours=24))
            .count()
        )

        return {
            "fame_score": today_fame["fame_score"],
            "fame_score_change": today_fame["fame_score"] - yesterday_fame.get("fame_score", 0),
            "impact_score": today_impact["impact_score"],
            "impact_change": today_impact["impact_score"] - yesterday_impact.get("impact_score", 0),
            "revenue_today": today_revenue,
            "revenue_change": today_revenue - yesterday_revenue,
            "authority_signals": today_authority,
            "penalty_score": today_penalty,
            "objective_score": round(objective_score, 2),
            "follower_count": follower_count,
            "follower_change": today_fame["follower_delta"],
            "tweets_today": recent_tweets,
            "engagement_rate": self._calculate_engagement_rate(session),
            "last_updated": datetime.now(UTC).isoformat(),
        }
    
    def create_follower_snapshot(self, session: Any, follower_count: int):
        """Create a follower count snapshot"""
        snapshot = FollowersSnapshot(
            ts=datetime.now(UTC),
            follower_count=follower_count
        )
        session.add(snapshot)
        session.commit()
        logger.info(f"Created follower snapshot: {follower_count}")
    
    def get_follower_history(self, session: Any, days: int = 30) -> List[Dict[str, Any]]:
        """Get follower count history"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        
        snapshots = (
            session.query(FollowersSnapshot)
            .filter(lambda snapshot: snapshot.ts >= cutoff)
            .order_by(lambda snapshot: snapshot.ts)
            .all()
        )
        
        return [
            {
                "timestamp": snapshot.ts.isoformat(),
                "follower_count": snapshot.follower_count
            }
            for snapshot in snapshots
        ]
    
    def _calculate_authority_score(self, tweet_metrics: Dict[str, Any]) -> float:
        """Calculate authority score for a tweet based on engagement quality"""
        # This would analyze who engaged (verified users, high followers, etc.)
        # For now, use a simple heuristic based on engagement patterns
        
        likes = tweet_metrics.get("like_count", 0)
        rts = tweet_metrics.get("retweet_count", 0)
        replies = tweet_metrics.get("reply_count", 0)
        
        # High retweet-to-like ratio often indicates authority engagement
        if likes > 0:
            rt_ratio = rts / likes
            authority_score = min(rt_ratio * 10, 10)  # Cap at 10
        else:
            authority_score = 0
        
        # Boost for high reply engagement (indicates discussion)
        if replies > 5:
            authority_score += min(replies * 0.5, 5)
        
        return authority_score
    
    def _calculate_j_score(
        self,
        tweet: Tweet,
        *,
        penalty: float = 0.0,
        mission_alignment: float = 0.0,
    ) -> float:
        """Calculate the objective function J score for a tweet."""

        engagement = (
            self.engagement_weights["likes"] * (tweet.likes or 0)
            + self.engagement_weights["rts"] * (tweet.rts or 0)
            + self.engagement_weights["replies"] * (tweet.replies or 0)
            + self.engagement_weights["quotes"] * (tweet.quotes or 0)
        )

        engagement_score = min(engagement / 100, 1.0)
        mission_score = max(0.0, min(mission_alignment, 1.0))

        weights = {"engagement": 0.5, "mission": 0.5}
        j_score = (
            weights["engagement"] * engagement_score
            + weights["mission"] * mission_score
        )

        goal_mode = (
            self.config.GOAL_MODE.upper()
            if isinstance(self.config.GOAL_MODE, str)
            else "IMPACT"
        )
        penalty_weight = self.config.GOAL_WEIGHTS.get(
            goal_mode,
            {"lambda": 0.1},
        ).get("lambda", 0.1)
        penalty_normalized = max(0.0, min(penalty / 10.0, 1.0))

        adjusted_score = max(j_score - penalty_weight * penalty_normalized, 0.0)

        return round(adjusted_score, 3)
    
    def _get_follower_delta(self, session: Any, days: int) -> float:
        """Get follower count change over specified days"""
        now = datetime.now(UTC)
        start_time = now - timedelta(days=days)
        
        # Get snapshots at start and end of period
        start_snapshot = (
            session.query(FollowersSnapshot)
            .filter(lambda snapshot: snapshot.ts <= start_time)
            .order_by(lambda snapshot: snapshot.ts, descending=True)
            .first()
        )

        end_snapshot = (
            session.query(FollowersSnapshot)
            .filter(lambda snapshot: snapshot.ts <= now)
            .order_by(lambda snapshot: snapshot.ts, descending=True)
            .first()
        )
        
        if not start_snapshot or not end_snapshot:
            return 0.0
        
        return float(end_snapshot.follower_count - start_snapshot.follower_count)
    
    def _simple_z_score(self, value: float, mean: float, std: float) -> float:
        """Simple z-score calculation"""
        if std == 0:
            return 0.0
        return (value - mean) / std
    
    def _calculate_engagement_rate(self, session: Any) -> float:
        """Calculate overall engagement rate"""
        recent_tweets = (
            session.query(Tweet)
            .filter(lambda tweet: tweet.created_at >= datetime.now(UTC) - timedelta(days=7))
            .all()
        )
        
        if not recent_tweets:
            return 0.0
        
        total_engagement = 0
        for tweet in recent_tweets:
            engagement = (tweet.likes or 0) + (tweet.rts or 0) + (tweet.replies or 0) + (tweet.quotes or 0)
            total_engagement += engagement
        
        # Get approximate follower count
        latest_snapshot = (
            session.query(FollowersSnapshot)
            .order_by(lambda snapshot: snapshot.ts, descending=True)
            .first()
        )
        
        follower_count = latest_snapshot.follower_count if latest_snapshot else 1000
        
        avg_engagement = total_engagement / len(recent_tweets)
        engagement_rate = (avg_engagement / follower_count) * 100
        
        return round(min(engagement_rate, 100), 2)
