"""
Analytics service for Fame, Authority, Revenue calculation and follower tracking
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import statistics
from sqlalchemy.orm import Session

from db.models import Tweet, FollowersSnapshot, Redirect, Action
from services.logging_utils import get_logger

logger = get_logger(__name__)

class AnalyticsService:
    """Comprehensive analytics for the AI agent"""
    
    def __init__(self):
        self.engagement_weights = {
            "likes": 1.0,
            "rts": 2.0,
            "replies": 1.5,
            "quotes": 1.5
        }
    
    def pull_and_update_metrics(self, session: Session, x_client) -> Dict[str, Any]:
        """Pull latest metrics from X API and update database"""
        try:
            # Get recent tweets that need metric updates
            cutoff = datetime.utcnow() - timedelta(hours=6)
            tweets_to_update = session.query(Tweet).filter(
                Tweet.created_at >= cutoff
            ).all()
            
            if not tweets_to_update or not x_client:
                return {"updated_count": 0}
            
            # Get tweet IDs
            tweet_ids = [tweet.id for tweet in tweets_to_update]
            
            # Fetch metrics from X API
            metrics = x_client.metrics_for(tweet_ids)
            
            updated_count = 0
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
                    tweet.j_score = self._calculate_j_score(tweet)
                    
                    updated_count += 1
            
            session.commit()
            logger.info(f"Updated metrics for {updated_count} tweets")
            
            return {"updated_count": updated_count}
            
        except Exception as e:
            logger.error(f"Metrics update failed: {e}")
            session.rollback()
            return {"error": str(e)}
    
    def calculate_fame_score(self, session: Session, days: int = 1) -> Dict[str, float]:
        """Calculate Fame Score using engagement proxy and follower growth"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get tweets in period
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= cutoff
        ).all()
        
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
    
    def calculate_revenue_per_day(self, session: Session) -> float:
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
    
    def calculate_authority_signals(self, session: Session, days: int = 1) -> float:
        """Calculate authority signals from verified/high-follower interactions"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= cutoff
        ).all()
        
        total_authority = sum(tweet.authority_score or 0 for tweet in tweets)
        
        # Normalize to reasonable range
        return round(min(total_authority / 10, 100), 2)
    
    def calculate_penalty_score(self, session: Session, days: int = 1) -> float:
        """Calculate penalty score from rate limits, violations, etc."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Count rate limit strikes
        rate_limit_actions = session.query(Action).filter(
            Action.created_at >= cutoff,
            Action.kind.like("%rate_limit%")
        ).count()
        
        # Count other penalties
        penalty_actions = session.query(Action).filter(
            Action.created_at >= cutoff,
            Action.kind.in_(["mute_detected", "block_detected", "ethics_violation"])
        ).count()
        
        penalty_score = rate_limit_actions * 2 + penalty_actions * 5
        
        return float(penalty_score)
    
    def get_analytics_summary(self, session: Session) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        # Today's metrics
        today_fame = self.calculate_fame_score(session, days=1)
        today_revenue = self.calculate_revenue_per_day(session)
        today_authority = self.calculate_authority_signals(session, days=1)
        today_penalty = self.calculate_penalty_score(session, days=1)
        
        # Yesterday's metrics for comparison
        yesterday_fame = self.calculate_fame_score(session, days=2)  # Will be adjusted
        yesterday_revenue = 0.0  # Simplified for now
        
        # Calculate objective function J
        # J = α·FameScore + β·RevenuePerDay + γ·AuthoritySignals − λ·Penalty
        alpha, beta, gamma, lambda_penalty = 0.65, 0.15, 0.25, 0.20  # FAME mode
        
        objective_score = (
            alpha * today_fame["fame_score"] +
            beta * today_revenue +
            gamma * today_authority -
            lambda_penalty * today_penalty
        )
        
        # Get follower count
        latest_follower_snapshot = session.query(FollowersSnapshot).order_by(
            FollowersSnapshot.ts.desc()
        ).first()
        
        follower_count = latest_follower_snapshot.follower_count if latest_follower_snapshot else 0
        
        # Recent activity
        recent_tweets = session.query(Tweet).filter(
            Tweet.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        return {
            "fame_score": today_fame["fame_score"],
            "fame_score_change": today_fame["fame_score"] - yesterday_fame.get("fame_score", 0),
            "revenue_today": today_revenue,
            "revenue_change": today_revenue - yesterday_revenue,
            "authority_signals": today_authority,
            "penalty_score": today_penalty,
            "objective_score": round(objective_score, 2),
            "follower_count": follower_count,
            "follower_change": today_fame["follower_delta"],
            "tweets_today": recent_tweets,
            "engagement_rate": self._calculate_engagement_rate(session),
            "last_updated": datetime.utcnow().isoformat()
        }
    
    def create_follower_snapshot(self, session: Session, follower_count: int):
        """Create a follower count snapshot"""
        snapshot = FollowersSnapshot(
            ts=datetime.utcnow(),
            follower_count=follower_count
        )
        session.add(snapshot)
        session.commit()
        logger.info(f"Created follower snapshot: {follower_count}")
    
    def get_follower_history(self, session: Session, days: int = 30) -> List[Dict[str, Any]]:
        """Get follower count history"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        snapshots = session.query(FollowersSnapshot).filter(
            FollowersSnapshot.ts >= cutoff
        ).order_by(FollowersSnapshot.ts.asc()).all()
        
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
    
    def _calculate_j_score(self, tweet: Tweet) -> float:
        """Calculate the objective function J score for a tweet"""
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
        
        return j_score
    
    def _get_follower_delta(self, session: Session, days: int) -> float:
        """Get follower count change over specified days"""
        now = datetime.utcnow()
        start_time = now - timedelta(days=days)
        
        # Get snapshots at start and end of period
        start_snapshot = session.query(FollowersSnapshot).filter(
            FollowersSnapshot.ts <= start_time
        ).order_by(FollowersSnapshot.ts.desc()).first()
        
        end_snapshot = session.query(FollowersSnapshot).filter(
            FollowersSnapshot.ts <= now
        ).order_by(FollowersSnapshot.ts.desc()).first()
        
        if not start_snapshot or not end_snapshot:
            return 0.0
        
        return float(end_snapshot.follower_count - start_snapshot.follower_count)
    
    def _simple_z_score(self, value: float, mean: float, std: float) -> float:
        """Simple z-score calculation"""
        if std == 0:
            return 0.0
        return (value - mean) / std
    
    def _calculate_engagement_rate(self, session: Session) -> float:
        """Calculate overall engagement rate"""
        recent_tweets = session.query(Tweet).filter(
            Tweet.created_at >= datetime.utcnow() - timedelta(days=7)
        ).all()
        
        if not recent_tweets:
            return 0.0
        
        total_engagement = 0
        for tweet in recent_tweets:
            engagement = (tweet.likes or 0) + (tweet.rts or 0) + (tweet.replies or 0) + (tweet.quotes or 0)
            total_engagement += engagement
        
        # Get approximate follower count
        latest_snapshot = session.query(FollowersSnapshot).order_by(
            FollowersSnapshot.ts.desc()
        ).first()
        
        follower_count = latest_snapshot.follower_count if latest_snapshot else 1000
        
        avg_engagement = total_engagement / len(recent_tweets)
        engagement_rate = (avg_engagement / follower_count) * 100
        
        return round(min(engagement_rate, 100), 2)
