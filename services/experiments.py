"""
Multi-armed bandit experiments tracking
"""

from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
import json
from sqlalchemy.orm import Session

from db.models import ArmsLog, Tweet
from services.logging_utils import get_logger

logger = get_logger(__name__)

class ExperimentsService:
    """Manages multi-armed bandit experiments"""
    
    def __init__(self):
        # Define experiment arms
        self.arms = {
            "post_type": ["proposal", "thread", "question", "insight"],
            "topic": ["technology", "economics", "coordination", "energy", "policy", "automation"],
            "hour_bin": list(range(24)),  # 0-23 hour bins
            "cta_variant": ["learn_more", "join_pilot", "provide_feedback", "share_experience", "book_call"]
        }
        
        # Arm combinations cache
        self._arm_combinations = None
    
    def get_arm_combinations(self) -> List[Tuple[str, str, int, str]]:
        """Get all possible arm combinations"""
        if self._arm_combinations is None:
            combinations = []
            for post_type in self.arms["post_type"]:
                for topic in self.arms["topic"]:
                    for hour_bin in self.arms["hour_bin"]:
                        for cta_variant in self.arms["cta_variant"]:
                            combinations.append((post_type, topic, hour_bin, cta_variant))
            self._arm_combinations = combinations
        
        return self._arm_combinations
    
    def log_arm_selection(
        self, 
        session: Session,
        tweet_id: str,
        post_type: str,
        topic: str,
        hour_bin: int,
        cta_variant: str,
        sampled_prob: float
    ):
        """Log an arm selection"""
        try:
            arms_log = ArmsLog(
                tweet_id=tweet_id,
                post_type=post_type,
                topic=topic,
                hour_bin=hour_bin,
                cta_variant=cta_variant,
                sampled_prob=sampled_prob,
                reward_j=None  # Will be updated later when metrics come in
            )
            session.add(arms_log)
            session.commit()
            
            logger.info(f"Logged arm selection for tweet {tweet_id}")
            
        except Exception as e:
            logger.error(f"Failed to log arm selection: {e}")
            session.rollback()
    
    def update_arm_rewards(self, session: Session):
        """Update rewards for arms based on tweet performance"""
        try:
            # Get arms logs without rewards
            pending_logs = session.query(ArmsLog).filter(
                ArmsLog.reward_j.is_(None),
                ArmsLog.tweet_id.isnot(None)
            ).all()
            
            updated_count = 0
            for log in pending_logs:
                # Get the corresponding tweet
                tweet = session.query(Tweet).filter(
                    Tweet.id == log.tweet_id
                ).first()
                
                if tweet and tweet.j_score is not None:
                    log.reward_j = tweet.j_score
                    updated_count += 1
            
            if updated_count > 0:
                session.commit()
                logger.info(f"Updated rewards for {updated_count} arm logs")
            
        except Exception as e:
            logger.error(f"Failed to update arm rewards: {e}")
            session.rollback()
    
    def get_arm_performance(self, session: Session, days: int = 30) -> Dict[str, Any]:
        """Get performance statistics for each arm"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Get arm logs with rewards
        logs = session.query(ArmsLog).filter(
            ArmsLog.created_at >= cutoff,
            ArmsLog.reward_j.isnot(None)
        ).all()
        
        if not logs:
            return {}
        
        # Group by arm dimensions
        performance = {
            "post_type": {},
            "topic": {},
            "hour_bin": {},
            "cta_variant": {}
        }
        
        for log in logs:
            reward = log.reward_j
            
            # Post type performance
            if log.post_type not in performance["post_type"]:
                performance["post_type"][log.post_type] = []
            performance["post_type"][log.post_type].append(reward)
            
            # Topic performance
            if log.topic not in performance["topic"]:
                performance["topic"][log.topic] = []
            performance["topic"][log.topic].append(reward)
            
            # Hour bin performance
            hour_key = str(log.hour_bin)
            if hour_key not in performance["hour_bin"]:
                performance["hour_bin"][hour_key] = []
            performance["hour_bin"][hour_key].append(reward)
            
            # CTA variant performance
            if log.cta_variant not in performance["cta_variant"]:
                performance["cta_variant"][log.cta_variant] = []
            performance["cta_variant"][log.cta_variant].append(reward)
        
        # Calculate statistics
        stats = {}
        for dimension, values in performance.items():
            stats[dimension] = {}
            for arm, rewards in values.items():
                if rewards:
                    stats[dimension][arm] = {
                        "mean_reward": sum(rewards) / len(rewards),
                        "count": len(rewards),
                        "total_reward": sum(rewards),
                        "min_reward": min(rewards),
                        "max_reward": max(rewards)
                    }
        
        return stats
    
    def get_experiment_summary(self, session: Session) -> Dict[str, Any]:
        """Get overall experiment summary"""
        # Total arms tested
        total_logs = session.query(ArmsLog).count()
        
        # Recent performance (last 7 days)
        recent_performance = self.get_arm_performance(session, days=7)
        
        # Best performing arms by dimension
        best_arms = {}
        for dimension, arms in recent_performance.items():
            if arms:
                best_arm = max(arms.items(), key=lambda x: x[1]["mean_reward"])
                best_arms[dimension] = {
                    "arm": best_arm[0],
                    "mean_reward": best_arm[1]["mean_reward"],
                    "count": best_arm[1]["count"]
                }
        
        # Exploration vs exploitation ratio
        recent_logs = session.query(ArmsLog).filter(
            ArmsLog.created_at >= datetime.utcnow() - timedelta(days=7)
        ).all()
        
        exploration_count = sum(1 for log in recent_logs if log.sampled_prob < 0.5)
        exploitation_count = len(recent_logs) - exploration_count
        
        return {
            "total_experiments": total_logs,
            "recent_experiments": len(recent_logs),
            "best_performing_arms": best_arms,
            "exploration_ratio": exploration_count / max(len(recent_logs), 1),
            "exploitation_ratio": exploitation_count / max(len(recent_logs), 1),
            "performance_by_dimension": recent_performance
        }
    
    def get_arm_recommendations(self, session: Session) -> Dict[str, str]:
        """Get recommended arms based on recent performance"""
        performance = self.get_arm_performance(session, days=14)
        
        recommendations = {}
        
        for dimension, arms in performance.items():
            if arms:
                # Find arm with highest mean reward and sufficient samples
                valid_arms = {
                    arm: stats for arm, stats in arms.items()
                    if stats["count"] >= 3  # Minimum sample size
                }
                
                if valid_arms:
                    best_arm = max(valid_arms.items(), key=lambda x: x[1]["mean_reward"])
                    recommendations[dimension] = best_arm[0]
                else:
                    # Fallback to most tested arm
                    most_tested = max(arms.items(), key=lambda x: x[1]["count"])
                    recommendations[dimension] = most_tested[0]
        
        return recommendations
    
    def should_explore(self, session: Session, epsilon: float = 0.1) -> bool:
        """Determine if we should explore (vs exploit) based on recent history"""
        # Get recent exploration ratio
        recent_logs = session.query(ArmsLog).filter(
            ArmsLog.created_at >= datetime.utcnow() - timedelta(hours=6)
        ).order_by(ArmsLog.created_at.desc()).limit(10).all()
        
        if not recent_logs:
            return True  # Explore when no recent data
        
        exploration_count = sum(1 for log in recent_logs if log.sampled_prob < 0.5)
        current_exploration_ratio = exploration_count / len(recent_logs)
        
        # Encourage exploration if we're below target
        return current_exploration_ratio < epsilon

