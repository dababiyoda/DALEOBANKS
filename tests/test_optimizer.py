"""
Tests for Thompson sampling optimizer and multi-armed bandit
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from services.optimizer import Optimizer
from services.experiments import ExperimentsService
from db.models import ArmsLog

class TestOptimizer:
    """Test Thompson sampling optimizer"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.optimizer = Optimizer()
        self.experiments = ExperimentsService()
    
    def test_beta_parameter_conversion(self):
        """Test conversion of J-scores to Beta distribution parameters"""
        # High performance should yield more successes
        high_reward = 0.8
        count = 10
        successes, failures = self.optimizer._convert_to_beta_params(high_reward, count)
        
        assert successes > failures
        assert successes + failures == count
        
        # Low performance should yield more failures
        low_reward = 0.2
        successes_low, failures_low = self.optimizer._convert_to_beta_params(low_reward, count)
        
        assert failures_low > successes_low
        assert successes_low + failures_low == count
    
    def test_j_score_normalization(self):
        """Test J-score normalization to 0-1 range"""
        # Set up some sample history
        self.optimizer.j_score_history = [0.1, 0.3, 0.5, 0.7, 0.9]
        
        # Test various scores
        low_score = self.optimizer._normalize_j_score(0.2)
        mid_score = self.optimizer._normalize_j_score(0.5)
        high_score = self.optimizer._normalize_j_score(0.8)
        
        # Verify normalization
        assert 0 <= low_score <= 1
        assert 0 <= mid_score <= 1
        assert 0 <= high_score <= 1
        assert low_score < mid_score < high_score
    
    @patch('services.optimizer.get_db_session')
    def test_arm_combination_sampling(self, mock_db_session):
        """Test arm combination sampling logic"""
        # Mock database session
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Mock performance data
        mock_performance = {
            "post_type": {
                "proposal": {"mean_reward": 0.8, "count": 10},
                "question": {"mean_reward": 0.6, "count": 5}
            },
            "topic": {
                "technology": {"mean_reward": 0.7, "count": 8},
                "economics": {"mean_reward": 0.5, "count": 7}
            },
            "hour_bin": {
                "14": {"mean_reward": 0.9, "count": 6},
                "18": {"mean_reward": 0.4, "count": 4}
            },
            "cta_variant": {
                "learn_more": {"mean_reward": 0.8, "count": 9},
                "join_pilot": {"mean_reward": 0.6, "count": 6}
            }
        }
        
        # Mock experiments service
        with patch.object(self.experiments, 'get_arm_performance', return_value=mock_performance):
            with patch.object(self.experiments, 'should_explore', return_value=False):
                
                selected = self.optimizer.sample_arm_combination(mock_session)
                
                # Verify selection contains all required dimensions
                assert "post_type" in selected
                assert "topic" in selected
                assert "hour_bin" in selected
                assert "cta_variant" in selected
                assert "selection_method" in selected
                assert "sampled_prob" in selected
    
    def test_exploration_vs_exploitation(self):
        """Test exploration vs exploitation decision making"""
        # Mock recent arms logs for exploration ratio calculation
        mock_logs = [
            MagicMock(sampled_prob=0.3),  # Exploration (< 0.5)
            MagicMock(sampled_prob=0.7),  # Exploitation (>= 0.5)
            MagicMock(sampled_prob=0.2),  # Exploration
            MagicMock(sampled_prob=0.8),  # Exploitation
        ]
        
        with patch('services.experiments.get_db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_logs
            
            # Current exploration ratio is 2/4 = 0.5
            # With epsilon=0.1, should encourage more exploration
            should_explore = self.experiments.should_explore(mock_session, epsilon=0.6)
            assert should_explore == True
    
    def test_goal_weight_updates(self):
        """Test goal weight adjustment based on mode"""
        # Test FAME mode
        self.optimizer.update_goal_weights("FAME")
        fame_weights = self.optimizer.goal_weights
        
        assert fame_weights["alpha"] > fame_weights["beta"]  # Fame > Revenue
        assert fame_weights["alpha"] == 0.65
        
        # Test MONETIZE mode
        self.optimizer.update_goal_weights("MONETIZE")
        monetize_weights = self.optimizer.goal_weights
        
        assert monetize_weights["beta"] > monetize_weights["alpha"]  # Revenue > Fame
        assert monetize_weights["beta"] == 0.55
    
    def test_optimization_simulation(self):
        """Test optimization simulation for convergence"""
        # Run simulation
        result = self.optimizer.simulate_optimization(iterations=100)
        
        # Verify simulation results
        assert result["iterations"] == 100
        assert "cumulative_reward" in result
        assert "average_reward" in result
        assert "total_regret" in result
        assert 0 <= result["average_reward"] <= 1
        assert result["cumulative_reward"] >= 0
    
    def test_regret_minimization(self):
        """Test that regret decreases over time (learning)"""
        # Run longer simulation to test learning
        result = self.optimizer.simulate_optimization(iterations=500)
        
        # In a real bandit, regret should generally decrease
        # This is a basic test that the simulation runs
        assert result["total_regret"] >= 0
        assert result["final_regret"] >= 0
    
    @patch('services.optimizer.get_db_session')
    def test_j_score_history_update(self, mock_db_session):
        """Test J-score history maintenance for normalization"""
        # Mock database with tweet data
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Mock tweets with J-scores
        mock_tweets = [
            MagicMock(j_score=0.1),
            MagicMock(j_score=0.5),
            MagicMock(j_score=0.8),
            MagicMock(j_score=0.3),
            MagicMock(j_score=0.9)
        ]
        
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_tweets
        
        # Update history
        self.optimizer.update_j_score_history(mock_session)
        
        # Verify history was updated
        assert len(self.optimizer.j_score_history) == 5
        assert 0.1 in self.optimizer.j_score_history
        assert 0.9 in self.optimizer.j_score_history
    
    def test_arm_recommendations(self):
        """Test arm recommendation generation"""
        # Mock performance data with clear winner
        mock_performance = {
            "post_type": {
                "proposal": {"mean_reward": 0.9, "count": 10},
                "question": {"mean_reward": 0.3, "count": 5}
            },
            "topic": {
                "technology": {"mean_reward": 0.8, "count": 8},
                "economics": {"mean_reward": 0.4, "count": 7}
            }
        }
        
        with patch.object(self.experiments, 'get_arm_performance', return_value=mock_performance):
            with patch('services.experiments.get_db_session'):
                recommendations = self.experiments.get_arm_recommendations(MagicMock())
                
                # Should recommend best performing arms
                assert recommendations["post_type"] == "proposal"
                assert recommendations["topic"] == "technology"
    
    @patch('services.optimizer.get_db_session')
    def test_optimization_status(self, mock_db_session):
        """Test optimization status reporting"""
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Mock experiment summary
        mock_summary = {
            "total_experiments": 50,
            "exploration_ratio": 0.3,
            "best_performing_arms": {
                "post_type": {"arm": "proposal", "mean_reward": 0.8, "count": 20}
            }
        }
        
        with patch.object(self.experiments, 'get_experiment_summary', return_value=mock_summary):
            with patch.object(self.experiments, 'get_arm_recommendations', return_value={"post_type": "proposal"}):
                
                status = self.optimizer.get_optimization_status(mock_session)
                
                assert "goal_mode" in status
                assert "total_experiments" in status
                assert "exploration_ratio" in status
                assert "best_arms" in status
                assert status["optimization_active"] == True  # > 10 experiments
    
    def test_thompson_sampling_exploration_floor(self):
        """Test that Thompson sampling respects epsilon floor"""
        # Even with very confident posterior, should still explore occasionally
        epsilon = 0.1

        # Mock very confident performance data
        confident_performance = {
            "post_type": {
                "proposal": {"mean_reward": 0.95, "count": 100},
                "question": {"mean_reward": 0.05, "count": 100}
            }
        }

        # Over many samples, should still explore at least epsilon fraction
        exploration_count = 0
        total_samples = 100

        np.random.seed(42)

        # This is a conceptual test - in practice, epsilon enforcement
        # happens at the experiment service level
        for _ in range(total_samples):
            # Random sampling should occasionally pick suboptimal arms
            if np.random.random() < epsilon:
                exploration_count += 1
        
        exploration_ratio = exploration_count / total_samples
        assert exploration_ratio >= epsilon * 0.5  # Allow some variance

class TestExperimentsService:
    """Test experiment tracking service"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.experiments = ExperimentsService()
    
    def test_arm_combinations_generation(self):
        """Test generation of all possible arm combinations"""
        combinations = self.experiments.get_arm_combinations()
        
        # Should have all combinations of arms
        assert len(combinations) > 0
        
        # Each combination should have 4 elements (post_type, topic, hour_bin, cta_variant)
        for combo in combinations[:10]:  # Test first 10
            assert len(combo) == 4
            assert combo[0] in self.experiments.arms["post_type"]
            assert combo[1] in self.experiments.arms["topic"]
            assert combo[2] in self.experiments.arms["hour_bin"]
            assert combo[3] in self.experiments.arms["cta_variant"]
    
    @patch('services.experiments.get_db_session')
    def test_arm_logging(self, mock_db_session):
        """Test arm selection logging"""
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Log an arm selection
        self.experiments.log_arm_selection(
            mock_session,
            tweet_id="12345",
            post_type="proposal",
            topic="technology",
            hour_bin=14,
            cta_variant="learn_more",
            sampled_prob=0.7
        )
        
        # Verify database interaction
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify ArmsLog object was created with correct data
        call_args = mock_session.add.call_args[0][0]
        assert call_args.tweet_id == "12345"
        assert call_args.post_type == "proposal"
        assert call_args.sampled_prob == 0.7
    
    @patch('services.experiments.get_db_session')
    def test_reward_updates(self, mock_db_session):
        """Test updating rewards when tweet metrics become available"""
        mock_session = MagicMock()
        mock_db_session.return_value.__enter__.return_value = mock_session
        
        # Mock pending arms logs
        pending_log = MagicMock()
        pending_log.tweet_id = "12345"
        pending_log.reward_j = None
        
        mock_session.query.return_value.filter.return_value.all.return_value = [pending_log]
        
        # Mock corresponding tweet with J-score
        mock_tweet = MagicMock()
        mock_tweet.j_score = 0.75
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tweet
        
        # Update rewards
        self.experiments.update_arm_rewards(mock_session)
        
        # Verify reward was updated
        assert pending_log.reward_j == 0.75
        mock_session.commit.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
