"""
Multi-armed bandit experiments tracking
"""

from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta, UTC
import json

from db.models import ArmsLog, Tweet
from services.logging_utils import get_logger
from db.session import get_db_session
from config import get_config

LAST_EXPERIMENTS_INSTANCE: Optional["ExperimentsService"] = None

logger = get_logger(__name__)

class ExperimentsService:
    """Manages multi-armed bandit experiments"""
    
    def __init__(self):
        self.config = get_config()

        # Define experiment arms
        intensity_levels = (
            list(range(self.config.MIN_INTENSITY_LEVEL, self.config.MAX_INTENSITY_LEVEL + 1))
            if self.config.MIN_INTENSITY_LEVEL <= self.config.MAX_INTENSITY_LEVEL
            else [self.config.MIN_INTENSITY_LEVEL]
        )

        self.arms = {
            "post_type": ["proposal", "thread", "reply", "question", "insight"],
            "topic": ["technology", "economics", "coordination", "energy", "policy", "automation"],
            "hour_bin": list(range(24)),  # 0-23 hour bins
            "cta_variant": ["learn_more", "join_pilot", "provide_feedback", "share_experience", "book_call"],
            "intensity": intensity_levels,
        }

        # Arm combinations cache
        self._arm_combinations = None

        global LAST_EXPERIMENTS_INSTANCE
        LAST_EXPERIMENTS_INSTANCE = self
    
    def get_arm_combinations(self) -> List[Tuple[str, str, int, str]]:
        """Get all possible arm combinations"""
        if self._arm_combinations is None:
            combinations = []
            for post_type in self.arms["post_type"]:
                for topic in self.arms["topic"]:
                    for hour_bin in self.arms["hour_bin"]:
                        for cta_variant in self.arms["cta_variant"]:
                            for intensity in self.arms["intensity"]:
                                combinations.append((post_type, topic, hour_bin, cta_variant, intensity))
            self._arm_combinations = combinations
        
        return self._arm_combinations
    
    def log_arm_selection(
        self,
        session: Any,
        tweet_id: str,
        post_type: str,
        topic: str,
        hour_bin: int,
        cta_variant: str,
        intensity: Optional[int],
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
                intensity=intensity,
                sampled_prob=sampled_prob,
                reward_j=None  # Will be updated later when metrics come in
            )
            session.add(arms_log)
            session.commit()
            
            logger.info(f"Logged arm selection for tweet {tweet_id}")
            
        except Exception as e:
            logger.error(f"Failed to log arm selection: {e}")
            session.rollback()
    
    def update_arm_rewards(self, session: Any):
        """Update rewards for arms based on tweet performance"""
        try:
            # Get arms logs without rewards
            pending_logs = (
                session.query(ArmsLog)
                .filter(
                    lambda log: log.reward_j is None,
                    lambda log: log.tweet_id is not None,
                )
                .all()
            )
            
            updated_count = 0
            for log in pending_logs:
                # Get the corresponding tweet
                tweet = (
                    session.query(Tweet)
                    .filter(lambda tweet: tweet.id == log.tweet_id)
                    .first()
                )
                
                if tweet and tweet.j_score is not None:
                    log.reward_j = tweet.j_score
                    updated_count += 1
            
            if updated_count > 0:
                session.commit()
                logger.info(f"Updated rewards for {updated_count} arm logs")
            
        except Exception as e:
            logger.error(f"Failed to update arm rewards: {e}")
            session.rollback()
    
    def get_arm_performance(self, session: Any, days: int = 30) -> Dict[str, Any]:
        """Get performance statistics for each arm"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        
        # Get arm logs with rewards
        logs = (
            session.query(ArmsLog)
            .filter(
                lambda log: log.created_at >= cutoff,
                lambda log: log.reward_j is not None,
            )
            .all()
        )
        
        if not logs:
            return {}
        
        # Group by arm dimensions
        performance = {
            "post_type": {},
            "topic": {},
            "hour_bin": {},
            "cta_variant": {},
            "intensity": {},
        }

        for log in logs:
            reward = log.reward_j

            # Post type performance
            if log.post_type:
                performance["post_type"].setdefault(log.post_type, []).append(reward)

            # Topic performance
            if log.topic:
                performance["topic"].setdefault(log.topic, []).append(reward)

            # Hour bin performance
            if log.hour_bin is not None:
                hour_key = int(log.hour_bin)
                performance["hour_bin"].setdefault(hour_key, []).append(reward)

            # CTA variant performance
            if log.cta_variant:
                performance["cta_variant"].setdefault(log.cta_variant, []).append(reward)

            # Intensity performance
            if log.intensity is not None:
                intensity_key = int(log.intensity)
                performance["intensity"].setdefault(intensity_key, []).append(reward)
        
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
    
    def get_experiment_summary(self, session: Any) -> Dict[str, Any]:
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
        recent_logs = (
            session.query(ArmsLog)
            .filter(lambda log: log.created_at >= datetime.now(UTC) - timedelta(days=7))
            .all()
        )
        
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
    
    def get_arm_recommendations(self, session: Any) -> Dict[str, str]:
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
    
    def should_explore(self, session: Any, epsilon: float = 0.1) -> bool:
        """Determine if we should explore (vs exploit) based on recent history"""
        # Get recent exploration ratio
        recent_logs = (
            session.query(ArmsLog)
            .filter(lambda log: log.created_at >= datetime.now(UTC) - timedelta(hours=6))
            .order_by(lambda log: log.created_at, descending=True)
            .limit(10)
            .all()
        )
        
        if not recent_logs:
            return True  # Explore when no recent data
        
        exploration_count = sum(1 for log in recent_logs if log.sampled_prob < 0.5)
        current_exploration_ratio = exploration_count / len(recent_logs)
        
        # Encourage exploration if we're below target
        return current_exploration_ratio < epsilon

