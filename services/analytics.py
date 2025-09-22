"""
Analytics service for Fame, Authority, Revenue calculation and follower tracking
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, UTC
import statistics

from db.models import Tweet, FollowersSnapshot, Redirect, Action
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
                    
                    # Calculate J-score
                    tweet.j_score = self._calculate_j_score(tweet, penalty=penalty_recent)
                    
                    updated_count += 1
            
            session.commit()
            logger.info(f"Updated metrics for {updated_count} tweets")

            weekly_impact = self.calculate_impact_score(session, days=7)["impact_score"]
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

    def calculate_impact_score(self, session: Any, days: int = 1) -> Dict[str, float]:
        """Calculate an overall impact score.

        The impact metric is a composite of fame, revenue and authority. It
        reflects both engagement and economic outcomes. Each sub‑metric is
        normalized to keep the score within a reasonable range. The
        weights used to combine the metrics can be adjusted via the
        configuration.

        Args:
            session: A database session for querying persistent data.
            days: The number of days over which to calculate the metric.

        Returns:
            A dictionary with the impact score and its components.
        """
        fame = self.calculate_fame_score(session, days)
        revenue = self.calculate_revenue_per_day(session)
        authority = self.calculate_authority_signals(session, days)

        # Normalize revenue to align roughly with fame scale. This divisor
        # can be tuned based on typical revenue ranges (e.g. dollars per
        # day). We choose 10 so that $100/day yields a comparable score.
        revenue_norm = revenue / 10.0

        # Normalize authority score to 0–1 range by dividing by 10 (max 100)
        authority_norm = authority / 10.0

        # Apply weights from configuration for the IMPACT goal. Fallback to
        # equal weights if unspecified.
        weights = self.config.GOAL_WEIGHTS.get("IMPACT", {
            "alpha": 0.4,
            "beta": 0.3,
            "gamma": 0.2,
            "lambda": 0.1,
        })
        alpha = weights.get("alpha", 0.4)
        beta = weights.get("beta", 0.3)
        gamma = weights.get("gamma", 0.2)

        impact_score = alpha * fame["fame_score"] + beta * revenue_norm + gamma * authority_norm

        return {
            "impact_score": round(impact_score, 2),
            "fame": fame["fame_score"],
            "revenue_norm": revenue_norm,
            "authority_norm": authority_norm,
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
    
    def _calculate_j_score(self, tweet: Tweet, *, penalty: float = 0.0) -> float:
        """Calculate the objective function J score for a tweet."""
        # Simplified J calculation for individual tweets
        engagement = (
            self.engagement_weights["likes"] * (tweet.likes or 0) +
            self.engagement_weights["rts"] * (tweet.rts or 0) +
            self.engagement_weights["replies"] * (tweet.replies or 0) +
            self.engagement_weights["quotes"] * (tweet.quotes or 0)
        )

        # Normalize to 0-1 scale
        engagement_score = min(engagement / 100, 1.0)
        authority_score = min((tweet.authority_score or 0) / 10, 1.0)

        # Simple J calculation
        j_score = 0.7 * engagement_score + 0.3 * authority_score

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
