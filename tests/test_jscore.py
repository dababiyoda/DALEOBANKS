from services.analytics import AnalyticsService


def test_jscore_floor_gating():
    service = AnalyticsService()
    above = service.calculate_goal_aligned_j_score(impact=20, revenue=50, authority=30, fame=40)
    below = service.calculate_goal_aligned_j_score(impact=2, revenue=50, authority=30, fame=40)
    assert above > below
