"""Reflection service for generating improvement notes based on recent actions and metrics"""

from typing import Any

from services.memory import MemoryService
from services.analytics import AnalyticsService
from services.logging_utils import get_logger

logger = get_logger(__name__)


class ReflectionService:
    """Generates structured reflections from recent activity"""

    def __init__(self) -> None:
        self.memory = MemoryService()
        self.analytics = AnalyticsService()

    def generate_reflection(self, session: Any) -> str:
        """Analyze recent actions and outcomes, recording a lesson learned."""
        try:
            recent_actions = self.memory.get_episodic_memory(session, hours=24)
            fame_stats = self.analytics.calculate_fame_score(session, days=1)

            if not recent_actions:
                note = "No recent activity to reflect on. Increase engagement and output."
            else:
                engagement = fame_stats.get("engagement_proxy", 0.0)
                follower_delta = fame_stats.get("follower_delta", 0.0)
                note = (
                    f"Reviewed {len(recent_actions)} actions. "
                    f"Engagement {engagement:.1f}, follower change {follower_delta:.1f}."
                )
                if engagement < 10:
                    note += " Consider posting more compelling content."
                if follower_delta < 0:
                    note += " Address follower decline."

            self.memory.add_improvement_note(session, note)
            return note
        except Exception as exc:
            logger.error(f"Reflection generation failed: {exc}")
            return "Reflection failed. Review logs for details."
