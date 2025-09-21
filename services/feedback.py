"""
Feedback and improvement note generation
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session

from db.models import Tweet, Action, KPI
from services.memory import MemoryService
from services.logging_utils import get_logger

logger = get_logger(__name__)

class FeedbackService:
    """Generates improvement feedback based on performance analysis"""
    
    def __init__(self):
        self.memory = MemoryService()
    
    def generate_daily_improvement_note(self, session: Session) -> str:
        """Generate a daily improvement note based on recent performance"""
        try:
            # Analyze last 24 hours
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            
            # Get recent tweets and their performance
            recent_tweets = session.query(Tweet).filter(
                Tweet.created_at >= cutoff
            ).order_by(Tweet.j_score.desc()).all()
            
            if not recent_tweets:
                return "No recent tweets to analyze. Consider increasing posting frequency."
            
            # Analyze patterns
            analysis = self._analyze_performance_patterns(recent_tweets)
            
            # Generate specific improvement note
            note = self._generate_improvement_from_analysis(analysis)
            
            # Add to memory
            self.memory.add_improvement_note(session, note)
            
            return note
            
        except Exception as e:
            logger.error(f"Failed to generate improvement note: {e}")
            return "Daily analysis failed. Review system logs for issues."
    
    def _analyze_performance_patterns(self, tweets: List[Tweet]) -> Dict[str, Any]:
        """Analyze performance patterns in recent tweets"""
        if not tweets:
            return {}
        
        # Sort by performance
        tweets_by_score = sorted(tweets, key=lambda t: t.j_score or 0, reverse=True)
        
        # Top and bottom performers
        top_performers = tweets_by_score[:3]
        bottom_performers = tweets_by_score[-3:]
        
        # Topic analysis
        topic_performance = {}
        for tweet in tweets:
            topic = tweet.topic or "unknown"
            if topic not in topic_performance:
                topic_performance[topic] = []
            topic_performance[topic].append(tweet.j_score or 0)
        
        # Calculate average scores per topic
        topic_averages = {
            topic: sum(scores) / len(scores) 
            for topic, scores in topic_performance.items()
        }
        
        # Time analysis
        hour_performance = {}
        for tweet in tweets:
            hour = tweet.hour_bin or 0
            if hour not in hour_performance:
                hour_performance[hour] = []
            hour_performance[hour].append(tweet.j_score or 0)
        
        hour_averages = {
            hour: sum(scores) / len(scores)
            for hour, scores in hour_performance.items()
        }
        
        # CTA analysis
        cta_performance = {}
        for tweet in tweets:
            cta = tweet.cta_variant or "none"
            if cta not in cta_performance:
                cta_performance[cta] = []
            cta_performance[cta].append(tweet.j_score or 0)
        
        cta_averages = {
            cta: sum(scores) / len(scores)
            for cta, scores in cta_performance.items()
        }
        
        return {
            "total_tweets": len(tweets),
            "average_score": sum(t.j_score or 0 for t in tweets) / len(tweets),
            "top_performers": [
                {"text": t.text[:100], "score": t.j_score, "topic": t.topic}
                for t in top_performers
            ],
            "bottom_performers": [
                {"text": t.text[:100], "score": t.j_score, "topic": t.topic}
                for t in bottom_performers
            ],
            "best_topics": sorted(topic_averages.items(), key=lambda x: x[1], reverse=True),
            "best_hours": sorted(hour_averages.items(), key=lambda x: x[1], reverse=True),
            "best_ctas": sorted(cta_averages.items(), key=lambda x: x[1], reverse=True)
        }
    
    def _generate_improvement_from_analysis(self, analysis: Dict[str, Any]) -> str:
        """Generate specific improvement note from analysis"""
        if not analysis:
            return "Insufficient data for analysis. Increase activity level."
        
        improvements = []
        
        # Topic recommendations
        best_topics = analysis.get("best_topics", [])
        if best_topics:
            top_topic = best_topics[0][0]
            improvements.append(f"Focus more on '{top_topic}' topic (highest J-score)")
        
        # Timing recommendations
        best_hours = analysis.get("best_hours", [])
        if best_hours:
            top_hour = best_hours[0][0]
            improvements.append(f"Post more frequently around hour {top_hour}")
        
        # CTA recommendations
        best_ctas = analysis.get("best_ctas", [])
        if best_ctas and best_ctas[0][0] != "none":
            top_cta = best_ctas[0][0]
            improvements.append(f"Use '{top_cta}' CTA variant more often")
        
        # Performance-based recommendations
        avg_score = analysis.get("average_score", 0)
        if avg_score < 0.5:
            improvements.append("Overall performance below target - review content quality")
        elif avg_score > 0.8:
            improvements.append("Strong performance - maintain current strategy")
        
        # Content quality analysis
        top_performers = analysis.get("top_performers", [])
        if top_performers:
            # Look for patterns in top performers
            top_topics = [p.get("topic") for p in top_performers if p.get("topic")]
            if len(set(top_topics)) == 1:
                improvements.append(f"Double down on {top_topics[0]} content")
        
        if not improvements:
            improvements.append("Maintain current strategy and monitor for emerging patterns")
        
        # Combine into a single improvement note
        return "; ".join(improvements[:3])  # Limit to top 3 improvements
    
    def analyze_weekly_trends(self, session: Session) -> Dict[str, Any]:
        """Analyze weekly performance trends"""
        cutoff = datetime.now(UTC) - timedelta(days=7)
        
        tweets = session.query(Tweet).filter(
            Tweet.created_at >= cutoff
        ).all()
        
        # Daily performance tracking
        daily_scores = {}
        for tweet in tweets:
            day = tweet.created_at.strftime("%Y-%m-%d")
            if day not in daily_scores:
                daily_scores[day] = []
            daily_scores[day].append(tweet.j_score or 0)
        
        daily_averages = {
            day: sum(scores) / len(scores)
            for day, scores in daily_scores.items()
        }
        
        # Trend analysis
        trend_direction = "stable"
        if len(daily_averages) >= 3:
            recent_avg = sum(list(daily_averages.values())[-3:]) / 3
            earlier_avg = sum(list(daily_averages.values())[:-3]) / max(1, len(daily_averages) - 3)
            
            if recent_avg > earlier_avg * 1.1:
                trend_direction = "improving"
            elif recent_avg < earlier_avg * 0.9:
                trend_direction = "declining"
        
        return {
            "daily_averages": daily_averages,
            "trend_direction": trend_direction,
            "total_tweets": len(tweets),
            "week_average": sum(t.j_score or 0 for t in tweets) / max(1, len(tweets))
        }
