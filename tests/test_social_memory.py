"""Tests for real social memory: Relationship records and segments."""

from db.models import Relationship
from db.session import get_db_session, init_db
from services.memory import MemoryService


def _service():
    return MemoryService()


def test_record_interaction_upserts_and_counts():
    init_db()
    service = _service()

    with get_db_session() as session:
        rel = service.record_interaction(
            session, user_id="42", handle="ally", kind="mention",
            topic="energy", text="I love this excellent proposal",
        )
        assert rel.interaction_count == 1
        assert rel.handle == "ally"
        assert rel.topics == ["energy"]
        assert rel.kinds == {"mention": 1}

        rel = service.record_interaction(
            session, user_id="42", kind="dm", topic="grids",
        )
        assert rel.interaction_count == 2
        assert rel.kinds == {"mention": 1, "dm": 1}
        assert rel.topics == ["energy", "grids"]

        # One record total, not two.
        assert session.query(Relationship).count() == 1


def test_sentiment_is_a_running_average():
    init_db()
    service = _service()

    with get_db_session() as session:
        service.record_interaction(
            session, user_id="7", kind="mention",
            text="this is excellent, great work, love it",
        )
        first = service.get_relationship(session, "7").sentiment_score
        assert first > 0

        service.record_interaction(
            session, user_id="7", kind="mention",
            text="terrible awful broken garbage",
        )
        second = service.get_relationship(session, "7").sentiment_score
        assert second < first


def test_social_memory_segments_and_communities():
    init_db()
    service = _service()

    with get_db_session() as session:
        for _ in range(3):
            service.record_interaction(
                session, user_id="ally1", handle="ally1", kind="mention",
                topic="energy", text="excellent great love this",
            )
        for _ in range(2):
            service.record_interaction(
                session, user_id="critic1", handle="critic1", kind="mention",
                topic="energy", text="terrible awful hate this",
            )
        service.record_interaction(
            session, user_id="newbie", handle="newbie", kind="dm",
        )

        social = service.get_social_memory(session)

    influential = social["influential_interactions"]
    assert influential[0]["id"] == "ally1"
    assert influential[0]["interactions"] == 3

    segments = social["follower_segments"]
    assert [r["id"] for r in segments["allies"]] == ["ally1"]
    assert [r["id"] for r in segments["critics"]] == ["critic1"]
    assert [r["id"] for r in segments["new_contacts"]] == ["newbie"]

    assert set(social["topic_communities"]["energy"]) == {"ally1", "critic1"}


def test_relationships_are_semantically_recallable(tmp_path, monkeypatch):
    from services import semantic_index as si_module
    from services.semantic_index import SemanticIndex

    isolated = SemanticIndex(path=str(tmp_path / "social.jsonl"))
    monkeypatch.setattr(si_module, "_SHARED_INDEX", isolated)

    init_db()
    service = _service()
    with get_db_session() as session:
        service.record_interaction(
            session, user_id="99", handle="gridwonk", kind="mention",
            topic="transmission", text="interconnection queues are the bottleneck",
        )

    hits = isolated.search("transmission interconnection", k=1)
    assert hits and hits[0]["meta"]["kind"] == "social"
