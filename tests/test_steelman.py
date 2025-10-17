import pytest

from services.generator import Generator
from services.llm_adapter import LLMAdapter


class StubLLM(LLMAdapter):
    async def chat(self, *args, **kwargs):
        return "We appreciate the pushback about timelines so let's clarify scope. We can concede the constraint on staffing." \
               " The core mechanism is to run a tight pilot with week-one metrics so finance stays looped in."


class StubPersonaStore:
    def get_current_persona(self):
        return {}


@pytest.mark.asyncio
async def test_enforce_steelman_preserves_two_sentence_cadence_with_citation():
    generator = Generator(StubPersonaStore(), StubLLM())
    sample = (
        "We agree on the staffing constraint."
        " Let's narrow scope and show receipts with Reuters coverage https://reuters.com/example."
        " That keeps everyone aligned."
    )

    enforced = generator._enforce_steelman(sample, intensity=3)
    sentences = generator._split_sentences(enforced)

    assert 1 <= len(sentences) <= 2
    assert "https://reuters.com/example" in enforced


@pytest.mark.asyncio
async def test_enforce_steelman_adds_safety_language_when_citation_missing():
    generator = Generator(StubPersonaStore(), StubLLM())
    sample = "We hear the urgency on timelines. We can revisit once we have receipts."

    enforced = generator._enforce_steelman(sample, intensity=3)
    sentences = generator._split_sentences(enforced)

    assert 1 <= len(sentences) <= 2
    assert "trusted receipt" in enforced.lower()
