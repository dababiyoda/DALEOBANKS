import pytest

from db.session import init_db, get_db_session
from db.models import SensedEvent
from services.perception import PerceptionService


class DummyXClient:
    def __init__(self) -> None:
        self.calls = {"mentions": [], "timeline": [], "trends": []}

    async def get_mentions(self, *, since_id=None, max_results=20):
        self.calls["mentions"].append({"since_id": since_id, "max_results": max_results})
        return [
            {"id": "111", "text": "ping", "author_id": "u1"},
            {"id": "222", "text": "pong", "author_id": "u2"},
        ]

    async def get_home_timeline(self, *, limit=20, pagination_token=None):
        self.calls["timeline"].append({"limit": limit, "pagination_token": pagination_token})
        return {
            "items": [
                {"id": "t-1", "text": "timeline", "author_id": "u3"},
            ],
            "next_token": "cursor-2",
        }

    async def get_trending_topics(self, *, woeid=1, limit=10):
        self.calls["trends"].append({"woeid": woeid, "limit": limit})
        return [
            {"name": "#AI", "tweet_volume": 1000},
            {"name": "#Python", "tweet_volume": 500},
        ]


@pytest.mark.asyncio
async def test_perception_ingest_records_event_without_client():
    init_db()
    service = PerceptionService()

    with get_db_session() as session:
        total = await service.ingest(session, x_client=None)
        assert isinstance(total, int)
        assert total >= 0

    with get_db_session() as session:
        events = session.query(SensedEvent).all()
        assert len(events) == 1
        event = events[0]
        assert event.counts["voices"] >= 0
        assert event.counts["x_mentions"] == 0
        assert event.payload["x"]["mentions"] == []
        assert event.source == "perception"


@pytest.mark.asyncio
async def test_perception_ingest_uses_x_client_payload():
    init_db()
    service = PerceptionService()
    client = DummyXClient()

    with get_db_session() as session:
        total = await service.ingest(
            session,
            x_client=client,
            since_id="100",
        )

    assert isinstance(total, int)
    assert client.calls["mentions"][0]["since_id"] == "100"

    with get_db_session() as session:
        event = session.query(SensedEvent).first()

    assert event is not None
    assert event.counts["x_mentions"] == 2
    assert event.counts["x_timeline"] == 1
    assert event.counts["x_trends"] == 2
    assert event.payload["x"]["mentions"][0]["id"] == "111"
    assert event.payload["x"]["home_timeline"][0]["id"] == "t-1"
    assert event.payload["x"]["trending_topics"][0]["name"] == "#AI"
    assert event.payload["x"]["meta"]["next_token"] == "cursor-2"
    assert service.last_state["x_mentions_since_id"] == "222"
    assert service.last_state["x_timeline_token"] == "cursor-2"
