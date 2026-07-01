import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.reflection import ReflectionService


def _make_service():
    """Build a ReflectionService with all collaborators mocked out."""
    with patch("services.reflection.MemoryService") as MockMemory, \
         patch("services.reflection.AnalyticsService") as MockAnalytics, \
         patch("services.reflection.KPIService") as MockKPI, \
         patch("services.reflection.Optimizer") as MockOptimizer, \
         patch("services.reflection.LLMAdapter") as MockLLM:
        service = ReflectionService()
        return service, {
            "memory": MockMemory.return_value,
            "analytics": MockAnalytics.return_value,
            "kpi": MockKPI.return_value,
            "optimizer": MockOptimizer.return_value,
            "llm": MockLLM.return_value,
        }


class TestReflectionService:
    def test_generate_reflection_with_activity(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_episodic_memory.return_value = [{"type": "action"}]
        mocks["analytics"].calculate_fame_score.return_value = {
            "engagement_proxy": 5.0,
            "follower_delta": 2.0,
        }

        note = service.generate_reflection(mock_session)

        mocks["memory"].add_improvement_note.assert_called_once_with(mock_session, note)
        assert "Reviewed 1 actions" in note

    def test_generate_reflection_no_activity(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_episodic_memory.return_value = []
        mocks["analytics"].calculate_fame_score.return_value = {
            "engagement_proxy": 0.0,
            "follower_delta": 0.0,
        }

        note = service.generate_reflection(mock_session)

        mocks["memory"].add_improvement_note.assert_called_once_with(mock_session, note)
        assert "No recent activity" in note

    def test_get_recent_lessons(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_recent_improvement_notes.return_value = ["a", "b", "c"]

        lessons = service.get_recent_lessons(mock_session, limit=2)

        assert lessons == ["a", "b"]

    @pytest.mark.asyncio
    async def test_async_reflection_no_activity_skips_llm(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_episodic_memory.return_value = []
        mocks["analytics"].calculate_fame_score.return_value = {
            "engagement_proxy": 0.0,
            "follower_delta": 0.0,
            "fame_score": 0.0,
        }
        mocks["kpi"].get_kpi_trends.return_value = {}
        mocks["memory"].get_recent_improvement_notes.return_value = []
        mocks["optimizer"].experiments.get_arm_recommendations.return_value = {}
        service.llm.chat = AsyncMock()

        note = await service.generate_reflection_async(mock_session)

        service.llm.chat.assert_not_called()
        mocks["memory"].add_improvement_note.assert_called_once_with(mock_session, note)
        assert "No recent activity" in note

    @pytest.mark.asyncio
    async def test_async_reflection_uses_llm_lesson(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_episodic_memory.return_value = [
            {"type": "post_proposal"},
            {"type": "reply"},
        ]
        mocks["analytics"].calculate_fame_score.return_value = {
            "engagement_proxy": 42.0,
            "follower_delta": 3.0,
            "fame_score": 1.2,
        }
        mocks["kpi"].get_kpi_trends.return_value = {
            "objective_score": [{"value": 1.0}, {"value": 2.0}],
            "fame_score": [{"value": 0.5}, {"value": 0.9}],
        }
        mocks["memory"].get_recent_improvement_notes.return_value = ["prior lesson"]
        mocks["optimizer"].experiments.get_arm_recommendations.return_value = {
            "post_type": "proposal",
        }
        service.llm.chat = AsyncMock(return_value="Post proposals at intensity 3 on tech topics.")

        note = await service.generate_reflection_async(mock_session)

        service.llm.chat.assert_awaited_once()
        assert "Post proposals at intensity 3" in note
        mocks["memory"].add_improvement_note.assert_called_once_with(mock_session, note)

    @pytest.mark.asyncio
    async def test_async_reflection_falls_back_on_llm_error(self):
        mock_session = MagicMock()
        service, mocks = _make_service()
        mocks["memory"].get_episodic_memory.return_value = [{"type": "post_proposal"}]
        mocks["analytics"].calculate_fame_score.return_value = {
            "engagement_proxy": 4.0,
            "follower_delta": -1.0,
            "fame_score": 0.1,
        }
        mocks["kpi"].get_kpi_trends.return_value = {}
        mocks["memory"].get_recent_improvement_notes.return_value = []
        mocks["optimizer"].experiments.get_arm_recommendations.return_value = {}
        service.llm.chat = AsyncMock(side_effect=RuntimeError("budget exceeded"))

        note = await service.generate_reflection_async(mock_session)

        assert "Reviewed 1 actions" in note
        mocks["memory"].add_improvement_note.assert_called_with(mock_session, note)
