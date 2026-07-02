"""Tests for DM ingest: the agent can hear private messages safely."""

import types

import pytest

import runner
from db.models import Action, Relationship
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances


class FakeDMClient:
    def __init__(self, events, self_id="me123"):
        self.events = events
        self.self_id = self_id

    def is_healthy(self):
        return True

    async def get_dm_events(self, **kwargs):
        return {"events": self.events, "next_token": None}


@pytest.fixture
def dm_env(tmp_path, monkeypatch):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    monkeypatch.setattr(runner.config, "ENABLE_DMS", True)
    yield ledger
    reset_shared_instances()


async def test_inbound_dms_are_stored_and_deduped(dm_env, monkeypatch):
    events = [
        {"id": "e1", "text": "Interested in the energy pilot", "sender_id": "u1",
         "event_type": "MessageCreate", "created_at": None},
        {"id": "e2", "text": "own outbound message", "sender_id": "me123",
         "event_type": "MessageCreate", "created_at": None},
    ]
    monkeypatch.setattr(runner, "x_client", FakeDMClient(events))

    await runner.dm_ingest_job()
    await runner.dm_ingest_job()  # second run must not duplicate

    with get_db_session() as session:
        received = session.query(Action).filter(lambda a: a.kind == "dm_received").all()
        rels = session.query(Relationship).all()

    assert len(received) == 1
    assert received[0].meta_json["dm_event_id"] == "e1"
    assert received[0].meta_json["sender_id"] == "u1"
    # Our own outbound event was skipped.
    assert all(a.meta_json["sender_id"] != "me123" for a in received)
    # Relationship recorded for the sender.
    assert any(r.id == "u1" and r.kinds.get("dm") for r in rels)


async def test_harmful_dm_is_flagged_not_heard(dm_env, monkeypatch):
    events = [
        {"id": "bad1", "text": "let's attack and destroy their systems",
         "sender_id": "u9", "event_type": "MessageCreate", "created_at": None},
    ]
    monkeypatch.setattr(runner, "x_client", FakeDMClient(events))

    await runner.dm_ingest_job()

    with get_db_session() as session:
        flagged = session.query(Action).filter(lambda a: a.kind == "dm_flagged").all()
        received = session.query(Action).filter(lambda a: a.kind == "dm_received").all()

    assert len(flagged) == 1 and flagged[0].meta_json["flag_reasons"]
    assert received == []
    # Flagged messages never become reply candidates.
    with get_db_session() as session:
        assert runner._find_unanswered_dm(session) is None


async def test_ledger_gets_metadata_but_never_private_text(dm_env, monkeypatch):
    ledger = dm_env
    events = [
        {"id": "e5", "text": "very private message content", "sender_id": "u5",
         "event_type": "MessageCreate", "created_at": None},
    ]
    monkeypatch.setattr(runner, "x_client", FakeDMClient(events))

    await runner.dm_ingest_job()

    entries = ledger.replay("dm_received")
    assert len(entries) == 1
    assert entries[0]["payload"] == {"event_id": "e5", "sender_id": "u5", "flagged": False}
    assert "private message" not in str(entries[0])


async def test_value_dm_replies_to_unanswered_inbound_first(dm_env, monkeypatch):
    with get_db_session() as session:
        session.add(Action(kind="dm_received", meta_json={
            "dm_event_id": "e7", "sender_id": "u7",
            "text": "How do I join the pilot?", "flag_reasons": [],
        }))
        session.commit()

    captured = {}

    async def fake_dm_copy(seed, *, topic, recipient, intensity):
        captured["seed"] = seed
        captured["recipient"] = recipient
        return {"content": "Here is how to join the pilot."}

    monkeypatch.setattr(runner.crisis_service, "guard", lambda action: True)
    monkeypatch.setattr(runner.generator, "make_dm_copy", fake_dm_copy)
    monkeypatch.setattr(runner, "x_client", types.SimpleNamespace(
        is_healthy=lambda: True))
    previous_live = runner.config.LIVE
    runner.config.LIVE = False  # draft path, no send

    try:
        await runner.value_dm_job()
    finally:
        runner.config.LIVE = previous_live

    assert captured["recipient"]["id"] == "u7"
    assert "How do I join the pilot?" in captured["seed"]

    with get_db_session() as session:
        drafted = session.query(Action).filter(
            lambda a: a.kind == "value_dm_drafted"
        ).all()
    assert len(drafted) == 1
    assert drafted[0].meta_json["reply_to_event_id"] == "e7"

    # Once answered (drafted counts), the same DM is not picked again.
    with get_db_session() as session:
        assert runner._find_unanswered_dm(session) is None
