"""Tests for dream consolidation: near-duplicate lessons merge into one."""

from unittest.mock import AsyncMock

from db.models import Note
from db.session import get_db_session, init_db
from services.consolidation import ConsolidationService
from services.ledger import DecisionLedger


def _ledger(tmp_path):
    return DecisionLedger(path=str(tmp_path / "ledger.jsonl"))


async def test_near_duplicates_merge_distinct_notes_survive(tmp_path):
    init_db()
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="Post energy proposals at 9am ET for peak engagement.")
    service = ConsolidationService(llm, ledger=_ledger(tmp_path))

    with get_db_session() as session:
        session.add(Note(text="post energy proposals earlier in the morning for engagement"))
        session.add(Note(text="energy proposals posted in the morning get more engagement"))
        session.add(Note(text="reply threads about governance need concrete citations"))
        session.commit()

        result = await service.consolidate(session)
        remaining = session.query(Note).all()

    assert result["clusters_merged"] == 1
    assert result["notes_removed"] == 1
    texts = {n.text for n in remaining}
    assert "Post energy proposals at 9am ET for peak engagement." in texts
    assert "reply threads about governance need concrete citations" in texts
    assert len(remaining) == 2


async def test_llm_failure_falls_back_to_newest_note(tmp_path):
    init_db()
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("budget exhausted"))
    service = ConsolidationService(llm, ledger=_ledger(tmp_path))

    with get_db_session() as session:
        session.add(Note(text="post energy proposals in the morning for engagement"))
        session.add(Note(text="morning energy proposals earn much higher engagement"))
        session.commit()

        result = await service.consolidate(session)
        remaining = session.query(Note).all()

    assert result["clusters_merged"] == 1
    assert len(remaining) == 1
    # Fallback keeps the newest note's text verbatim - sleep never corrupts.
    assert remaining[0].text == "morning energy proposals earn much higher engagement"


async def test_consolidation_is_ledgered_and_idempotent(tmp_path):
    init_db()
    ledger = _ledger(tmp_path)
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="Morning energy proposals earn the most engagement.")
    service = ConsolidationService(llm, ledger=ledger)

    with get_db_session() as session:
        session.add(Note(text="post energy proposals in the morning for engagement"))
        session.add(Note(text="morning energy proposals earn much higher engagement"))
        session.commit()

        await service.consolidate(session)
        events = ledger.replay("memory_consolidated")
        assert len(events) == 1
        assert events[0]["payload"]["cluster_size"] == 2

        # Second pass: nothing similar remains, nothing merges.
        second = await service.consolidate(session)
        assert second == {"clusters_merged": 0, "notes_removed": 0}
    ok, _ = ledger.verify_chain()
    assert ok is True


async def test_unrelated_notes_never_merge(tmp_path):
    init_db()
    llm = AsyncMock()
    service = ConsolidationService(llm, ledger=_ledger(tmp_path))

    with get_db_session() as session:
        session.add(Note(text="citations from reuters build authority"))
        session.add(Note(text="quadratic funding pilots convert on weekdays"))
        session.add(Note(text="threads outperform single posts at intensity two"))
        session.commit()

        result = await service.consolidate(session)
        assert result == {"clusters_merged": 0, "notes_removed": 0}
        assert session.query(Note).count() == 3
    llm.chat.assert_not_called()
