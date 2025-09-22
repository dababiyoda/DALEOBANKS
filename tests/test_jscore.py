from services.analytics import AnalyticsService


def test_jscore_floor_gating():
    service = AnalyticsService()
    above = service.calculate_goal_aligned_j_score(impact=20, revenue=50, authority=30, fame=40)
    below = service.calculate_goal_aligned_j_score(impact=2, revenue=50, authority=30, fame=40)
    assert above > below


def test_jscore_penalty_reduces_score():
    service = AnalyticsService()
    no_penalty = service.calculate_goal_aligned_j_score(
        impact=30,
        revenue=60,
        authority=40,
        fame=50,
        penalty=0,
    )
    penalized = service.calculate_goal_aligned_j_score(
        impact=30,
        revenue=60,
        authority=40,
        fame=50,
        penalty=10,
    )

    assert penalized < no_penalty
