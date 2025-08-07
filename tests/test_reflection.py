import pytest
from unittest.mock import MagicMock, patch

from services.reflection import ReflectionService

class TestReflectionService:
    def test_generate_reflection_with_activity(self):
        mock_session = MagicMock()
        with patch('services.reflection.MemoryService') as MockMemory, \
             patch('services.reflection.AnalyticsService') as MockAnalytics:
            memory_instance = MockMemory.return_value
            analytics_instance = MockAnalytics.return_value

            memory_instance.get_episodic_memory.return_value = [{"type": "action"}]
            analytics_instance.calculate_fame_score.return_value = {
                "engagement_proxy": 5.0,
                "follower_delta": 2.0,
            }

            service = ReflectionService()
            note = service.generate_reflection(mock_session)

            memory_instance.add_improvement_note.assert_called_once_with(mock_session, note)
            assert "Reviewed 1 actions" in note

    def test_generate_reflection_no_activity(self):
        mock_session = MagicMock()
        with patch('services.reflection.MemoryService') as MockMemory, \
             patch('services.reflection.AnalyticsService') as MockAnalytics:
            memory_instance = MockMemory.return_value
            analytics_instance = MockAnalytics.return_value

            memory_instance.get_episodic_memory.return_value = []
            analytics_instance.calculate_fame_score.return_value = {
                "engagement_proxy": 0.0,
                "follower_delta": 0.0,
            }

            service = ReflectionService()
            note = service.generate_reflection(mock_session)

            memory_instance.add_improvement_note.assert_called_once_with(mock_session, note)
            assert "No recent activity" in note
