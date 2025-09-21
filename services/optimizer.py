"""
Thompson sampling optimizer for multi-armed bandit optimization
"""

import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta, UTC
import random
import services.experiments as experiments_module
from services.experiments import ExperimentsService
from services.logging_utils import get_logger
from config import get_config
from db.session import get_db_session

logger = get_logger(__name__)

class Optimizer:
    """Thompson sampling optimizer with epsilon-floor exploration"""
    
    def __init__(self):
        self.config = get_config()
        self._experiments = ExperimentsService()
        
        # Thompson sampling parameters
        self.epsilon_floor = 0.1  # Minimum exploration probability
        self.beta_prior = (2.0, 2.0)  # Beta(alpha, beta) prior
        
        # Goal mode weights
        self.goal_weights = self.config.GOAL_WEIGHTS[self.config.GOAL_MODE]

        # Normalization parameters for J-score
        self.j_score_window_size = 100
        self.j_score_history = []

    @property
    def experiments(self) -> ExperimentsService:
        """Return the most recently constructed experiments service."""
        return experiments_module.LAST_EXPERIMENTS_INSTANCE or self._experiments
    
    def update_goal_weights(self, goal_mode: str):
        """Update goal weights based on mode change"""
        if goal_mode in self.config.GOAL_WEIGHTS:
            self.goal_weights = self.config.GOAL_WEIGHTS[goal_mode]
            logger.info(f"Updated goal weights for {goal_mode}: {self.goal_weights}")
    
    def get_action_weights(self) -> Dict[str, float]:
        """Get action weights based on current optimization state"""
        # This would analyze recent performance and suggest action probabilities
        # For now, return balanced weights
        return {
            "POST_PROPOSAL": 1.0,
            "REPLY_MENTIONS": 0.8,
            "SEARCH_ENGAGE": 0.6,
            "REST": 0.3
        }
    
    def sample_arm_combination(self, session: Any) -> Dict[str, Any]:
        """Sample an arm combination using Thompson sampling"""
        try:
            # Get arm performance data
            performance = self.experiments.get_arm_performance(session, days=30)
            
            # Decide exploration vs exploitation
            should_explore = self.experiments.should_explore(session, self.epsilon_floor)
            
            if should_explore or not performance:
                # Random exploration
                arms = self.experiments.arms
                selected = {
                    "post_type": random.choice(arms["post_type"]),
                    "topic": random.choice(arms["topic"]),
                    "hour_bin": random.choice(arms["hour_bin"]),
                    "cta_variant": random.choice(arms["cta_variant"]),
                    "selection_method": "exploration",
                    "sampled_prob": random.random()
                }
                logger.info("Selected arms via exploration")
            else:
                # Thompson sampling exploitation
                selected = self._thompson_sample(performance)
                selected["selection_method"] = "exploitation"
                logger.info("Selected arms via Thompson sampling")
            
            return selected
            
        except Exception as e:
            logger.error(f"Arm sampling failed: {e}")
            # Fallback to random selection
            arms = self.experiments.arms
            return {
                "post_type": random.choice(arms["post_type"]),
                "topic": random.choice(arms["topic"]),
                "hour_bin": random.choice(arms["hour_bin"]),
                "cta_variant": random.choice(arms["cta_variant"]),
                "selection_method": "fallback",
                "sampled_prob": 0.5
            }
    
    def _thompson_sample(self, performance: Dict[str, Any]) -> Dict[str, Any]:
        """Perform Thompson sampling for each arm dimension"""
        selected = {}
        total_prob = 1.0
        
        for dimension in ["post_type", "topic", "hour_bin", "cta_variant"]:
            if dimension in performance and performance[dimension]:
                arm_probs = {}
                
                # Calculate Thompson sampling probabilities
                for arm, stats in performance[dimension].items():
                    # Convert J-scores to success/failure for Beta distribution
                    successes, failures = self._convert_to_beta_params(
                        stats["mean_reward"], 
                        stats["count"]
                    )
                    
                    # Sample from Beta distribution
                    alpha = self.beta_prior[0] + successes
                    beta = self.beta_prior[1] + failures
                    
                    # Handle edge cases
                    if alpha <= 0:
                        alpha = 1
                    if beta <= 0:
                        beta = 1
                    
                    try:
                        sampled_prob = np.random.beta(alpha, beta)
                        arm_probs[arm] = sampled_prob
                    except Exception as e:
                        logger.warning(f"Beta sampling failed for {arm}: {e}")
                        arm_probs[arm] = 0.5
                
                # Select arm with highest sampled probability
                if arm_probs:
                    best_arm = max(arm_probs.items(), key=lambda x: x[1])
                    selected[dimension] = best_arm[0]
                    total_prob *= best_arm[1]
                else:
                    # Fallback to random
                    selected[dimension] = random.choice(list(performance[dimension].keys()))
                    total_prob *= 0.5
            else:
                # No data for this dimension, choose randomly
                arms = self.experiments.arms
                selected[dimension] = random.choice(arms[dimension])
                total_prob *= 0.5
        
        selected["sampled_prob"] = total_prob
        return selected
    
    def _convert_to_beta_params(self, mean_reward: float, count: int) -> Tuple[int, int]:
        """Convert J-score performance to Beta distribution parameters"""
        # Normalize J-score to 0-1 range
        normalized_reward = self._normalize_j_score(mean_reward)
        
        # Convert to successes/failures
        # Higher J-score = more successes
        successes = int(normalized_reward * count)
        failures = count - successes
        
        return max(successes, 0), max(failures, 0)
    
    def _normalize_j_score(self, j_score: float) -> float:
        """Normalize J-score to 0-1 range using rolling statistics"""
        if not self.j_score_history:
            # Fall back to the observed score when we lack history.
            return max(0.0, min(1.0, j_score))
        
        # Use percentile-based normalization
        sorted_scores = sorted(self.j_score_history)
        percentile = self._find_percentile(j_score, sorted_scores)
        
        return percentile / 100.0
    
    def _find_percentile(self, value: float, sorted_list: List[float]) -> float:
        """Find percentile of value in sorted list"""
        if not sorted_list:
            return 50.0
        
        if value <= sorted_list[0]:
            return 0.0
        if value >= sorted_list[-1]:
            return 100.0
        
        # Linear interpolation
        for i in range(len(sorted_list) - 1):
            if sorted_list[i] <= value <= sorted_list[i + 1]:
                ratio = (value - sorted_list[i]) / (sorted_list[i + 1] - sorted_list[i])
                percentile = (i + ratio) / len(sorted_list) * 100
                return percentile
        
        return 50.0
    
    def update_j_score_history(self, session: Any):
        """Update J-score history for normalization"""
        try:
            # Get recent J-scores
            cutoff = datetime.now(UTC) - timedelta(days=7)
            
            from db.models import Tweet

            recent_tweets = (
                session.query(Tweet)
                .filter(
                    lambda tweet: tweet.created_at >= cutoff,
                    lambda tweet: tweet.j_score is not None,
                )
                .order_by(lambda tweet: tweet.created_at, descending=True)
                .limit(self.j_score_window_size)
                .all()
            )
            
            self.j_score_history = [tweet.j_score for tweet in recent_tweets]
            
            logger.info(f"Updated J-score history with {len(self.j_score_history)} samples")
            
        except Exception as e:
            logger.error(f"Failed to update J-score history: {e}")
    
    def get_optimization_status(self, session: Any) -> Dict[str, Any]:
        """Get current optimization status"""
        try:
            experiment_summary = self.experiments.get_experiment_summary(session)
            
            # Calculate optimization metrics
            total_experiments = experiment_summary.get("total_experiments", 0)
            exploration_ratio = experiment_summary.get("exploration_ratio", 0)
            
            # Get current best arms
            recommendations = self.experiments.get_arm_recommendations(session)
            
            return {
                "goal_mode": self.config.GOAL_MODE,
                "goal_weights": self.goal_weights,
                "total_experiments": total_experiments,
                "exploration_ratio": exploration_ratio,
                "epsilon_floor": self.epsilon_floor,
                "best_arms": recommendations,
                "j_score_samples": len(self.j_score_history),
                "optimization_active": total_experiments > 10
            }
            
        except Exception as e:
            logger.error(f"Failed to get optimization status: {e}")
            return {"error": str(e)}
    
    def simulate_optimization(self, iterations: int = 1000) -> Dict[str, Any]:
        """Simulate optimization performance for testing"""
        # Simulate arm rewards
        true_rewards = {
            ("proposal", "technology", 14, "learn_more"): 0.8,
            ("proposal", "coordination", 16, "join_pilot"): 0.75,
            ("thread", "economics", 10, "provide_feedback"): 0.6,
            ("question", "energy", 18, "share_experience"): 0.7
        }
        
        # Run simulation
        cumulative_reward = 0
        selections = []
        regret_history = []
        
        for i in range(iterations):
            # Random arm selection for simulation
            arms = self.experiments.arms
            selected_arm = (
                random.choice(arms["post_type"]),
                random.choice(arms["topic"]),
                random.choice(arms["hour_bin"]),
                random.choice(arms["cta_variant"])
            )
            
            # Get reward (with noise)
            true_reward = true_rewards.get(selected_arm, 0.5)
            noise = np.random.normal(0, 0.1)
            observed_reward = max(0, min(1, true_reward + noise))
            
            cumulative_reward += observed_reward
            selections.append({
                "iteration": i,
                "arm": selected_arm,
                "reward": observed_reward
            })
            
            # Calculate regret
            optimal_reward = max(true_rewards.values())
            regret = optimal_reward - observed_reward
            regret_history.append(regret)
        
        return {
            "iterations": iterations,
            "cumulative_reward": cumulative_reward,
            "average_reward": cumulative_reward / iterations,
            "total_regret": sum(regret_history),
            "final_regret": regret_history[-1] if regret_history else 0,
            "convergence": len([r for r in regret_history[-100:] if r < 0.1]) if len(regret_history) >= 100 else 0
        }

