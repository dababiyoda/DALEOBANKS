"""Explicit hosted fallbacks behind the local-first primary model."""

import asyncio
from types import SimpleNamespace

import pytest

from services import llm_adapter
from services.llm_providers import PRESETS, ProviderConfig, resolve_fallbacks

_ENV = [
    "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "OLLAMA_URL", "LLM_FALLBACKS",
    "GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
    "GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_keys_alone_never_create_fallbacks():
    env = {"GROQ_API_KEY": "gsk", "OPENROUTER_API_KEY": "or", "OPENAI_API_KEY": "sk"}
    assert resolve_fallbacks(env) == ([], [])


def test_listed_fallbacks_resolve_in_order_with_fixed_urls():
    env = {"LLM_FALLBACKS": "groq, gemini", "GROQ_API_KEY": "gsk", "GEMINI_API_KEY": "gm"}
    chain, skipped = resolve_fallbacks(env)
    assert [(p.name, p.model, p.base_url) for p in chain] == [
        ("groq", "llama-3.3-70b-versatile", PRESETS["groq"].base_url),
        ("gemini", "gemini-3.5-flash", PRESETS["gemini"].base_url),
    ]
    assert skipped == []
    assert chain[0].open_weights and not chain[1].open_weights


def test_missing_config_unknown_and_duplicate_entries_are_skipped_not_guessed():
    env = {"LLM_FALLBACKS": "openrouter,ollama,groq,groq,openai", "OPENROUTER_API_KEY": "or",
           "GROQ_API_KEY": "gsk"}
    chain, skipped = resolve_fallbacks(env, primary="openai")
    assert [p.name for p in chain] == ["groq"]
    assert any("OPENROUTER_MODEL" in r for r in skipped)
    assert any(r.startswith("ollama: not a hosted fallback") for r in skipped)
    assert any(r == "groq: already in the chain" for r in skipped)
    assert any(r == "openai: already in the chain" for r in skipped)


def test_paid_openai_only_when_listed_and_marked_paid():
    chain, _ = resolve_fallbacks({"LLM_FALLBACKS": "openai", "OPENAI_API_KEY": "sk"})
    assert chain[0].name == "openai" and chain[0].paid is True


class _Recorder:
    def __init__(self):
        self.clients = []

    def __call__(self, **kwargs):
        record = {"kwargs": kwargs, "calls": []}
        self.clients.append(record)
        outcome = self.outcomes.get(kwargs["base_url"], "ok")

        async def create(**call):
            record["calls"].append(call)
            if isinstance(outcome, Exception):
                raise outcome
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"from {call['model']}"))],
                                   usage=SimpleNamespace(total_tokens=1))

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _adapter(monkeypatch, outcomes):
    recorder = _Recorder()
    recorder.outcomes = outcomes
    monkeypatch.setattr(llm_adapter.openai, "AsyncOpenAI", recorder)
    return llm_adapter.LLMAdapter(), recorder


def _close(recorder):
    for client in recorder.clients:
        asyncio.run(client["kwargs"]["http_client"].aclose())


def test_local_primary_serves_without_touching_fallbacks(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACKS", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    adapter, recorder = _adapter(monkeypatch, {})
    assert asyncio.run(adapter.chat("s", [{"role": "user", "content": "hi"}])) == "from qwen3.5:4b"
    assert adapter.last_provider == "ollama"
    groq = next(c for c in recorder.clients if c["kwargs"]["base_url"] == PRESETS["groq"].base_url)
    assert groq["calls"] == []
    _close(recorder)


def test_local_failure_fails_over_to_listed_hosted_fallback(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACKS", "openrouter,groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    monkeypatch.setenv("OPENROUTER_MODEL", "some/model:free")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    adapter, recorder = _adapter(monkeypatch, {
        "http://127.0.0.1:11434/v1": ConnectionError("ollama not running"),
        PRESETS["openrouter"].base_url: RuntimeError("daily cap"),
    })
    reply = asyncio.run(adapter.chat("s", [{"role": "user", "content": "hi"}]))
    assert reply == "from llama-3.3-70b-versatile"
    assert adapter.last_provider == "groq"
    status = adapter.get_budget_status()
    assert status["daily_usage"].startswith("1/")
    assert [f["name"] for f in status["fallbacks"]] == ["openrouter", "groq"]
    hosted = [c["kwargs"] for c in recorder.clients if c["kwargs"]["base_url"] != "http://127.0.0.1:11434/v1"]
    assert all(k["http_client"].follow_redirects is False for k in hosted)
    _close(recorder)


def test_all_failing_degrades_to_template_as_before(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACKS", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    adapter, recorder = _adapter(monkeypatch, {
        "http://127.0.0.1:11434/v1": ConnectionError("down"),
        PRESETS["groq"].base_url: ConnectionError("down"),
    })
    reply = asyncio.run(adapter.chat("reply system", [{"role": "user", "content": "hi"}]))
    assert reply.startswith("Interesting point.")
    assert adapter.last_provider == "template"
    _close(recorder)


def test_template_mode_makes_no_calls_even_with_fallbacks(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "template")
    monkeypatch.setenv("LLM_FALLBACKS", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    adapter, recorder = _adapter(monkeypatch, {})
    asyncio.run(adapter.chat("s", [{"role": "user", "content": "hi"}]))
    assert recorder.clients == [] and adapter.fallbacks == []
    assert adapter.last_provider == "template"
