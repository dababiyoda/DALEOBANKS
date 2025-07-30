"""
Action selection based on persona, drives, optimizer, and constraints
"""

import random
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import yaml

from services.persona_store import PersonaStore
from services.optimizer import Optimizer
from services.logging_utils import get_logger
from config import get_config

logger = get_logger(__name__)

class Selector:
    """Intelligent action selection service"""
    
    def __init__(self, persona_store: PersonaStore):
        self.persona_store = persona_store
        self.optimizer = Optimizer()
        self.config = get_config()
        self.drives = self._load_drives()
        
        # Action types with their base probabilities
        self.action_types = {
            "POST_PROPOSAL": 0.4,
            "REPLY_MENTIONS": 0.3,
            "SEARCH_ENGAGE": 0.2,
            "REST": 0.1
        }
        
        # Minimum intervals between actions (minutes)
        self.min_intervals = {
            "POST_PROPOSAL": 45,
            "REPLY_MENTIONS": 12,
            "SEARCH_ENGAGE": 25,
            "REST": 5
        }
        
        # Last action timestamps
        self.last_actions: Dict[str, datetime] = {}
    
    def _load_drives(self) -> Dict[str, float]:
        """Load drives from YAML file"""
        try:
            with open("drives.yaml", "r") as f:
                drives_config = yaml.safe_load(f)
                return drives_config
        except Exception as e:
            logger.error(f"Failed to load drives: {e}")
            return {
                "curiosity": 0.35,
                "novelty": 0.25,
                "impact": 0.30,
                "stability": 0.10
            }
    
    async def get_next_action(self) -> Dict[str, Any]:
        """
        Select the next action based on multiple factors:
        - Persona content mix
        - Drive weights
        - Optimizer recommendations
        - Minimum intervals
        - Quiet hours
        """
        try:
            # Check quiet hours
            if self._is_quiet_hours():
                return {
                    "type": "REST",
                    "reason": "quiet_hours",
                    "next_check_minutes": 60
                }
            
            # Get available actions (respecting min intervals)
            available_actions = self._get_available_actions()
            
            if not available_actions:
                return {
                    "type": "REST",
                    "reason": "all_actions_on_cooldown",
                    "next_check_minutes": 5
                }
            
            # Get persona preferences
            persona = self.persona_store.get_current_persona()
            content_mix = persona.get("content_mix", {})
            
            # Get optimizer recommendations
            optimizer_weights = self.optimizer.get_action_weights()
            
            # Combine all factors to compute final probabilities
            action_probs = self._compute_action_probabilities(
                available_actions, content_mix, optimizer_weights
            )
            
            # Select action
            selected_action = self._weighted_random_selection(action_probs)
            
            # Get specific parameters for the action
            action_params = await self._get_action_parameters(selected_action)
            
            # Record the action selection
            self.last_actions[selected_action] = datetime.utcnow()
            
            return {
                "type": selected_action,
                "reason": "intelligent_selection",
                **action_params
            }
            
        except Exception as e:
            logger.error(f"Action selection failed: {e}")
            return {
                "type": "REST",
                "reason": "error",
                "error": str(e),
                "next_check_minutes": 10
            }
    
    def _is_quiet_hours(self) -> bool:
        """Check if current time is in quiet hours"""
        if not self.config.QUIET_HOURS_ET:
            return False
        
        # Convert current time to ET (simplified)
        current_hour = datetime.now().hour
        
        # Quiet hours are typically overnight
        start_hour, end_hour = self.config.QUIET_HOURS_ET
        
        if start_hour <= end_hour:
            return start_hour <= current_hour <= end_hour
        else:
            # Spans midnight
            return current_hour >= start_hour or current_hour <= end_hour
    
    def _get_available_actions(self) -> list[str]:
        """Get actions that are not on cooldown"""
        available = []
        now = datetime.utcnow()
        
        for action_type in self.action_types.keys():
            if action_type == "REST":
                available.append(action_type)
                continue
            
            last_time = self.last_actions.get(action_type)
            if not last_time:
                available.append(action_type)
                continue
            
            min_interval = self.min_intervals.get(action_type, 60)
            if now - last_time >= timedelta(minutes=min_interval):
                available.append(action_type)
        
        return available
    
    def _compute_action_probabilities(
        self, 
        available_actions: list[str], 
        content_mix: Dict[str, float],
        optimizer_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """Compute final action probabilities"""
        
        probabilities = {}
        
        for action in available_actions:
            # Base probability
            base_prob = self.action_types[action]
            
            # Persona content mix influence
            mix_factor = 1.0
            if action == "POST_PROPOSAL":
                mix_factor = content_mix.get("proposals", 0.7) * 2
            elif action == "REPLY_MENTIONS":
                mix_factor = content_mix.get("elite_replies", 0.2) * 5
            
            # Drive influence
            drive_factor = 1.0
            drives = self.drives
            if action == "POST_PROPOSAL":
                drive_factor = drives.get("impact", 0.3) + drives.get("novelty", 0.25)
            elif action == "SEARCH_ENGAGE":
                drive_factor = drives.get("curiosity", 0.35) + drives.get("novelty", 0.25)
            elif action == "REST":
                drive_factor = drives.get("stability", 0.10) * 2
            
            # Optimizer influence
            optimizer_factor = optimizer_weights.get(action, 1.0)
            
            # Combine factors
            final_prob = base_prob * mix_factor * drive_factor * optimizer_factor
            probabilities[action] = final_prob
        
        # Normalize probabilities
        total = sum(probabilities.values())
        if total > 0:
            probabilities = {k: v/total for k, v in probabilities.items()}
        
        return probabilities
    
    def _weighted_random_selection(self, probabilities: Dict[str, float]) -> str:
        """Select action using weighted random selection"""
        actions = list(probabilities.keys())
        weights = list(probabilities.values())
        
        return random.choices(actions, weights=weights)[0]
    
    async def _get_action_parameters(self, action_type: str) -> Dict[str, Any]:
        """Get specific parameters for the selected action"""
        params = {}
        
        if action_type == "POST_PROPOSAL":
            # Select topic based on recent patterns or random
            topics = ["technology", "economics", "policy", "coordination", "energy", "automation"]
            params["topic"] = random.choice(topics)
            
            # Select CTA variant
            cta_variants = ["learn_more", "join_pilot", "provide_feedback", "share_experience"]
            params["cta_variant"] = random.choice(cta_variants)
            
            # Hour bin for analysis
            params["hour_bin"] = datetime.now().hour
            
        elif action_type == "REPLY_MENTIONS":
            params["max_mentions"] = 5
            params["priority"] = "high_authority_first"
            
        elif action_type == "SEARCH_ENGAGE":
            # Select search terms based on persona interests
            persona = self.persona_store.get_current_persona()
            interests = ["mechanisms", "pilots", "coordination", "energy", "policy"]
            params["search_terms"] = random.sample(interests, k=2)
            params["max_results"] = 10
            
        elif action_type == "REST":
            params["duration_minutes"] = random.randint(5, 15)
        
        return params
    
    def get_next_scheduled_actions(self) -> Dict[str, datetime]:
        """Get when each action type can next be performed"""
        next_actions = {}
        now = datetime.utcnow()
        
        for action_type in self.action_types.keys():
            if action_type == "REST":
                continue
                
            last_time = self.last_actions.get(action_type)
            if not last_time:
                next_actions[action_type] = now
            else:
                min_interval = self.min_intervals.get(action_type, 60)
                next_actions[action_type] = last_time + timedelta(minutes=min_interval)
        
        return next_actions
    
    def get_drive_status(self) -> Dict[str, Any]:
        """Get current drive status and influence"""
        return {
            "drives": self.drives,
            "last_actions": {k: v.isoformat() for k, v in self.last_actions.items()},
            "available_actions": self._get_available_actions(),
            "in_quiet_hours": self._is_quiet_hours()
        }
