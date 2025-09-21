from db.session import init_db, get_db_session
from db.models import SensedEvent
from services.perception import PerceptionService


def test_perception_ingest_records_event():
    init_db()
    service = PerceptionService()

    with get_db_session() as session:
        total = service.ingest(session)
        assert isinstance(total, int)
        assert total >= 0

    with get_db_session() as session:
        events = session.query(SensedEvent).all()
        assert len(events) == 1
        event = events[0]
        assert event.counts["voices"] >= 0
        assert event.source == "perception"
