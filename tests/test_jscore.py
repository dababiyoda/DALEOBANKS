from services.analytics import AnalyticsService
from db.models import Tweet


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


def test_tweet_jscore_includes_mission_alignment():
    service = AnalyticsService()
    tweet = Tweet(id="1", text="example", kind="proposal")
    tweet.likes = 10
    tweet.rts = 2
    tweet.replies = 1
    high_alignment = service._calculate_j_score(tweet, mission_alignment=1.0)
    low_alignment = service._calculate_j_score(tweet, mission_alignment=0.0)

    assert high_alignment > low_alignment
