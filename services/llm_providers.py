"""
Provider chain for OpenAI-compatible chat endpoints.

Local runtimes (Ollama, llama.cpp server, vLLM, LM Studio) and most hosted
free tiers (Groq, OpenRouter, Gemini) speak the OpenAI chat-completions wire
format, so one client type covers all of them; only base URL, key and model
differ. The chain is resolved from environment variables:

    LLM_PROVIDERS=ollama,groq,openrouter    # tried in order, then template
    OLLAMA_URL=http://localhost:11434       # /v1 appended if missing
    OLLAMA_MODEL=qwen3.6
    GROQ_API_KEY=...        GROQ_MODEL=llama-3.3-70b-versatile
    OPENROUTER_API_KEY=...  OPENROUTER_MODEL=<model id, required>
    GEMINI_API_KEY=...      GEMINI_MODEL=gemini-3.5-flash
    OPENAI_API_KEY=...      OPENAI_MODEL=gpt-4o-mini
    LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...   # "custom" provider

Without LLM_PROVIDERS the chain is inferred from whichever credentials are
present (local first, then free hosted tiers, then paid OpenAI), so an
existing OPENAI_API_KEY-only deployment behaves exactly as before.

A provider with missing configuration is skipped and reported, never
guessed. Selecting a provider grants nothing: the harness guards and the
Kernel Consequence Gate still decide what, if anything, happens next.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    base_url: Optional[str]
    url_env: Optional[str]
    key_env: Optional[str]
    model_env: str
    default_model: Optional[str]
    open_weights: bool
    needs_key: bool = True


# Base URLs are the providers' documented OpenAI-compatible endpoints.
PRESETS: Dict[str, ProviderPreset] = {
    "ollama": ProviderPreset(
        name="ollama",
        base_url="http://localhost:11434/v1",
        url_env="OLLAMA_URL",
        key_env=None,
        model_env="OLLAMA_MODEL",
        default_model="qwen3.6",
        open_weights=True,
        needs_key=False,
    ),
    "groq": ProviderPreset(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        url_env=None,
        key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL",
        default_model="llama-3.3-70b-versatile",
        open_weights=True,
    ),
    "openrouter": ProviderPreset(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        url_env=None,
        key_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        default_model=None,  # free model ids rotate; require an explicit choice
        open_weights=True,
    ),
    "gemini": ProviderPreset(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        url_env=None,
        key_env="GEMINI_API_KEY",
        model_env="GEMINI_MODEL",
        default_model="gemini-3.5-flash",
        open_weights=False,  # free tier, but closed weights
    ),
    "openai": ProviderPreset(
        name="openai",
        base_url=None,  # SDK default
        url_env=None,
        key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        default_model="gpt-4o-mini",
        open_weights=False,
    ),
    "custom": ProviderPreset(
        name="custom",
        base_url=None,
        url_env="LLM_BASE_URL",
        key_env="LLM_API_KEY",
        model_env="LLM_MODEL",
        default_model=None,
        open_weights=True,
        needs_key=False,  # many self-hosted servers ignore the key
    ),
}

# Inference order when LLM_PROVIDERS is unset: local, free hosted, paid.
INFERRED_ORDER = ("custom", "ollama", "groq", "openrouter", "gemini", "openai")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: Optional[str]
    api_key: str
    model: str
    open_weights: bool


def _normalize_ollama_url(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


def _is_present(preset: ProviderPreset, env: Mapping[str, str]) -> bool:
    if preset.url_env and env.get(preset.url_env):
        return True
    return bool(preset.key_env and env.get(preset.key_env))


def _resolve_one(
    preset: ProviderPreset, env: Mapping[str, str]
) -> Tuple[Optional[ProviderConfig], Optional[str]]:
    base_url = preset.base_url
    if preset.url_env and env.get(preset.url_env):
        base_url = env[preset.url_env]
        if preset.name == "ollama":
            base_url = _normalize_ollama_url(base_url)
    if preset.name == "custom" and not base_url:
        return None, "custom: LLM_BASE_URL is not set"

    api_key = env.get(preset.key_env, "") if preset.key_env else ""
    if preset.needs_key and not api_key:
        return None, f"{preset.name}: {preset.key_env} is not set"

    model = env.get(preset.model_env) or preset.default_model
    if not model:
        return None, f"{preset.name}: {preset.model_env} is not set"

    return (
        ProviderConfig(
            name=preset.name,
            base_url=base_url,
            # The OpenAI SDK rejects an empty key even for keyless servers.
            api_key=api_key or "not-needed",
            model=model,
            open_weights=preset.open_weights,
        ),
        None,
    )


def resolve_provider_chain(
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[List[ProviderConfig], List[str]]:
    """Return (usable providers in order, reasons for skipped providers)."""
    env = os.environ if env is None else env
    explicit = [p.strip().lower() for p in env.get("LLM_PROVIDERS", "").split(",") if p.strip()]

    if explicit:
        names = explicit
    else:
        names = [n for n in INFERRED_ORDER if _is_present(PRESETS[n], env)]

    chain: List[ProviderConfig] = []
    skipped: List[str] = []
    for name in names:
        preset = PRESETS.get(name)
        if preset is None:
            skipped.append(f"{name}: unknown provider")
            continue
        config, reason = _resolve_one(preset, env)
        if config is None:
            skipped.append(reason or f"{name}: not configured")
        elif all(existing.name != config.name for existing in chain):
            chain.append(config)
    return chain, skipped
