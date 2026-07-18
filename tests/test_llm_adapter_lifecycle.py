import pytest

from services.llm_adapter import LLMAdapter


def test_adapter_does_not_construct_provider_client_at_startup(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("provider client must be created lazily")

    monkeypatch.setattr("services.llm_adapter.openai.AsyncOpenAI", fail_if_constructed)

    adapter = LLMAdapter()

    assert adapter.client is None


@pytest.mark.asyncio
async def test_missing_provider_configuration_uses_template_fallback(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("fallback must not construct a provider client")

    monkeypatch.setattr("services.llm_adapter.openai.AsyncOpenAI", fail_if_constructed)

    adapter = LLMAdapter()
    adapter.config.OPENAI_API_KEY = ""
    result = await adapter.chat(
        system="Draft a proposal",
        messages=[{"role": "user", "content": "Test"}],
    )

    assert "Pilot:" in result
    assert adapter.client is None
