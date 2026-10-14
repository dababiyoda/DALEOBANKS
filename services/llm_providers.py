"""
Explicit hosted fallbacks behind the local-first primary model.

``services.model_settings`` chooses the primary provider: local loopback
inference by default, offline templates, or explicitly selected OpenAI. This
module adds an optional, ordered list of hosted fallbacks that are tried only
after the primary fails, then the template fallback:

    LLM_FALLBACKS=groq,openrouter           # empty/unset = no fallbacks
    GROQ_API_KEY=...        GROQ_MODEL=llama-3.3-70b-versatile
    OPENROUTER_API_KEY=...  OPENROUTER_MODEL=<model id, required>
    GEMINI_API_KEY=...      GEMINI_MODEL=gemini-3.5-flash
    OPENAI_API_KEY=...      OPENAI_MODEL=gpt-4o-mini   # paid; only if listed

Nothing is inferred from which keys happen to be present: a hosted fallback
sends prompts off this machine, so it runs only when named here. Base URLs
are fixed per provider so a key can never be sent to an arbitrary host. A
listed provider with missing configuration is skipped with a reason, never
guessed. Offline template mode (``LLM_PROVIDER=template``) makes no calls at
all, fallbacks included.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class HostedPreset:
    name: str
    base_url: str
    key_env: str
    model_env: str
    default_model: Optional[str]
    open_weights: bool
    paid: bool


# Base URLs are the providers' documented OpenAI-compatible endpoints.
PRESETS: Dict[str, HostedPreset] = {
    "groq": HostedPreset("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
                         "GROQ_MODEL", "llama-3.3-70b-versatile", open_weights=True, paid=False),
    "openrouter": HostedPreset("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                               "OPENROUTER_MODEL", None, open_weights=True, paid=False),
    "gemini": HostedPreset("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
                           "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-3.5-flash",
                           open_weights=False, paid=False),
    "openai": HostedPreset("openai", "https://api.openai.com/v1", "OPENAI_API_KEY",
                           "OPENAI_MODEL", "gpt-4o-mini", open_weights=False, paid=True),
}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    open_weights: bool
    paid: bool


def resolve_fallbacks(
    env: Optional[Mapping[str, str]] = None,
    *,
    primary: Optional[str] = None,
) -> Tuple[List[ProviderConfig], List[str]]:
    """Return (usable hosted fallbacks in order, reasons for skipped entries)."""
    env = os.environ if env is None else env
    names = [n.strip().lower() for n in env.get("LLM_FALLBACKS", "").split(",") if n.strip()]

    chain: List[ProviderConfig] = []
    skipped: List[str] = []
    for name in names:
        preset = PRESETS.get(name)
        if preset is None:
            skipped.append(f"{name}: not a hosted fallback (choose from {', '.join(PRESETS)})")
            continue
        if name == primary or any(p.name == name for p in chain):
            skipped.append(f"{name}: already in the chain")
            continue
        key = env.get(preset.key_env, "").strip()
        if not key:
            skipped.append(f"{name}: {preset.key_env} is not set")
            continue
        model = (env.get(preset.model_env) or preset.default_model or "").strip()
        if not model:
            skipped.append(f"{name}: {preset.model_env} is not set")
            continue
        chain.append(ProviderConfig(name, preset.base_url, key, model, preset.open_weights, preset.paid))
    return chain, skipped
