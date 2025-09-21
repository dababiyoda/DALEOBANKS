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
async def test_enforce_steelman_cadence():
    generator = Generator(StubPersonaStore(), StubLLM())
    sample = "One long reply without cadence."  # base text is ignored in enforcement
    enforced = generator._enforce_steelman(sample, intensity=3)
    sentences = generator._split_sentences(enforced)
    assert len(sentences) == 3
    lengths = [len(sentence.split()) for sentence in sentences]
    assert lengths[0] <= 18
    assert lengths[1] <= 18
    assert lengths[2] >= 24
    assert generator.critic.has_periodic_cadence(enforced)
