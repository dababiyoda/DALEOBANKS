import json

import pytest

from db.session import init_db
from services.generator import Generator
from services.persona_store import PersonaStore


class StubLLM:
    def __init__(self, payload):
        self.payload = payload

    async def chat(self, *, system, messages, temperature):  # noqa: D401 - simple stub
        return json.dumps(self.payload)


@pytest.mark.asyncio
async def test_make_thread_returns_valid_posts(monkeypatch):
    init_db()

    payload = {
        "posts": [
            {
                "text": "1/ Systemic issue with receipts https://www.reuters.com/example. Next step: convene the pilot.",
                "media": {"path": "image.png", "type": "image", "alt": "chart"},
            },
            {
                "text": "2/ Mechanism and next step https://www.reuters.com/followup",
            },
        ],
        "dm_copy": "Sharing a follow-up with receipts https://www.reuters.com/followup",
    }

    persona = PersonaStore()
    generator = Generator(persona, StubLLM(payload))

    result = await generator.make_thread(topic="coordination", intensity=3)

    assert "error" not in result
    assert len(result["posts"]) == 2
    first_media = result["posts"][0]["media"][0]
    assert first_media["path"] == "image.png"
    assert first_media["type"] == "image"
    assert "dm_copy" in result and "follow-up" in result["dm_copy"]


@pytest.mark.asyncio
async def test_make_thread_requires_citation_at_high_intensity(monkeypatch):
    init_db()

    payload = {
        "posts": [
            {"text": "1/ Strong claim without link. Next step: invite partners."},
        ],
    }

    persona = PersonaStore()
    generator = Generator(persona, StubLLM(payload))

    result = await generator.make_thread(topic="policy", intensity=3, include_dm=False)

    assert "error" in result
    assert "credible" in result["details"]["error"].lower()


@pytest.mark.asyncio
async def test_make_dm_copy_trims_and_respects_guardrails(monkeypatch):
    init_db()

    class DMStub:
        async def chat(self, *, system, messages, temperature):
            return "Offering a helpful resource on coordination with trusted data."

    persona = PersonaStore()
    generator = Generator(persona, DMStub())

    dm = await generator.make_dm_copy(
        "Highlight the coalition opportunity.",
        topic="energy",
        recipient={"username": "ally"},
        intensity=2,
    )

    assert "error" not in dm
    assert dm["content"].startswith("Offering a helpful resource")
    assert dm["recipient"]["username"] == "ally"
