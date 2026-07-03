"""Tests for the reception predictor (internal simulator)."""

from db.models import Tweet
from db.session import get_db_session, init_db
from services.simulator import ReceptionPredictor


def _seed(session, topic, hour, scores):
    for i, score in enumerate(scores):
        session.add(Tweet(
            id=f"{topic}-{hour}-{i}", text="x", kind="proposal",
            topic=topic, hour_bin=hour, j_score=score,
        ))
    session.commit()


def test_thin_history_predicts_nothing():
    init_db()
    predictor = ReceptionPredictor(min_samples=5)

    with get_db_session() as session:
        _seed(session, "energy", 9, [0.8, 0.7])
        result = predictor.predict(session, topic="energy", hour=9)

    assert result["predicted_j"] is None
    assert result["basis"] == "insufficient_history"
    assert result["confidence"] == 0.0


def test_strong_topic_predicts_higher_than_weak_topic():
    init_db()
    predictor = ReceptionPredictor(min_samples=5)

    with get_db_session() as session:
        _seed(session, "energy", 9, [0.9, 0.85, 0.8, 0.9])
        _seed(session, "gossip", 21, [0.1, 0.15, 0.1, 0.05])

        strong = predictor.predict(session, topic="energy", hour=9)
        weak = predictor.predict(session, topic="gossip", hour=21)

    assert strong["predicted_j"] is not None
    assert strong["predicted_j"] > weak["predicted_j"]
    assert 0 < strong["confidence"] <= 1


def test_unknown_topic_shrinks_to_global_mean():
    init_db()
    predictor = ReceptionPredictor(min_samples=5)

    with get_db_session() as session:
        _seed(session, "energy", 9, [0.6, 0.6, 0.6, 0.6, 0.6])
        result = predictor.predict(session, topic="never-seen", hour=3)

    # No topic or hour evidence: the prediction is exactly the global mean.
    assert result["predicted_j"] == result["global_mean"] == 0.6
    assert result["samples"]["topic"] == 0
    assert result["samples"]["hour"] == 0


def test_shrinkage_tempers_small_samples():
    init_db()
    predictor = ReceptionPredictor(min_samples=5, shrinkage=3.0)

    with get_db_session() as session:
        # Global mean pulled low by many mediocre posts...
        _seed(session, "misc", 12, [0.3] * 10)
        # ...one lucky high-scorer on a new topic must not dominate.
        _seed(session, "newtopic", 9, [1.0])

        result = predictor.predict(session, topic="newtopic", hour=9)

    global_mean = result["global_mean"]
    # Prediction sits between the global mean and the single sample,
    # much closer to the mean than to 1.0.
    assert global_mean < result["predicted_j"] < 0.6
