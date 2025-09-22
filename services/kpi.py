"""
KPI computation and tracking service
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session

from db.models import KPI, Tweet, FollowersSnapshot, Redirect
from config import get_config
from services.analytics import AnalyticsService
from services.logging_utils import get_logger

logger = get_logger(__name__)

class KPIService:
    """Manages KPI calculation and storage"""
    
    def __init__(self):
        self.config = get_config()
        self.analytics_service = AnalyticsService()
        self.kpi_definitions = {
            "fame_score": self._calculate_fame_score,
            "revenue_daily": self._calculate_daily_revenue,
            "authority_signals": self._calculate_authority_signals,
            "penalty_score": self._calculate_penalty_score,
            "engagement_rate": self._calculate_engagement_rate,
            "follower_growth": self._calculate_follower_growth,
            "tweet_frequency": self._calculate_tweet_frequency,
            "objective_score": self._calculate_objective_score
        }
    
    def calculate_and_store_kpis(self, session: Session, period_start: datetime, period_end: datetime):
        """Calculate all KPIs for a given period and store them"""
        try:
            for kpi_name, calculator in self.kpi_definitions.items():
                value = calculator(session, period_start, period_end)
                
                # Store KPI
                kpi = KPI(
                    name=kpi_name,
                    value=value,
                    period_start=period_start,
                    period_end=period_end
                )
                session.add(kpi)
            
            session.commit()
            logger.info(f"Calculated and stored KPIs for period {period_start} to {period_end}")
            
        except Exception as e:
            logger.error(f"KPI calculation failed: {e}")
            session.rollback()
    
    def get_latest_kpis(self, session: Session) -> Dict[str, Any]:
        """Get the latest KPI values"""
        latest_kpis = {}
        
        for kpi_name in self.kpi_definitions.keys():
            latest = session.query(KPI).filter(
                KPI.name == kpi_name
            ).order_by(KPI.period_end.desc()).first()
            
            if latest:
                latest_kpis[kpi_name] = {
                    "value": latest.value,
                    "period_start": latest.period_start.isoformat(),
                    "period_end": latest.period_end.isoformat()
                }
            else:
                latest_kpis[kpi_name] = {"value": 0.0}
        
        return latest_kpis
    
    def get_kpi_trends(self, session: Session, days: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """Get KPI trends over specified number of days"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        trends = {}
        
        for kpi_name in self.kpi_definitions.keys():
            kpi_history = session.query(KPI).filter(
                KPI.name == kpi_name,
                KPI.period_end >= cutoff
            ).order_by(KPI.period_end.asc()).all()
            
            trends[kpi_name] = [
                {
                    "value": kpi.value,
                    "timestamp": kpi.period_end.isoformat()
                }
                for kpi in kpi_history
            ]
        
        return trends
    
    def _calculate_fame_score(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate fame score based on engagement and follower growth"""
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= period_start,
            Tweet.created_at <= period_end
        ).all()
        
        if not tweets:
            return 0.0
        
        # Engagement proxy: likes + 2*rts + 1.5*replies + 1.5*quotes
        total_engagement = 0
        for tweet in tweets:
            engagement = (
                (tweet.likes or 0) +
                2 * (tweet.rts or 0) +
                1.5 * (tweet.replies or 0) +
                1.5 * (tweet.quotes or 0)
            )
            total_engagement += engagement
        
        # Get follower growth
        follower_growth = self._get_follower_growth(session, period_start, period_end)
        
        # Z-score normalization (simplified)
        engagement_score = min(total_engagement / 100, 100)  # Cap at 100
        growth_score = min(follower_growth, 100)  # Cap at 100
        
        # Combine: 50% engagement, 50% growth
        fame_score = 0.5 * engagement_score + 0.5 * growth_score
        
        return round(fame_score, 2)
    
    def _calculate_daily_revenue(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate revenue from tracked redirects"""
        # Calculate total revenue from redirects in the period
        # This would track clicks on monetized links
        redirects = session.query(Redirect).all()
        
        total_revenue = 0.0
        for redirect in redirects:
            # In a real implementation, this would track clicks per day
            # For now, we'll use a simple estimate
            estimated_daily_revenue = redirect.clicks * 0.10  # $0.10 per click estimate
            total_revenue += estimated_daily_revenue
        
        return round(total_revenue, 2)
    
    def _calculate_authority_signals(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate authority signals from verified/high-follower interactions"""
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= period_start,
            Tweet.created_at <= period_end
        ).all()
        
        # Use authority_score field if available
        total_authority = sum(tweet.authority_score or 0 for tweet in tweets)
        
        # Normalize to 0-100 scale
        return round(min(total_authority, 100), 2)
    
    def _calculate_penalty_score(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate penalty score from rate limits, mutes, etc."""
        period_days = max((period_end - period_start).days, 1)
        return float(self.analytics_service.calculate_penalty_score(session, days=period_days))
    
    def _calculate_engagement_rate(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate engagement rate as percentage"""
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= period_start,
            Tweet.created_at <= period_end
        ).all()
        
        if not tweets:
            return 0.0
        
        # Get current follower count (approximate)
        latest_snapshot = session.query(FollowersSnapshot).order_by(
            FollowersSnapshot.ts.desc()
        ).first()
        
        follower_count = latest_snapshot.follower_count if latest_snapshot else 1000
        
        # Calculate average engagement per tweet
        total_engagement = 0
        for tweet in tweets:
            engagement = (
                (tweet.likes or 0) +
                (tweet.rts or 0) +
                (tweet.replies or 0) +
                (tweet.quotes or 0)
            )
            total_engagement += engagement
        
        avg_engagement = total_engagement / len(tweets)
        engagement_rate = (avg_engagement / follower_count) * 100
        
        return round(min(engagement_rate, 100), 2)
    
    def _calculate_follower_growth(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate follower growth in the period"""
        return self._get_follower_growth(session, period_start, period_end)
    
    def _calculate_tweet_frequency(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate tweets per day in the period"""
        tweet_count = session.query(Tweet).filter(
            Tweet.created_at >= period_start,
            Tweet.created_at <= period_end
        ).count()
        
        period_days = (period_end - period_start).days or 1
        frequency = tweet_count / period_days
        
        return round(frequency, 2)
    
    def _calculate_objective_score(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Calculate the main objective function J"""
        # Get component scores
        fame = self._calculate_fame_score(session, period_start, period_end)
        revenue = self._calculate_daily_revenue(session, period_start, period_end)
        authority = self._calculate_authority_signals(session, period_start, period_end)
        penalty = self._calculate_penalty_score(session, period_start, period_end)
        
        goal_mode = (
            self.config.GOAL_MODE.upper()
            if isinstance(self.config.GOAL_MODE, str)
            else "IMPACT"
        )
        weights = self.config.GOAL_WEIGHTS.get(
            goal_mode,
            {"alpha": 0.65, "beta": 0.15, "gamma": 0.25, "lambda": 0.20},
        )
        alpha = weights.get("alpha", 0.65)
        beta = weights.get("beta", 0.15)
        gamma = weights.get("gamma", 0.25)
        lambda_penalty = weights.get("lambda", 0.20)

        # Normalize revenue to 0-100 scale
        revenue_normalized = min(revenue * 10, 100)  # $10 = 100 points
        penalty_adjusted = min(max(penalty, 0.0), 100.0)

        objective_score = (
            alpha * fame +
            beta * revenue_normalized +
            gamma * authority -
            lambda_penalty * penalty_adjusted
        )

        return round(max(objective_score, 0), 2)
    
    def _get_follower_growth(self, session: Session, period_start: datetime, period_end: datetime) -> float:
        """Get follower growth between two points"""
        start_snapshot = session.query(FollowersSnapshot).filter(
            FollowersSnapshot.ts <= period_start
        ).order_by(FollowersSnapshot.ts.desc()).first()
        
        end_snapshot = session.query(FollowersSnapshot).filter(
            FollowersSnapshot.ts <= period_end
        ).order_by(FollowersSnapshot.ts.desc()).first()
        
        if not start_snapshot or not end_snapshot:
            return 0.0
        
        growth = end_snapshot.follower_count - start_snapshot.follower_count
        return float(growth)
    
    def get_kpi_summary(self, session: Session) -> Dict[str, Any]:
        """Get a comprehensive KPI summary"""
        latest_kpis = self.get_latest_kpis(session)
        trends = self.get_kpi_trends(session, days=7)
        
        # Calculate growth rates
        growth_rates = {}
        for kpi_name, trend_data in trends.items():
            if len(trend_data) >= 2:
                recent = trend_data[-1]["value"]
                previous = trend_data[-2]["value"]
                if previous != 0:
                    growth_rate = ((recent - previous) / previous) * 100
                    growth_rates[kpi_name] = round(growth_rate, 1)
                else:
                    growth_rates[kpi_name] = 0.0
            else:
                growth_rates[kpi_name] = 0.0
        
        return {
            "latest_values": latest_kpis,
            "growth_rates": growth_rates,
            "trends": trends,
            "last_updated": datetime.now(UTC).isoformat()
        }
