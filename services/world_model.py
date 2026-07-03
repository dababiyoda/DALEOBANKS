"""Self-authored world model: durable, associative memory of the environment.

Perception scans are ephemeral - each cycle's mentions, timeline posts, and
trends are processed and dropped. The world model keeps them: every observed
entity and event is embedded into its own semantic index (separate file from
the lesson index), so the planner and generator can ask "what do I know
about X" and get answers grounded in things the agent actually saw, with
timestamps and sources.

Observations are just data. Nothing in the world model can direct action;
it only informs generation context, per the constitution's inbound-content
invariant.
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from services.logging_utils import get_logger
from services.semantic_index import SemanticIndex

logger = get_logger(__name__)


def default_world_model_path() -> str:
    return os.getenv("WORLD_MODEL_PATH", os.path.join("data", "world_model.jsonl"))


class WorldModel:
    """Embedded, durable records of observed entities and events."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.index = SemanticIndex(path=path or default_world_model_path())

    def observe(
        self,
        *,
        kind: str,
        summary: str,
        entity: Optional[str] = None,
        source: str = "x",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Record one observation. Returns the record id (None on failure)."""
        summary = (summary or "").strip()
        if not summary:
            return None
        try:
            record_meta = {
                "kind": kind,
                "entity": entity,
                "source": source,
                "observed_at": datetime.now(UTC).isoformat(),
                **(meta or {}),
            }
            text = f"{entity}: {summary}" if entity else summary
            return self.index.add(text, meta=record_meta)
        except Exception as exc:
            logger.error(f"World model observation failed: {exc}")
            return None

    def observe_perception(self, payload: Dict[str, Any]) -> int:
        """Fold one perception payload (mentions/timeline/trends) in."""
        observed = 0
        x_payload = payload.get("x") or {}

        for mention in x_payload.get("mentions", []) or []:
            if not isinstance(mention, dict):
                continue
            if self.observe(
                kind="mention",
                entity=mention.get("username"),
                summary=str(mention.get("text", ""))[:280],
                meta={"post_id": mention.get("id")},
            ):
                observed += 1

        for post in x_payload.get("home_timeline", []) or []:
            if not isinstance(post, dict):
                continue
            if self.observe(
                kind="timeline_post",
                entity=post.get("username") or post.get("author_id"),
                summary=str(post.get("text", ""))[:280],
                meta={"post_id": post.get("id")},
            ):
                observed += 1

        for trend in x_payload.get("trending_topics", []) or []:
            summary = trend.get("name") if isinstance(trend, dict) else str(trend)
            if self.observe(kind="trend", summary=str(summary)[:120]):
                observed += 1

        return observed

    def recall(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """What does the agent know about this, from direct observation?"""
        try:
            return self.index.search(query, k=k)
        except Exception as exc:
            logger.error(f"World model recall failed: {exc}")
            return []

    def __len__(self) -> int:
        return len(self.index)


_SHARED_WORLD_MODEL: Optional[WorldModel] = None


def get_world_model() -> WorldModel:
    global _SHARED_WORLD_MODEL
    if _SHARED_WORLD_MODEL is None:
        _SHARED_WORLD_MODEL = WorldModel()
    return _SHARED_WORLD_MODEL


def set_world_model(model: Optional[WorldModel]) -> None:
    """Swap the shared world model (used by tests)."""
    global _SHARED_WORLD_MODEL
    _SHARED_WORLD_MODEL = model


__all__ = ["WorldModel", "get_world_model", "set_world_model", "default_world_model_path"]
