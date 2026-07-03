"""Tests for the compounding advantages: calibration, relationship-aware
replies, and the evidence library."""

from db.models import Tweet
from db.session import get_db_session, init_db
from services.evidence_library import EvidenceLibrary
from services.simulator import ReceptionPredictor


# ---------------------------------------------------------------------- #
# Evidence library
# ---------------------------------------------------------------------- #
def test_evidence_records_once_and_recalls_by_topic(tmp_path):
    library = EvidenceLibrary(path=str(tmp_path / "evidence.jsonl"))

    first = library.record(
        url="https://www.reuters.com/energy/grid-report",
        topic="energy",
        context="grid interconnection queues doubled",
    )
    duplicate = library.record(
        url="https://www.reuters.com/energy/grid-report",
        topic="energy",
    )
    library.record(url="https://apnews.com/governance-piece", topic="governance")

    assert first is not None
    assert duplicate is None  # same URL banks only once
    assert len(library) == 2

    hits = library.recall("energy grid", k=2)
    assert hits and hits[0]["url"] == "https://www.reuters.com/energy/grid-report"


def test_evidence_survives_restart(tmp_path):
    path = str(tmp_path / "evidence.jsonl")
    EvidenceLibrary(path=path).record(url="https://apnews.com/x", topic="energy")

    reloaded = EvidenceLibrary(path=path)
    assert len(reloaded) == 1
    # Dedupe knowledge survives too.
    assert reloaded.record(url="https://apnews.com/x", topic="energy") is None


def test_validated_proposals_bank_their_citations(tmp_path, monkeypatch):
    from services import evidence_library as el_module
    from unittest.mock import AsyncMock, MagicMock
    from services.generator import Generator

    isolated = EvidenceLibrary(path=str(tmp_path / "evidence.jsonl"))
    monkeypatch.setattr(el_module, "_SHARED_LIBRARY", isolated)

    persona_store = MagicMock()
    persona_store.get_current_persona.return_value = {"templates": {}}
    generator = Generator(persona_store, AsyncMock())

    content = (
        "Problem: grid queues. Mechanism: shared dispatch. Pilot: 30 days. "
        "KPI: 20% fewer delays. Risk: adoption. Rollback: revert. "
        "Uncertainty noted. CTA: join. https://www.reuters.com/energy/grid"
    )
    init_db()

    import asyncio

    async def run():
        with get_db_session() as session:
            return await generator._validate_and_refine(
                content, "proposal", "energy", session, 1
            )

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(run())
    finally:
        loop.close()

    assert "error" not in result
    assert len(isolated) == 1
    assert isolated.recall("energy", k=1)[0]["url"].startswith("https://www.reuters.com")


# ---------------------------------------------------------------------- #
# Prediction calibration
# ---------------------------------------------------------------------- #
def _seed_scored(session, n, predicted, actual, topic="energy", hour=9):
    for i in range(n):
        session.add(Tweet(
            id=f"{topic}{hour}{predicted}{i}", text="x", kind="proposal",
            topic=topic, hour_bin=hour, j_score=actual, predicted_j=predicted,
        ))
    session.commit()


def test_bias_correction_learns_from_past_errors():
    init_db()
    predictor = ReceptionPredictor(min_samples=5, shrinkage=3.0)

    with get_db_session() as session:
        # History: we consistently predicted 0.4 but reality was 0.6.
        _seed_scored(session, 8, predicted=0.4, actual=0.6)

        result = predictor.predict(session, topic="energy", hour=9)

    # The correction pushes the forecast above the raw historical mean.
    assert result["bias_correction"] > 0.1
    assert result["predicted_j"] > 0.6


def test_prediction_accuracy_summary():
    init_db()
    predictor = ReceptionPredictor()

    with get_db_session() as session:
        _seed_scored(session, 4, predicted=0.5, actual=0.7)
        accuracy = predictor.prediction_accuracy(session)

    assert accuracy["pairs"] == 4
    assert abs(accuracy["mean_error"] - 0.2) < 1e-6
    assert abs(accuracy["mean_abs_error"] - 0.2) < 1e-6


def test_accuracy_empty_without_scored_pairs():
    init_db()
    predictor = ReceptionPredictor()
    with get_db_session() as session:
        assert predictor.prediction_accuracy(session)["pairs"] == 0


# ---------------------------------------------------------------------- #
# Relationship-aware replies
# ---------------------------------------------------------------------- #
def test_reply_prompt_includes_relationship_history():
    from unittest.mock import AsyncMock, MagicMock
    from services.generator import Generator

    persona_store = MagicMock()
    persona_store.get_current_persona.return_value = {"templates": {"reply": "t"}, "tone_rules": {}}
    persona_store.get_reply_style_override.return_value = ""
    generator = Generator(persona_store, AsyncMock())

    context = {
        "original_tweet": "what about queue reform?",
        "author_info": {"username": "gridwonk"},
        "relationship": {
            "handle": "gridwonk",
            "interactions": 4,
            "sentiment": 0.35,
            "topics": ["transmission", "energy"],
        },
    }
    prompt = generator._build_reply_prompt(context, {}, 1)

    assert "4 prior interactions" in prompt
    assert "+0.35" in prompt
    assert "transmission, energy" in prompt

    # Without history, no fabricated familiarity.
    bare = generator._build_reply_prompt(
        {"original_tweet": "hi", "author_info": {"username": "new"}}, {}, 1
    )
    assert "prior interactions" not in bare
