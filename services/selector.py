"""Action selection based on persona, drives, optimizer, and constraints."""

import random
from typing import Dict, Any, Optional, List, Mapping
from datetime import datetime, timedelta, UTC

from services.persona_store import PersonaStore
from services.optimizer import Optimizer
from services.logging_utils import get_logger
from services.bandit import ThompsonBandit
from services.analytics import AnalyticsService
from services.crisis import CrisisService
from services.perception import PerceptionService
from config import get_config
from db.session import get_db_session
from db.models import Tweet

try:  # pragma: no cover
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

logger = get_logger(__name__)

class Selector:
    """Intelligent action selection service"""

    SUCCESS_J_THRESHOLD = 0.6
    REGRESSION_J_THRESHOLD = 0.25

    def __init__(
        self,
        persona_store: PersonaStore,
        *,
        analytics_service: Optional[AnalyticsService] = None,
        crisis_service: Optional[CrisisService] = None,
        perception_service: Optional[PerceptionService] = None,
    ):
        self.persona_store = persona_store
        self.optimizer = Optimizer()
        self.config = get_config()
        self.drives = self._load_drives()
        self.bandit = ThompsonBandit(
            [
                "POST_PROPOSAL",
                "REPLY_MENTIONS",
                "SEARCH_ENGAGE",
                "POST_THREAD",
                "SEND_VALUE_DM",
                "REST",
            ]
        )
        self._last_arm: Optional[str] = None
        self.analytics = analytics_service or AnalyticsService()
        self.crisis = crisis_service or CrisisService()
        self.perception = perception_service or PerceptionService()
        self._last_intensity_by_action: Dict[str, int] = {}
        self._last_successful_intensity: Dict[str, int] = {}
        self._latest_signal_snapshot: Dict[str, Any] = {}
        self._recent_dm_targets: Dict[str, datetime] = {}
        self.dm_cooldown_minutes = 24 * 60

        # Action types with their base probabilities
        self.action_types = {
            "POST_PROPOSAL": 0.35,
            "REPLY_MENTIONS": 0.25,
            "SEARCH_ENGAGE": 0.18,
            "POST_THREAD": 0.15,
            "SEND_VALUE_DM": 0.07,
            "REST": 0.0,
        }

        # Minimum intervals between actions (minutes)
        self.min_intervals = {
            "POST_PROPOSAL": 45,
            "REPLY_MENTIONS": 12,
            "SEARCH_ENGAGE": 25,
            "POST_THREAD": 180,
            "SEND_VALUE_DM": 240,
            "REST": 5,
        }
        
        # Last action timestamps
        self.last_actions: Dict[str, datetime] = {}
    
    def _load_drives(self) -> Dict[str, float]:
        """Load drives from YAML file"""
        if yaml is None:
            logger.warning("PyYAML not available; using default drive weights")
            return {
                "curiosity": 0.35,
                "novelty": 0.25,
                "impact": 0.30,
                "stability": 0.10
            }
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
    
    async def decide_next_action(self) -> Dict[str, Any]:
        """Use the Thompson bandit to decide what to do next."""
        try:
            if self._is_quiet_hours():
                self._last_arm = "REST"
                return {
                    "type": "REST",
                    "reason": "quiet_hours",
                    "next_check_minutes": 60
                }

            available_actions = self._get_available_actions()
            if not available_actions:
                self._last_arm = "REST"
                return {
                    "type": "REST",
                    "reason": "all_actions_on_cooldown",
                    "next_check_minutes": 5
                }

            persona = self.persona_store.get_current_persona()
            content_mix = persona.get("content_mix", {})
            optimizer_weights = self.optimizer.get_action_weights()

            action_probs = self._compute_action_probabilities(
                available_actions, content_mix, optimizer_weights
            )

            # Bandit selection using weighted candidates
            candidates = list(action_probs.keys())
            selected_action = self.bandit.select(candidates)

            signal_snapshot = self._gather_signal_snapshot()
            self._latest_signal_snapshot = signal_snapshot
            action_params = await self._get_action_parameters(selected_action, signal_snapshot)

            self.last_actions[selected_action] = datetime.now(UTC)
            self._last_arm = selected_action

            return {
                "type": selected_action,
                "reason": "bandit_selection",
                **action_params
            }

        except Exception as e:
            logger.error(f"Action selection failed: {e}")
            self._last_arm = "REST"
            return {
                "type": "REST",
                "reason": "error",
                "error": str(e),
                "next_check_minutes": 10
            }

    async def get_next_action(self) -> Dict[str, Any]:
        """Backward compatible alias for `decide_next_action`."""
        return await self.decide_next_action()

    def record_outcome(self, metrics: Dict[str, Any], arm: Optional[str] = None) -> None:
        """Update bandit state with observed metrics."""
        arm_to_update = arm or self._last_arm
        if not arm_to_update:
            return

        reward = metrics.get("j_score", 0.0)
        try:
            self.bandit.record_outcome(arm_to_update, reward)
        except Exception as exc:
            logger.error(f"Failed to record bandit outcome: {exc}")

        intensity_used = metrics.get("intensity")
        if intensity_used is None:
            intensity_used = self._last_intensity_by_action.get(arm_to_update)

        if intensity_used is None:
            return

        try:
            intensity_value = int(intensity_used)
        except (TypeError, ValueError):
            return

        self._last_intensity_by_action[arm_to_update] = intensity_value

        j_score = metrics.get("j_score")
        if j_score is None:
            return

        if j_score >= self.SUCCESS_J_THRESHOLD:
            self._last_successful_intensity[arm_to_update] = intensity_value
        elif j_score <= self.REGRESSION_J_THRESHOLD:
            stored = self._last_successful_intensity.get(arm_to_update)
            if stored is not None and stored > intensity_value:
                self._last_successful_intensity[arm_to_update] = max(
                    self.config.MIN_INTENSITY_LEVEL, intensity_value
                )

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
        now = datetime.now(UTC)
        
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
            elif action == "POST_THREAD":
                mix_factor = content_mix.get("proposals", 0.7) * 1.5
            elif action == "SEND_VALUE_DM":
                mix_factor = content_mix.get("summaries", 0.1) * 2

            # Drive influence
            drive_factor = 1.0
            drives = self.drives
            if action == "POST_PROPOSAL":
                drive_factor = drives.get("impact", 0.3) + drives.get("novelty", 0.25)
            elif action == "SEARCH_ENGAGE":
                drive_factor = drives.get("curiosity", 0.35) + drives.get("novelty", 0.25)
            elif action == "REST":
                drive_factor = drives.get("stability", 0.10) * 2
            elif action == "POST_THREAD":
                drive_factor = drives.get("impact", 0.3) + drives.get("stability", 0.1)
            elif action == "SEND_VALUE_DM":
                drive_factor = drives.get("impact", 0.3) + drives.get("curiosity", 0.35)

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
    
    async def _get_action_parameters(
        self,
        action_type: str,
        signal_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get specific parameters for the selected action"""
        params = {}

        if action_type == "POST_PROPOSAL":
            with get_db_session() as session:
                sampled_arms = self.optimizer.sample_arm_combination(session)

            # Capture sampled metadata for downstream logging
            sampled_arms["post_type"] = "proposal"
            params["arm_metadata"] = sampled_arms

            # Topic, CTA, hour bin come from optimizer sample with fallbacks
            topics = ["technology", "economics", "policy", "coordination", "energy", "automation"]
            params["topic"] = sampled_arms.get("topic") or random.choice(topics)

            cta_variants = ["learn_more", "join_pilot", "provide_feedback", "share_experience"]
            params["cta_variant"] = sampled_arms.get("cta_variant") or random.choice(cta_variants)

            params["hour_bin"] = sampled_arms.get("hour_bin")
            if params["hour_bin"] is None:
                params["hour_bin"] = datetime.now().hour

            sampled_intensity = sampled_arms.get("intensity")
            if sampled_intensity is None:
                sampled_intensity = self.config.MIN_INTENSITY_LEVEL
            sampled_intensity = max(
                self.config.MIN_INTENSITY_LEVEL,
                min(self.config.MAX_INTENSITY_LEVEL, int(sampled_intensity)),
            )
            params["intensity"] = self._select_intensity(
                "POST_PROPOSAL",
                baseline=sampled_intensity,
                signal_snapshot=signal_snapshot,
            )
            sampled_arms["intensity"] = params["intensity"]

        elif action_type == "REPLY_MENTIONS":
            with get_db_session() as session:
                sampled_arms = self.optimizer.sample_arm_combination(session)

            sampled_arms["post_type"] = "reply"
            params["arm_metadata"] = sampled_arms

            topics = ["technology", "economics", "policy", "coordination", "energy", "automation"]
            params["topic"] = sampled_arms.get("topic") or random.choice(topics)

            params["hour_bin"] = sampled_arms.get("hour_bin")
            if params["hour_bin"] is None:
                params["hour_bin"] = datetime.now().hour

            params["cta_variant"] = sampled_arms.get("cta_variant") or "reply_default"

            params["max_mentions"] = 5
            params["priority"] = "high_authority_first"
            params["intensity"] = self._select_intensity(
                "REPLY_MENTIONS",
                signal_snapshot=signal_snapshot,
            )
            sampled_arms["intensity"] = params["intensity"]

        elif action_type == "SEARCH_ENGAGE":
            # Select search terms based on persona interests
            persona = self.persona_store.get_current_persona()
            interests = ["mechanisms", "pilots", "coordination", "energy", "policy"]
            params["search_terms"] = random.sample(interests, k=2)
            params["max_results"] = 10
            params["intensity"] = self._select_intensity(
                "SEARCH_ENGAGE",
                signal_snapshot=signal_snapshot,
            )

        elif action_type == "POST_THREAD":
            with get_db_session() as session:
                sampled_arms = self.optimizer.sample_arm_combination(session)

            sampled_arms["post_type"] = "thread"
            params["arm_metadata"] = sampled_arms

            topics = ["systems", "coordination", "technology", "policy", "energy"]
            params["topic"] = sampled_arms.get("topic") or random.choice(topics)

            params["hour_bin"] = sampled_arms.get("hour_bin")
            if params["hour_bin"] is None:
                params["hour_bin"] = datetime.now().hour

            params["cta_variant"] = sampled_arms.get("cta_variant") or "thread_default"

            baseline_intensity = sampled_arms.get("intensity") or self.config.MIN_INTENSITY_LEVEL + 1
            params["intensity"] = self._select_intensity(
                "POST_THREAD",
                baseline=baseline_intensity,
                signal_snapshot=signal_snapshot,
            )
            sampled_arms["intensity"] = params["intensity"]

        elif action_type == "SEND_VALUE_DM":
            candidate = self._select_dm_target()
            if candidate:
                params["recipient"] = candidate
            params["intensity"] = self._select_intensity(
                "SEND_VALUE_DM",
                baseline=self.config.MIN_INTENSITY_LEVEL,
                signal_snapshot=signal_snapshot,
            )

        elif action_type == "REST":
            params["duration_minutes"] = random.randint(5, 15)

        return params
    
    def get_next_scheduled_actions(self) -> Dict[str, datetime]:
        """Get when each action type can next be performed"""
        next_actions = {}
        now = datetime.now(UTC)
        
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

    def mark_dm_sent(self, target_id: str) -> None:
        """Record that a DM was sent to a target to enforce cooldowns."""

        if not target_id:
            return
        self._recent_dm_targets[str(target_id)] = datetime.now(UTC)

    def _select_dm_target(self) -> Optional[Dict[str, Any]]:
        """Select an account eligible for a value-first DM."""

        accounts = self._get_qualified_accounts()
        if not accounts:
            return None

        cooldown = timedelta(minutes=self.dm_cooldown_minutes)
        now = datetime.now(UTC)

        for account in accounts:
            target_id = account.get("id") or account.get("user_id") or account.get("username")
            if not target_id:
                continue
            last = self._recent_dm_targets.get(str(target_id))
            if last and now - last < cooldown:
                continue
            account["id"] = str(target_id)
            return account

        return None

    def _get_qualified_accounts(
        self,
        min_authority: float = 0.75,
        max_candidates: int = 5,
    ) -> List[Dict[str, Any]]:
        try:
            accounts = self.perception.get_priority_accounts(
                min_authority=min_authority,
                max_count=max_candidates * 2,
            )
        except Exception as exc:
            logger.warning("Failed to fetch priority accounts: %s", exc)
            return []

        qualified: List[Dict[str, Any]] = []
        for account in accounts:
            if not isinstance(account, dict):
                continue
            authority = float(account.get("authority_weight", 0.0))
            if authority < min_authority:
                continue
            handle = account.get("username")
            if not handle:
                continue
            candidate = dict(account)
            candidate.setdefault(
                "id",
                str(candidate.get("user_id") or abs(hash(handle)) % 10_000_000),
            )
            qualified.append(candidate)

        qualified.sort(
            key=lambda item: (
                float(item.get("authority_weight", 0.0)),
                int(item.get("follower_count", 0)),
            ),
            reverse=True,
        )
        return qualified[:max_candidates]

    def _gather_signal_snapshot(self) -> Dict[str, Any]:
        """Collect recent analytics and crisis metrics for intensity policy."""

        snapshot: Dict[str, Any] = {
            "avg_j_score": 0.0,
            "penalty": 0.0,
            "authority": 0.0,
            "crisis_signal": 0.0,
            "crisis_active": False,
            "samples": 0,
        }

        try:
            with get_db_session() as session:
                recent_tweets = (
                    session.query(Tweet)
                    .order_by(lambda tweet: tweet.created_at, descending=True)
                    .limit(5)
                    .all()
                )
                j_scores = [
                    float(tweet.j_score)
                    for tweet in recent_tweets
                    if tweet.j_score is not None
                ]
                if j_scores:
                    snapshot["avg_j_score"] = sum(j_scores) / len(j_scores)
                    snapshot["samples"] = len(j_scores)

                snapshot["penalty"] = float(
                    self.analytics.calculate_penalty_score(session, days=1)
                )
                snapshot["authority"] = float(
                    self.analytics.calculate_authority_signals(session, days=1)
                )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to gather analytics signals: %s", exc)

        try:
            snapshot["crisis_signal"] = float(self.crisis.last_signal)
        except Exception:  # pragma: no cover - crisis service guarantees float but guard just in case
            snapshot["crisis_signal"] = 0.0

        try:
            snapshot["crisis_active"] = bool(self.crisis.is_paused())
        except Exception:  # pragma: no cover
            snapshot["crisis_active"] = False

        snapshot["crisis_threshold"] = getattr(self.crisis, "signal_threshold", 0.0)
        snapshot["crisis_resume"] = getattr(self.crisis, "resume_threshold", 0.0)

        return snapshot

    def _select_intensity(
        self,
        action_type: str,
        *,
        baseline: Optional[int] = None,
        signal_snapshot: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Apply policy rules to select an intensity level."""

        min_level = self.config.MIN_INTENSITY_LEVEL
        max_level = self.config.MAX_INTENSITY_LEVEL

        if baseline is None:
            baseline = self._last_successful_intensity.get(
                action_type,
                self._last_intensity_by_action.get(action_type, min_level),
            )

        try:
            baseline_value = int(baseline)
        except (TypeError, ValueError):
            baseline_value = min_level

        baseline_value = max(min_level, min(max_level, baseline_value))

        if not self.config.ADAPTIVE_INTENSITY:
            self._last_intensity_by_action[action_type] = baseline_value
            return baseline_value

        snapshot = signal_snapshot or self._gather_signal_snapshot()
        self._latest_signal_snapshot = snapshot

        penalty = snapshot.get("penalty", 0.0) or 0.0
        avg_j_score = snapshot.get("avg_j_score", 0.0) or 0.0
        authority = snapshot.get("authority", 0.0) or 0.0
        crisis_signal = snapshot.get("crisis_signal", 0.0) or 0.0
        crisis_active = bool(snapshot.get("crisis_active", False))
        crisis_threshold = snapshot.get("crisis_threshold", 0.0) or 0.0

        adjustments = 0

        if penalty >= 8:
            adjustments -= 2
        elif penalty >= 4:
            adjustments -= 1

        if avg_j_score >= 0.65:
            adjustments += 1
        elif avg_j_score <= 0.35 and not crisis_active:
            adjustments -= 1

        if authority >= 60:
            adjustments += 1

        if crisis_active:
            adjustments -= 2
        elif crisis_signal >= crisis_threshold and crisis_threshold > 0:
            adjustments -= 1

        if crisis_active:
            adjustments = min(adjustments, -2)
        elif crisis_signal >= crisis_threshold and crisis_threshold > 0:
            adjustments = min(adjustments, -1)

        target = baseline_value + adjustments

        previous = self._last_intensity_by_action.get(action_type, baseline_value)
        try:
            previous_value = int(previous)
        except (TypeError, ValueError):
            previous_value = baseline_value

        max_step = 2 if crisis_active else 1

        if target > previous_value + max_step:
            target = previous_value + max_step
        elif target < previous_value - max_step:
            target = previous_value - max_step

        target = max(min_level, min(max_level, target))
        self._last_intensity_by_action[action_type] = target
        return target
