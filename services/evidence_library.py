"""Evidence library: verified citations become durable, reusable assets.

Every time a published piece of content passes the citation gate, the
trusted URLs it cited are recorded here with their topic and context.
Future generation recalls pre-vetted sources by topic, so the agent walks
into every proposal already holding receipts instead of hoping the LLM
invents a citable link — raising both evidence quality and the pass rate
of the citation gate over time.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.logging_utils import get_logger
from services.semantic_index import SemanticIndex

logger = get_logger(__name__)


def default_evidence_path() -> str:
    return os.getenv("EVIDENCE_LIBRARY_PATH", os.path.join("data", "evidence_library.jsonl"))


class EvidenceLibrary:
    """Durable, topic-recallable store of verified citations."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.index = SemanticIndex(path=path or default_evidence_path())
        self._seen_urls = {
            record.get("meta", {}).get("url")
            for record in self.index.records()
            if record.get("meta", {}).get("url")
        }

    def record(self, *, url: str, topic: str, context: str = "") -> Optional[str]:
        """Store a verified citation once. Returns record id or None."""
        url = (url or "").strip()
        if not url or url in self._seen_urls:
            return None
        try:
            text = f"{topic}: {context[:160]} [{url}]" if context else f"{topic} [{url}]"
            record_id = self.index.add(text, meta={
                "kind": "evidence",
                "url": url,
                "topic": topic,
            })
            self._seen_urls.add(url)
            return record_id
        except Exception as exc:
            logger.error(f"Failed to record evidence: {exc}")
            return None

    def recall(self, topic: str, k: int = 3) -> List[Dict[str, Any]]:
        """Pre-vetted sources relevant to a topic: [{url, text}, ...]."""
        try:
            return [
                {"url": hit["meta"].get("url"), "text": hit["text"]}
                for hit in self.index.search(topic, k=k)
                if hit.get("meta", {}).get("url")
            ]
        except Exception as exc:
            logger.error(f"Evidence recall failed: {exc}")
            return []

    def __len__(self) -> int:
        return len(self.index)


_SHARED_LIBRARY: Optional[EvidenceLibrary] = None


def get_evidence_library() -> EvidenceLibrary:
    global _SHARED_LIBRARY
    if _SHARED_LIBRARY is None:
        _SHARED_LIBRARY = EvidenceLibrary()
    return _SHARED_LIBRARY


def set_evidence_library(library: Optional[EvidenceLibrary]) -> None:
    """Swap the shared library (used by tests)."""
    global _SHARED_LIBRARY
    _SHARED_LIBRARY = library


__all__ = [
    "EvidenceLibrary",
    "get_evidence_library",
    "set_evidence_library",
    "default_evidence_path",
]
