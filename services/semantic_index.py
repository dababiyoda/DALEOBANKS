"""Durable associative memory: a lightweight, offline-safe semantic index.

Lessons and other memories are embedded as hashed bag-of-words vectors and
persisted to an append-only JSONL file, so the agent's associative recall
survives restarts and database note pruning. Deliberately dependency-free:
no network calls, no embedding API, deterministic across environments. The
representation can be upgraded to learned embeddings later without changing
the interface (``add`` / ``search``).
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
    """Sparse hashed term-frequency vector, L2-normalized."""

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

    def __init__(self, path: Optional[str] = None, dimensions: int = 4096) -> None:
        self.path = path or default_index_path()
        self.dimensions = dimensions
        self._lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []
        self._vectors: List[Dict[int, float]] = []
        self._load()

    def __len__(self) -> int:
        return len(self._records)

    def add(self, text: str, meta: Optional[Dict[str, Any]] = None,
            record_id: Optional[str] = None) -> str:
        """Index a memory and persist it. Returns the record id."""

        record = {
            "id": record_id or uuid.uuid4().hex,
            "ts": datetime.now(UTC).isoformat(),
            "text": text,
            "meta": meta or {},
        }
        vector = _embed(text, self.dimensions)
        with self._lock:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
            self._records.append(record)
            self._vectors.append(vector)
        return record["id"]

    def records(self) -> List[Dict[str, Any]]:
        """All stored records in insertion order (copies)."""
        with self._lock:
            return [dict(record) for record in self._records]

    def search(self, query: str, k: int = 5,
               min_score: float = 0.05) -> List[Dict[str, Any]]:
        """Top-k most similar memories, newest first among ties."""

        query_vec = _embed(query, self.dimensions)
        if not query_vec:
            return []
        with self._lock:
            scored: List[Tuple[float, int]] = []
            for idx, vector in enumerate(self._vectors):
                score = _cosine(query_vec, vector)
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
                    self._records.append(record)
                    self._vectors.append(_embed(record.get("text", ""), self.dimensions))
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
