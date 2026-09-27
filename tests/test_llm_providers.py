"""Provider chain: open-weight/free endpoints behind one OpenAI-compatible client."""

import asyncio

import pytest

from services.llm_adapter import LLMAdapter
from services.llm_harness import ModelRouter
from services.llm_providers import PRESETS, ProviderConfig, resolve_provider_chain

_PROVIDER_ENV = [
    "LLM_PROVIDERS", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
    "OLLAMA_URL", "OLLAMA_MODEL", "GROQ_API_KEY", "GROQ_MODEL",
    "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL",
    "OPENAI_API_KEY", "OPENAI_MODEL",
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in _PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_empty_env_yields_no_providers():
    chain, skipped = resolve_provider_chain({})
    assert chain == [] and skipped == []


def test_openai_only_env_is_unchanged_behavior():
    chain, _ = resolve_provider_chain({"OPENAI_API_KEY": "sk-test"})
    assert [(p.name, p.model, p.base_url) for p in chain] == [("openai", "gpt-4o-mini", None)]


def test_inferred_order_puts_local_and_free_before_paid():
    env = {
        "OPENAI_API_KEY": "sk-test",
        "GROQ_API_KEY": "gsk-test",
        "OLLAMA_URL": "http://gpu-box:11434",
    }
    chain, _ = resolve_provider_chain(env)
    assert [p.name for p in chain] == ["ollama", "groq", "openai"]
    ollama = chain[0]
    assert ollama.base_url == "http://gpu-box:11434/v1"
    assert ollama.model == PRESETS["ollama"].default_model
    assert ollama.open_weights is True


def test_explicit_chain_order_and_skip_reasons():
    env = {
        "LLM_PROVIDERS": "groq, openrouter, ollama, nonsense",
        "GROQ_API_KEY": "gsk-test",
        "OPENROUTER_API_KEY": "or-test",  # model deliberately missing
    }
    chain, skipped = resolve_provider_chain(env)
    assert [p.name for p in chain] == ["groq", "ollama"]
    assert any("OPENROUTER_MODEL" in reason for reason in skipped)
    assert any("nonsense" in reason for reason in skipped)


def test_explicit_provider_missing_key_is_skipped_not_guessed():
    chain, skipped = resolve_provider_chain({"LLM_PROVIDERS": "groq"})
    assert chain == []
    assert skipped == ["groq: GROQ_API_KEY is not set"]


def test_custom_endpoint_needs_base_url_and_model():
    chain, skipped = resolve_provider_chain({"LLM_PROVIDERS": "custom", "LLM_BASE_URL": "http://vllm:8000/v1"})
    assert chain == [] and "LLM_MODEL" in skipped[0]
    chain, _ = resolve_provider_chain(
        {"LLM_BASE_URL": "http://vllm:8000/v1", "LLM_MODEL": "Qwen/Qwen3.6-27B"}
    )
    assert chain[0].name == "custom" and chain[0].api_key == "not-needed"


def test_router_reports_first_configured_provider(clean_env):
    assert ModelRouter().route("draft") == "template"
    clean_env.setenv("GROQ_API_KEY", "gsk-test")
    assert ModelRouter().route("draft") == "groq"
    assert ModelRouter().route("screen") == "deterministic"


class _FailingCompletions:
    async def create(self, **_):
        raise ConnectionError("provider down")


class _Recording:
    def __init__(self, text):
        self.text, self.calls = text, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Msg:
            content = self.text

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = None

        return _Resp()


def _client(completions):
    class _Chat:
        pass

    class _Client:
        chat = _Chat()

    _Client.chat.completions = completions
    return _Client()


def _cfg(name, model):
    return ProviderConfig(name=name, base_url="http://x/v1", api_key="k", model=model, open_weights=True)


def test_adapter_fails_over_to_next_provider(clean_env):
    adapter = LLMAdapter(providers=[_cfg("ollama", "qwen3.6"), _cfg("groq", "llama-3.3-70b-versatile")])
    groq = _Recording("answer from groq")
    adapter.clients = {"ollama": _client(_FailingCompletions()), "groq": _client(groq)}

    reply = asyncio.run(adapter.chat("system", [{"role": "user", "content": "hi"}]))

    assert reply == "answer from groq"
    assert adapter.last_provider == "groq"
    assert groq.calls[0]["model"] == "llama-3.3-70b-versatile"
    assert groq.calls[0]["messages"][0] == {"role": "system", "content": "system"}
    assert adapter.get_budget_status()["daily_usage"].startswith("1/")


def test_adapter_degrades_to_template_when_all_providers_fail(clean_env):
    adapter = LLMAdapter(providers=[_cfg("ollama", "qwen3.6")])
    adapter.clients = {"ollama": _client(_FailingCompletions())}

    reply = asyncio.run(adapter.chat("reply system", [{"role": "user", "content": "hi"}]))

    assert adapter.last_provider == "template"
    assert reply.startswith("Interesting point.")
    assert adapter.get_budget_status()["daily_usage"].startswith("0/")


def test_adapter_raises_when_template_disabled_and_chain_empty(clean_env):
    adapter = LLMAdapter(providers=[])
    adapter.template_fallback_enabled = False
    with pytest.raises(Exception, match="no LLM provider configured"):
        asyncio.run(adapter.chat("s", [{"role": "user", "content": "hi"}]))
