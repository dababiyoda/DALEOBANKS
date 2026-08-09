"""Per-arm quality telemetry: the signal that turns the outrage guard on.

Until these deltas exist the J-score is engagement all the way down, and an
arm that wins by making people angry is indistinguishable from one that wins
by helping. The guard was wired before this and could not fire. These tests
prove the signal arrives and that the guard binds to it.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.models import Action, ArmsLog, HelpfulnessFeedback
from db.session import get_db_session, init_db
from services.experiments import ExperimentsService
from services.optimizer import Optimizer


def _log(session, *, topic, reward, when, tweet_id):
    row = ArmsLog(tweet_id=tweet_id, post_type="proposal", topic=topic,
                  hour_bin=9, cta_variant="a", intensity=2, reward_j=reward)
    row.created_at = when
    session.add(row)
    return row


def _rating(session, *, tweet_id, rating, when):
    row = HelpfulnessFeedback(channel="x", rating=rating, reference_id=tweet_id)
    row.captured_at = when
    session.add(row)
    return row


@pytest.fixture
def svc():
    init_db()
    return ExperimentsService()


def test_engagement_delta_is_computed_per_arm(svc):
    now = datetime.now(UTC)
    early, late = now - timedelta(days=25), now - timedelta(days=2)
    with get_db_session() as session:
        _log(session, topic="fees", reward=0.2, when=early, tweet_id="t1")
        _log(session, topic="fees", reward=0.8, when=late, tweet_id="t2")
        session.commit()
        stats = svc.get_arm_performance(session, days=30)
    arm = stats["topic"]["fees"]
    assert abs(arm["engagement_delta"] - 0.6) < 0.01


def test_capability_delta_reads_helpfulness_attributed_to_the_arm(svc):
    now = datetime.now(UTC)
    early, late = now - timedelta(days=25), now - timedelta(days=2)
    with get_db_session() as session:
        _log(session, topic="fees", reward=0.2, when=early, tweet_id="t1")
        _log(session, topic="fees", reward=0.9, when=late, tweet_id="t2")
        _rating(session, tweet_id="t1", rating=5.0, when=early)
        _rating(session, tweet_id="t2", rating=2.0, when=late)
        session.commit()
        stats = svc.get_arm_performance(session, days=30)
    arm = stats["topic"]["fees"]
    # Engagement up, helpfulness down: the signature the guard exists for.
    assert arm["engagement_delta"] > 0
    assert abs(arm["capability_delta"] - (-3.0)) < 0.01


def test_no_ratings_means_no_capability_delta(svc):
    """Absence of a signal is not a neutral signal. The guard treats the
    difference as decisive, so the telemetry must not invent a zero."""
    now = datetime.now(UTC)
    with get_db_session() as session:
        _log(session, topic="fees", reward=0.2, when=now - timedelta(days=25),
             tweet_id="t1")
        _log(session, topic="fees", reward=0.8, when=now - timedelta(days=2),
             tweet_id="t2")
        session.commit()
        stats = svc.get_arm_performance(session, days=30)
    assert "capability_delta" not in stats["topic"]["fees"]


def test_one_sided_window_produces_no_delta(svc):
    """A delta needs both halves. Otherwise it is noise wearing a number."""
    now = datetime.now(UTC)
    with get_db_session() as session:
        _log(session, topic="fees", reward=0.5, when=now - timedelta(days=2),
             tweet_id="t1")
        _log(session, topic="fees", reward=0.6, when=now - timedelta(days=1),
             tweet_id="t2")
        session.commit()
        stats = svc.get_arm_performance(session, days=30)
    assert "engagement_delta" not in stats["topic"]["fees"]


def test_trust_delta_falls_when_penalty_signals_rise(svc):
    now = datetime.now(UTC)
    early, late = now - timedelta(days=25), now - timedelta(days=2)
    with get_db_session() as session:
        _log(session, topic="fees", reward=0.2, when=early, tweet_id="t1")
        _log(session, topic="fees", reward=0.9, when=late, tweet_id="t2")
        for _ in range(4):
            row = Action(kind="block_detected")
            row.created_at = late
            session.add(row)
        session.commit()
        stats = svc.get_arm_performance(session, days=30)
    assert stats["topic"]["fees"]["trust_delta"] < 0


def test_the_guard_now_binds_to_real_telemetry(svc):
    """The whole point. Before this the guard was wired and blind."""
    now = datetime.now(UTC)
    early, late = now - timedelta(days=25), now - timedelta(days=2)
    with get_db_session() as session:
        _log(session, topic="outrage", reward=0.1, when=early, tweet_id="t1")
        _log(session, topic="outrage", reward=0.9, when=late, tweet_id="t2")
        _rating(session, tweet_id="t1", rating=5.0, when=early)
        _rating(session, tweet_id="t2", rating=1.0, when=late)
        session.commit()
        stats = svc.get_arm_performance(session, days=30)

    status = Optimizer.integrity_guard_status(stats)
    assert status["bound_to_telemetry"] is True
    assert status["arms_with_quality_signal"] > 0

    optimizer = Optimizer.__new__(Optimizer)
    successes, failures = optimizer._apply_integrity_guard(
        "topic", "outrage", stats["topic"]["outrage"], 8, 2
    )
    assert successes == 0 and failures == 10


def test_a_healthy_arm_still_reinforces_with_telemetry_present(svc):
    """Negative control: the telemetry must not punish arms that are working."""
    now = datetime.now(UTC)
    early, late = now - timedelta(days=25), now - timedelta(days=2)
    with get_db_session() as session:
        _log(session, topic="explainer", reward=0.2, when=early, tweet_id="t1")
        _log(session, topic="explainer", reward=0.9, when=late, tweet_id="t2")
        _rating(session, tweet_id="t1", rating=3.0, when=early)
        _rating(session, tweet_id="t2", rating=5.0, when=late)
        session.commit()
        stats = svc.get_arm_performance(session, days=30)

    optimizer = Optimizer.__new__(Optimizer)
    assert optimizer._apply_integrity_guard(
        "topic", "explainer", stats["topic"]["explainer"], 8, 2
    ) == (8, 2)
