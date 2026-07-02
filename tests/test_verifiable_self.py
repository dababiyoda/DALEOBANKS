"""Phase 2: identity changes and lessons are chained into the ledger."""

from unittest.mock import AsyncMock, MagicMock, patch

from services.ledger import DecisionLedger
from services.self_model import SelfModelService


def _persona_store(mission="advance coordination"):
    store = MagicMock()
    store.get_current_persona.return_value = {
        "handle": "DaLeoBanks",
        "mission": mission,
        "beliefs": ["mechanisms beat vibes"],
        "doctrine": ["problem", "mechanism"],
        "tone_rules": {"default": "direct"},
        "guardrails": ["no deception"],
    }
    return store


async def test_identity_changes_are_chained(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    store = _persona_store()
    service = SelfModelService(store, ledger=ledger)

    await service.ensure_self_model()
    first_hash = service.get_identity_hash()

    changes = ledger.replay("identity_change")
    assert len(changes) == 1
    assert changes[0]["payload"]["old_hash"] is None
    assert changes[0]["payload"]["new_hash"] == first_hash

    # Same persona again: no new identity event.
    await service.ensure_self_model()
    assert len(ledger.replay("identity_change")) == 1

    # Persona drift: a second chained event referencing the previous hash.
    store.get_current_persona.return_value = _persona_store(
        mission="advance planetary coordination"
    ).get_current_persona()
    await service.ensure_self_model()

    changes = ledger.replay("identity_change")
    assert len(changes) == 2
    assert changes[1]["payload"]["old_hash"] == first_hash
    assert changes[1]["payload"]["new_hash"] == service.get_identity_hash()

    ok, bad = ledger.verify_chain()
    assert ok is True and bad is None


async def test_reflection_lessons_are_chained(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))

    with patch("services.reflection.MemoryService") as MockMemory, \
         patch("services.reflection.AnalyticsService"), \
         patch("services.reflection.KPIService"), \
         patch("services.reflection.Optimizer"), \
         patch("services.reflection.LLMAdapter") as MockLLM:
        from services.reflection import ReflectionService

        service = ReflectionService(ledger=ledger)
        service.memory.get_episodic_memory.return_value = [
            {"type": "action", "kind": "proposal_posted"}
        ]
        service.analytics.calculate_fame_score.return_value = {
            "engagement_proxy": 12.0,
            "follower_delta": 2.0,
            "fame_score": 40.0,
        }
        service.kpi.get_kpi_trends.return_value = {}
        service.optimizer.experiments.get_arm_recommendations.return_value = {}
        service.memory.get_recent_improvement_notes.return_value = []
        service.llm.chat = AsyncMock(
            return_value="Post energy proposals at 9am; measure reply depth."
        )

        lesson = await service.generate_reflection_async(session=MagicMock())

    chained = ledger.replay("reflection_lesson")
    assert len(chained) == 1
    assert chained[0]["payload"]["lesson"] == lesson
    assert chained[0]["payload"]["source"] == "llm"

    ok, bad = ledger.verify_chain()
    assert ok is True and bad is None
