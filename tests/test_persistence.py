"""Tests for the durable object store (db/session.py persistence layer)."""

from datetime import datetime, UTC

from db.models import Action, Note, Tweet
from db.session import get_db_session, init_db


def _enable_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSIST_STORE", "true")
    monkeypatch.setenv("DB_SNAPSHOT_PATH", str(tmp_path / "store.jsonl"))


def test_store_survives_restart(monkeypatch, tmp_path):
    _enable_persistence(monkeypatch, tmp_path)
    init_db()

    with get_db_session() as session:
        session.add(Tweet(id="t1", text="hello world", kind="proposal", topic="energy"))
        session.add(Action(kind="proposal_posted", meta_json={"tweet_id": "t1"}))
        session.add(Note(text="post earlier in the day"))
        session.commit()

    # Simulate a restart: init_db clears memory and reloads the snapshot.
    init_db()

    with get_db_session() as session:
        tweets = session.query(Tweet).all()
        actions = session.query(Action).all()
        notes = session.query(Note).all()

    assert len(tweets) == 1 and tweets[0].text == "hello world"
    assert len(actions) == 1 and actions[0].meta_json == {"tweet_id": "t1"}
    assert len(notes) == 1

    # Typed datetime fields are restored as datetimes, not strings.
    assert isinstance(tweets[0].created_at, datetime)
    assert tweets[0].created_at.tzinfo is not None


def test_datetime_queries_work_after_reload(monkeypatch, tmp_path):
    _enable_persistence(monkeypatch, tmp_path)
    init_db()

    with get_db_session() as session:
        session.add(Action(kind="a"))
        session.add(Action(kind="b"))
        session.commit()

    init_db()

    cutoff = datetime(2000, 1, 1, tzinfo=UTC)
    with get_db_session() as session:
        recent = (
            session.query(Action)
            .filter(lambda a: a.created_at >= cutoff)
            .order_by(lambda a: a.created_at, descending=True)
            .all()
        )
    assert [a.kind for a in recent] in (["a", "b"], ["b", "a"])
    assert len(recent) == 2


def test_delete_removes_and_persists(monkeypatch, tmp_path):
    _enable_persistence(monkeypatch, tmp_path)
    init_db()

    with get_db_session() as session:
        note = Note(text="ephemeral")
        session.add(note)
        session.commit()
        session.delete(note)
        session.commit()

    init_db()
    with get_db_session() as session:
        assert session.query(Note).count() == 0


def test_persistence_disabled_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSIST_STORE", "false")
    monkeypatch.setenv("DB_SNAPSHOT_PATH", str(tmp_path / "store.jsonl"))
    init_db()

    with get_db_session() as session:
        session.add(Note(text="in memory only"))
        session.commit()

    assert not (tmp_path / "store.jsonl").exists()

    init_db()
    with get_db_session() as session:
        assert session.query(Note).count() == 0


def test_corrupt_snapshot_lines_are_skipped(monkeypatch, tmp_path):
    _enable_persistence(monkeypatch, tmp_path)
    snapshot = tmp_path / "store.jsonl"
    init_db()
    with get_db_session() as session:
        session.add(Note(text="good"))
        session.commit()

    with open(snapshot, "a") as f:
        f.write("not json at all\n")
        f.write('{"model": "NoSuchModel", "data": {}}\n')

    init_db()
    with get_db_session() as session:
        notes = session.query(Note).all()
    assert len(notes) == 1 and notes[0].text == "good"


def test_note_pruning_uses_delete(monkeypatch, tmp_path):
    """Regression: MemoryService pruning calls session.delete (was missing)."""
    _enable_persistence(monkeypatch, tmp_path)
    init_db()

    from services.memory import MemoryService

    service = MemoryService()
    service.max_improvement_notes = 5

    with get_db_session() as session:
        for i in range(7):
            service.add_improvement_note(session, f"lesson {i}")
        remaining = session.query(Note).count()

    assert remaining <= 5
