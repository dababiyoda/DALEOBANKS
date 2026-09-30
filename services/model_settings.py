"""Provider selection: local inference by default; hosted billing is explicit."""
from __future__ import annotations

import ipaddress
import os
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit


def local_base_url(value: str) -> str:
    url = urlsplit(value)
    try:
        local = url.hostname == "localhost" or ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        local = False
    if (not local or url.scheme not in ("http", "https")
            or url.username or url.password or url.query or url.fragment
            or url.path.rstrip("/") not in ("", "/v1")):
        raise ValueError("local models require a loopback URL with no credentials")
    return value.rstrip("/") + ("/v1" if not url.path.rstrip("/") else "")


class NoLocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("local inference redirects are refused")


def local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoLocalRedirect())


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    model: str
    base_url: str
    api_key: str


def model_settings() -> ModelSettings:
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider == "template":
        return ModelSettings(provider, "", "", "")
    if provider in ("ollama", "local"):
        model = os.getenv("LLM_MODEL", "qwen3.5:4b")
        if not model.strip() or "cloud" in model.lower():
            raise ValueError("a non-cloud local model name is required")
        base = local_base_url(os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")))
        return ModelSettings(provider, model, base, "local")
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("explicit openai provider requires OPENAI_API_KEY")
        return ModelSettings(provider, os.getenv("LLM_MODEL", "gpt-4o-mini"), "https://api.openai.com/v1", key)
    raise ValueError("LLM_PROVIDER must be ollama, local, template or openai")
