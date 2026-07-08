"""Embedding provider layer for the semantic memory systems.

`SemanticIndex` (and everything built on it: lesson memory, the world model,
evidence recall) asks this layer for vectors instead of hardwiring a
representation. The `add`/`search` API stays synchronous and unchanged.

Provider modes (env `EMBEDDINGS_PROVIDER`, default ``hash``):

- ``hash``    the existing hashed bag-of-words vectors — deterministic,
              offline, dependency-free. Always available.
- ``openai``  OpenAI embeddings (env `EMBEDDINGS_MODEL`, default
              ``text-embedding-3-small``) via a plain synchronous HTTPS
              call; every failure falls back to ``hash`` for that call, so
              memory never stops working.
- ``auto``    ``openai`` when `OPENAI_API_KEY` is set, else ``hash``.
- ``shadow``  serves ``hash`` (behavior unchanged) while also exercising the
              OpenAI path and counting outcomes in :attr:`shadow_stats` — a
              safe observation window before switching.

Vectors are sparse ``{slot: weight}`` dicts in both representations, each
tagged with ``{"provider", "model", "dim"}``. Cosine similarity is only
meaningful within one tag, so the index compares like with like.
"""

from __future__ import annotations

import json
import math
import os
import threading
import urllib.request
from typing import Any, Dict, Optional, Tuple

from services.logging_utils import get_logger

logger = get_logger(__name__)

Vector = Dict[int, float]
Tag = Dict[str, Any]

HASH_DIMENSIONS = 4096


def hash_tag(dimensions: int = HASH_DIMENSIONS) -> Tag:
    return {"provider": "hash", "dim": dimensions}


def tag_key(tag: Tag) -> Tuple[str, Any]:
    return (str(tag.get("provider", "hash")), tag.get("dim"))


class EmbeddingService:
    """Resolves the configured provider per call, with hash as bedrock."""

    def __init__(self, mode: Optional[str] = None, dimensions: int = HASH_DIMENSIONS) -> None:
        self._mode = mode
        self.dimensions = dimensions
        self.shadow_stats = {"ok": 0, "failed": 0}
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return (self._mode or os.getenv("EMBEDDINGS_PROVIDER", "hash")).lower()

    @property
    def model(self) -> str:
        return os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")

    def hash_embed(self, text: str) -> Vector:
        # The bedrock representation lives in semantic_index (consolidation
        # imports it directly); imported lazily to avoid a module cycle.
        from services.semantic_index import _embed
        return _embed(text, self.dimensions)

    def embed(self, text: str) -> Tuple[Vector, Tag]:
        """Vector + tag for ``text`` under the configured mode. Never raises;
        never returns an unusable vector — hash is the universal fallback."""
        mode = self.mode
        if mode == "openai" or (mode == "auto" and os.getenv("OPENAI_API_KEY")):
            dense = self._openai_embed(text)
            if dense is not None:
                return dense, {"provider": "openai", "model": self.model, "dim": len(dense)}
            logger.warning("OpenAI embedding failed; falling back to hash for this call")
        elif mode == "shadow":
            dense = self._openai_embed(text)
            with self._lock:
                self.shadow_stats["ok" if dense is not None else "failed"] += 1
        return self.hash_embed(text), hash_tag(self.dimensions)

    def _openai_embed(self, text: str) -> Optional[Vector]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            payload = json.dumps({"model": self.model, "input": text[:8000]}).encode()
            request = urllib.request.Request(
                os.getenv("EMBEDDINGS_URL", "https://api.openai.com/v1/embeddings"),
                data=payload,
                method="POST",
            )
            request.add_header("Authorization", f"Bearer {api_key}")
            request.add_header("Content-Type", "application/json")
            timeout = float(os.getenv("EMBEDDINGS_TIMEOUT", "10"))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.load(response)
            values = body["data"][0]["embedding"]
            norm = math.sqrt(sum(v * v for v in values))
            if norm == 0:
                return None
            return {i: v / norm for i, v in enumerate(values)}
        except Exception as exc:
            logger.error(f"OpenAI embedding call failed: {exc}")
            return None


_SHARED_SERVICE: Optional[EmbeddingService] = None
_SHARED_LOCK = threading.Lock()


def get_embedding_service() -> EmbeddingService:
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        if _SHARED_SERVICE is None:
            _SHARED_SERVICE = EmbeddingService()
        return _SHARED_SERVICE


def set_embedding_service(service: Optional[EmbeddingService]) -> None:
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        _SHARED_SERVICE = service


__all__ = [
    "EmbeddingService", "get_embedding_service", "set_embedding_service",
    "hash_tag", "tag_key", "Vector", "Tag", "HASH_DIMENSIONS",
]
