"""Durable associative memory: a lightweight, offline-safe semantic index.

Memories are embedded through the provider layer in
``services/embeddings.py`` (hash bag-of-words by default; optionally OpenAI
embeddings with per-call hash fallback) and persisted to an append-only
JSONL file, so the agent's associative recall survives restarts and database
note pruning. The ``add`` / ``search`` interface is synchronous and
unchanged regardless of provider.

Every record carries an embedding tag (provider/model/dim); cosine
similarity is only computed within matching tags. A hash vector is always
kept alongside provider vectors, so recall keeps working even if a provider
disappears (key removed, offline) after records were written with it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Tuple

from services.embeddings import (
    EmbeddingService, HASH_DIMENSIONS, Tag, Vector, get_embedding_service,
    hash_tag, tag_key,
)
from services.logging_utils import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9']+")

# Common English stopwords; kept short on purpose - the goal is signal, not
# linguistic perfection.
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on "
    "or that the their this to was were will with your you we our".split()
)


def default_index_path() -> str:
    return os.getenv("SEMANTIC_INDEX_PATH", os.path.join("data", "semantic_index.jsonl"))


def _tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _embed(text: str, dimensions: int) -> Dict[int, float]:
    """Sparse hashed term-frequency vector, L2-normalized.

    The bedrock representation: deterministic, offline, dependency-free.
    Also used directly by the consolidation service for clustering."""

    counts: Dict[int, float] = {}
    for token in _tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        counts[slot] = counts.get(slot, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm == 0:
        return {}
    return {k: v / norm for k, v in counts.items()}


def _cosine(a: Dict[int, float], b: Dict[int, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(value * b.get(slot, 0.0) for slot, value in a.items())


class SemanticIndex:
    """Append-only persisted index with cosine-similarity search."""

    def __init__(
        self,
        path: Optional[str] = None,
        dimensions: int = HASH_DIMENSIONS,
        embeddings: Optional[EmbeddingService] = None,
    ) -> None:
        self.path = path or default_index_path()
        self.dimensions = dimensions
        if embeddings is not None:
            self.embeddings = embeddings
        elif dimensions == HASH_DIMENSIONS:
            self.embeddings = get_embedding_service()
        else:
            self.embeddings = EmbeddingService(dimensions=dimensions)
        self._lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []
        # Per record: {tag_key: vector}. The hash vector is always present;
        # a provider vector is present when the record was written with one.
        self._vectors: List[Dict[Tuple[str, Any], Vector]] = []
        self._load()

    def __len__(self) -> int:
        return len(self._records)

    @property
    def _hash_key(self) -> Tuple[str, Any]:
        return tag_key(hash_tag(self.dimensions))

    def _vector_map(self, text: str, vector: Optional[Vector], tag: Optional[Tag]) -> Dict[Tuple[str, Any], Vector]:
        vmap: Dict[Tuple[str, Any], Vector] = {}
        if vector is not None and tag is not None:
            vmap[tag_key(tag)] = vector
        if self._hash_key not in vmap:
            vmap[self._hash_key] = _embed(text, self.dimensions)
        return vmap

    def add(self, text: str, meta: Optional[Dict[str, Any]] = None,
            record_id: Optional[str] = None) -> str:
        """Index a memory and persist it. Returns the record id."""

        vector, tag = self.embeddings.embed(text)
        record = {
            "id": record_id or uuid.uuid4().hex,
            "ts": datetime.now(UTC).isoformat(),
            "text": text,
            "meta": meta or {},
            "emb": tag,
        }
        if tag.get("provider") != "hash":
            # Provider vectors are expensive to recompute — persist them so
            # reload never re-calls the API.
            record["vec"] = [[i, round(v, 7)] for i, v in vector.items()]
        with self._lock:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
            stored = {k: v for k, v in record.items() if k != "vec"}
            self._records.append(stored)
            self._vectors.append(self._vector_map(text, vector, tag))
        return record["id"]

    def records(self) -> List[Dict[str, Any]]:
        """All stored records in insertion order (copies)."""
        with self._lock:
            return [dict(record) for record in self._records]

    def search(self, query: str, k: int = 5,
               min_score: float = 0.05) -> List[Dict[str, Any]]:
        """Top-k most similar memories, newest first among ties."""

        query_vec, query_tag = self.embeddings.embed(query)
        queries: Dict[Tuple[str, Any], Vector] = {tag_key(query_tag): query_vec}
        if self._hash_key not in queries:
            queries[self._hash_key] = _embed(query, self.dimensions)
        queries = {key: vec for key, vec in queries.items() if vec}
        if not queries:
            return []
        with self._lock:
            scored: List[Tuple[float, int]] = []
            for idx, vmap in enumerate(self._vectors):
                score = max(
                    (_cosine(qvec, vmap[key]) for key, qvec in queries.items() if key in vmap),
                    default=0.0,
                )
                if score >= min_score:
                    scored.append((score, idx))
        scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
        results = []
        for score, idx in scored[:k]:
            record = dict(self._records[idx])
            record["score"] = round(score, 4)
            results.append(record)
        return results

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping corrupt semantic index line")
                        continue
                    vector: Optional[Vector] = None
                    tag = record.get("emb")
                    raw_vec = record.pop("vec", None)
                    if raw_vec and tag and tag.get("provider") != "hash":
                        try:
                            vector = {int(i): float(v) for i, v in raw_vec}
                        except (TypeError, ValueError):
                            vector = None
                    self._records.append(record)
                    self._vectors.append(
                        self._vector_map(record.get("text", ""), vector, tag)
                    )
            logger.info(f"Semantic index loaded with {len(self._records)} memories")
        except OSError as exc:
            logger.error(f"Failed to load semantic index: {exc}")


_SHARED_INDEX: Optional[SemanticIndex] = None
_SHARED_INDEX_LOCK = threading.Lock()


def get_semantic_index() -> SemanticIndex:
    global _SHARED_INDEX
    with _SHARED_INDEX_LOCK:
        if _SHARED_INDEX is None:
            _SHARED_INDEX = SemanticIndex()
        return _SHARED_INDEX


def set_semantic_index(index: Optional[SemanticIndex]) -> None:
    """Swap the shared index (used by tests)."""

    global _SHARED_INDEX
    with _SHARED_INDEX_LOCK:
        _SHARED_INDEX = index


__all__ = [
    "SemanticIndex",
    "default_index_path",
    "get_semantic_index",
    "set_semantic_index",
]
