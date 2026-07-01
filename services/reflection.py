"""Reflection service: turns raw activity + metrics into concrete, compounding lessons.

This is the agent's learning organ. The nightly job calls ``generate_reflection_async``
which gathers real signals (recent actions, engagement / follower deltas, KPI and
J-score trends, and the best-performing bandit arms), then asks the LLM to synthesise
a specific, testable lesson. Those lessons are written to memory as improvement notes,
which the generator already feeds back into every piece of content it produces -- so the
loop actually closes and the agent gets measurably sharper over time.

A synchronous ``generate_reflection`` remains for backward compatibility and as the
template fallback used when the LLM budget is exhausted or an error occurs.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from services.memory import MemoryService
from services.analytics import AnalyticsService
from services.kpi import KPIService
from services.optimizer import Optimizer
from services.llm_adapter import LLMAdapter
from services.logging_utils import get_logger

logger = get_logger(__name__)

class ReflectionService:
    """Generates structured, compounding reflections from recent activity."""

    def __init__(self) -> None:
        self.memory = MemoryService()
        self.analytics = AnalyticsService()
        self.kpi = KPIService()
        self.optimizer = Optimizer()
        self.llm = LLMAdapter()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def generate_reflection_async(self, session: Any) -> str:
        """Deep, LLM-driven reflection. Falls back to templates on any failure."""
        try:
            signals = self._gather_signals(session)
        except Exception as exc:  # never let signal gathering crash the loop
            logger.error(f"Reflection signal gathering failed: {exc}")
            return self.generate_reflection(session)

        # No activity -> cheap template note, skip the LLM entirely.
        if not signals["recent_actions"]:
            note = (
                "No recent activity to reflect on. Prioritise shipping proposals and "
                "elite replies tomorrow to restart the engagement loop."
            )
            self.memory.add_improvement_note(session, note)
            return note

        try:
            note = await self._synthesize_lesson(signals)
        except Exception as exc:
            logger.error(f"LLM reflection failed, using template fallback: {exc}")
            return self.generate_reflection(session)

        if not note:
            return self.generate_reflection(session)

        self.memory.add_improvement_note(session, note)
        logger.info(f"Reflection lesson recorded: {note[:120]}")
        return note

    def generate_reflection(self, session: Any) -> str:
        """Synchronous template reflection (backward compatible + fallback)."""
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

    def get_recent_lessons(self, session: Any, limit: int = 20) -> List[str]:
        """Expose recent improvement notes (the learned 'mind') for the API/UI."""
        try:
            notes = self.memory.get_recent_improvement_notes(session)
            return notes[:limit]
        except Exception as exc:
            logger.error(f"Failed to fetch lessons: {exc}")
            return []

    # ------------------------------------------------------------------ #
    # Signal gathering
    # ------------------------------------------------------------------ #
    def _gather_signals(self, session: Any) -> Dict[str, Any]:
        recent_actions = self.memory.get_episodic_memory(session, hours=24)
        fame_today = self.analytics.calculate_fame_score(session, days=1)
        fame_week = self.analytics.calculate_fame_score(session, days=7)

        # KPI + J-score trend direction.
        j_trend = self._trend_direction(session, "objective_score")
        fame_trend = self._trend_direction(session, "fame_score")

        # Best-performing bandit arms, if enough samples exist.
        best_arms: Dict[str, Any] = {}
        try:
            best_arms = self.optimizer.experiments.get_arm_recommendations(session)
        except Exception as exc:
            logger.debug(f"Arm recommendations unavailable: {exc}")

        prior_lessons = self.get_recent_lessons(session, limit=5)

        # Roll up action kinds for a quick behavioural summary.
        action_counts: Dict[str, int] = {}
        for a in recent_actions:
            kind = a.get("type") or a.get("kind") or "unknown"
            action_counts[kind] = action_counts.get(kind, 0) + 1

        return {
            "recent_actions": recent_actions,
            "action_counts": action_counts,
            "engagement_today": fame_today.get("engagement_proxy", 0.0),
            "follower_delta_today": fame_today.get("follower_delta", 0.0),
            "fame_today": fame_today.get("fame_score", 0.0),
            "engagement_week": fame_week.get("engagement_proxy", 0.0),
            "follower_delta_week": fame_week.get("follower_delta", 0.0),
            "j_trend": j_trend,
            "fame_trend": fame_trend,
            "best_arms": best_arms,
            "prior_lessons": prior_lessons,
        }

    def _trend_direction(self, session: Any, kpi_name: str) -> str:
        """Return 'rising' / 'falling' / 'flat' / 'unknown' for a KPI series."""
        try:
            trends = self.kpi.get_kpi_trends(session, days=7)
            series = trends.get(kpi_name, [])
            values = [pt.get("value", 0.0) for pt in series if pt is not None]
            if len(values) < 2:
                return "unknown"
            delta = values[-1] - values[0]
            spread = max(abs(values[-1]), abs(values[0]), 1e-6)
            if delta > 0.05 * spread:
                return "rising"
            if delta < -0.05 * spread:
                return "falling"
            return "flat"
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------ #
    # LLM synthesis
    # ------------------------------------------------------------------ #
    async def _synthesize_lesson(self, signals: Dict[str, Any]) -> str:
        system = (
            "You are the reflective, self-improving core of an autonomous social-media "
            "agent. Given today's activity and performance signals, produce ONE concise, "
            "concrete, testable lesson that will change tomorrow's behaviour. Reference "
            "specific levers the agent controls: post type (proposal / reply / thread), "
            "topic, intensity (1-4), posting hour, and cadence. Do not repeat prior "
            "lessons verbatim -- build on them or correct them. No hedging, no filler. "
            "Return a single sentence of at most 45 words."
        )

        payload = {
            "action_counts": signals["action_counts"],
            "engagement_today": round(signals["engagement_today"], 1),
            "follower_delta_today": round(signals["follower_delta_today"], 1),
            "engagement_week": round(signals["engagement_week"], 1),
            "follower_delta_week": round(signals["follower_delta_week"], 1),
            "objective_score_trend": signals["j_trend"],
            "fame_trend": signals["fame_trend"],
            "best_performing_arms": signals["best_arms"],
            "recent_lessons": signals["prior_lessons"],
        }

        user_message = (
            "Signals (JSON):\n"
            + json.dumps(payload, indent=2, default=str)
            + "\n\nWrite the single most valuable lesson for tomorrow."
        )

        lesson = await self.llm.chat(
            system=system,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.5,
            max_tokens=120,
        )
        lesson = (lesson or "").strip().strip('"')

        # Tag with a compact metrics footprint so progress is auditable over time.
        if lesson:
            footprint = (
                f" [eng {payload['engagement_today']}, "
                f"df {payload['follower_delta_today']}, "
                f"J:{signals['j_trend']}]"
            )
            if len(lesson) + len(footprint) <= 500:
                lesson += footprint
        return lesson
