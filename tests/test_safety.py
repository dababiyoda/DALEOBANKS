"""Safety gates: receipts, tone, and citation validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.generator import Generator
from services.websearch import WebSearchService


@pytest.fixture
def generator_instance() -> Generator:
    persona_store = MagicMock()
    persona_store.get_current_persona.return_value = {
        "templates": {
            "tweet": "Problem → Mechanism → Pilot → KPIs → Risks → CTA",
            "reply": "Acknowledge → Mechanism → Next step",
        },
        "tone_rules": {"people": "Kind."},
    }
    llm_adapter = AsyncMock()
    return Generator(persona_store, llm_adapter)


@pytest.fixture
def empty_session() -> MagicMock:
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    return session


@pytest.mark.asyncio
async def test_proposal_requires_trusted_receipt(generator_instance: Generator, empty_session: MagicMock) -> None:
    """Spicy proposals must include at least one trusted citation."""
    proposal = (
        "Problem: Coordination stalls.\n"
        "Mechanism: Launch open pilot.\n"
        "Pilot: 30-day sprint with 3 cities.\n"
        "KPIs: 1) adoption>20% 2) NPS>50 3) rollback-ready.\n"
        "Risks: adoption + compliance.\n"
        "Rollback: Revert to manual intake if KPIs miss for 7 days.\n"
        "CTA: Join: https://example.com/pilot"
    )

    result = await generator_instance._validate_and_refine(
        proposal,
        "proposal",
        "governance",
        empty_session,
        intensity=3,
    )

    assert "error" in result
    assert "citation" in result["error"].lower()


@pytest.mark.asyncio
async def test_proposal_with_trusted_receipt_passes(generator_instance: Generator, empty_session: MagicMock) -> None:
    proposal = (
        "Problem: Coordination stalls.\n"
        "Mechanism: Launch open pilot.\n"
        "Pilot: 30-day sprint with 3 cities.\n"
        "KPIs: 1) adoption>20% 2) NPS>50 3) rollback-ready.\n"
        "Risks: adoption + compliance.\n"
        "Rollback: Revert to manual intake if KPIs miss for 7 days.\n"
        "CTA: Join: https://www.reuters.com/markets/pilot"
    )

    result = await generator_instance._validate_and_refine(
        proposal,
        "proposal",
        "governance",
        empty_session,
        intensity=2,
    )

    assert "error" not in result
    assert result["content_type"] == "proposal"


@pytest.mark.asyncio
async def test_reply_limited_to_two_sentences(generator_instance: Generator, empty_session: MagicMock) -> None:
    reply = "One sentence. Second sentence! Third sentence?"

    result = await generator_instance._validate_and_refine(
        reply,
        "reply",
        "general",
        empty_session,
        intensity=1,
    )

    assert "error" in result
    assert "two sentences" in result["error"].lower()


def test_websearch_trusted_domain_detection() -> None:
    service = WebSearchService()

    trusted = "https://www.reuters.com/world"
    untrusted = "https://blog.example.org/post"

    assert service.has_valid_citation(f"Read more: {trusted}") is True
    assert service.has_valid_citation(f"Sketchy: {untrusted}") is False
