"""Free default, paid opt-in, and local embedding boundary checks."""
import asyncio
from types import SimpleNamespace

import pytest

from services.embeddings import EmbeddingService, tag_key
from services.llm_harness import ModelRouter
from services.model_settings import local_base_url, model_settings


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "OLLAMA_URL", "EMBEDDINGS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-legacy-key")


def test_legacy_key_does_not_select_paid_model():
    selected = model_settings()
    assert selected.provider == "ollama"
    assert selected.model == "qwen3.5:4b"
    assert selected.base_url == "http://127.0.0.1:11434/v1"
    assert selected.api_key == "local"
    assert ModelRouter().route("draft") == "ollama"


@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1", "http://example.com", "http://localhost?token=x",
    "http://secret@localhost", "file:///tmp/model",
])
def test_local_url_never_becomes_a_hosted_api(url):
    with pytest.raises(ValueError):
        local_base_url(url)


def test_explicit_hosted_mode_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ValueError):
        model_settings()


def test_offline_template_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "template")
    assert ModelRouter().route("draft") == "template"
    assert ModelRouter().route("screen") == "deterministic"


def test_adapter_sends_configured_local_model(monkeypatch):
    from services import llm_adapter
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="local result"))],
                               usage=SimpleNamespace(total_tokens=2))

    def client(**kwargs):
        captured["client"] = kwargs
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(llm_adapter.openai, "AsyncOpenAI", client)
    adapter = llm_adapter.LLMAdapter()
    assert asyncio.run(adapter.chat("system", [{"role": "user", "content": "request"}])) == "local result"
    assert captured["model"] == "qwen3.5:4b"
    assert captured["client"]["base_url"].startswith("http://127.0.0.1")
    assert captured["client"]["api_key"] == "local"
    asyncio.run(captured["client"]["http_client"].aclose())


def test_auto_embeddings_do_not_spend_for_existing_key(monkeypatch):
    service = EmbeddingService(mode="auto")
    monkeypatch.setattr(service, "_openai_embed", lambda _: pytest.fail("unexpected paid embedding"))
    assert service.embed("recall")[1]["provider"] == "hash"


def test_local_embeddings_fall_back_to_hash_without_paid_call(monkeypatch):
    service = EmbeddingService(mode="ollama")
    monkeypatch.setattr(service, "_local_embed", lambda _: None)
    monkeypatch.setattr(service, "_openai_embed", lambda _: pytest.fail("unexpected paid fallback"))
    assert service.embed("recall")[1]["provider"] == "hash"


def test_local_vectors_keep_model_identity(monkeypatch):
    service = EmbeddingService(mode="ollama")
    monkeypatch.setattr(service, "_local_embed", lambda _: {0: 0.6, 1: 0.8})
    _, tag = service.embed("recall")
    assert tag == {"provider": "local", "model": "nomic-embed-text", "dim": 2}
    assert tag_key(tag) != tag_key({**tag, "model": "different-model"})
