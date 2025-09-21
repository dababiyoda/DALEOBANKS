"""Perception loop that keeps lightweight situational awareness."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Tuple

try:  # pragma: no cover - import guard for environments without PyYAML
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from services.logging_utils import get_logger
from db.models import SensedEvent

logger = get_logger(__name__)


class PerceptionService:
    """Loads seed data and produces synthetic perception counts."""

    def __init__(
        self,
        influencers_path: Path | str = Path("data/seed_influencers.yaml"),
        keywords_path: Path | str = Path("data/seed_keywords.yaml"),
    ) -> None:
        self.influencers_path = Path(influencers_path)
        self.keywords_path = Path(keywords_path)
        self._voices = self._load_influencers()
        self._keywords = self._load_keywords()

    def _load_influencers(self) -> List[Dict[str, object]]:
        if yaml is None or not self.influencers_path.exists():
            return []
        data = yaml.safe_load(self.influencers_path.read_text()) or {}
        voices: List[Dict[str, object]] = []
        for group in data.values():
            if isinstance(group, list):
                voices.extend([voice for voice in group if isinstance(voice, dict)])
        return voices

    def _load_keywords(self) -> List[str]:
        if yaml is None or not self.keywords_path.exists():
            return []
        data = yaml.safe_load(self.keywords_path.read_text()) or {}
        keywords: List[str] = []
        for bucket in data.values():
            if isinstance(bucket, list):
                keywords.extend(str(word) for word in bucket)
        return keywords

    def _summarize(self) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
        voices = len(self._voices)
        trend_topics = sorted({topic for voice in self._voices for topic in voice.get("topics", [])})
        trends = len(trend_topics)
        keywords = len(self._keywords)

        counts = {
            "voices": voices,
            "trends": trends,
            "keywords": keywords,
        }
        payload = {
            "top_voices": [voice.get("username") for voice in self._voices[:5]],
            "trend_topics": trend_topics[:5],
            "keywords": self._keywords[:10],
        }
        return counts, payload

    def ingest(self, session) -> int:
        counts, payload = self._summarize()
        # Simulate variability so the scheduler has movement without API calls.
        variability = random.randint(0, max(1, counts["voices"]))
        counts["signals"] = variability

        event = SensedEvent(
            source="perception",
            kind="ingest",
            payload=payload,
            counts=counts,
        )
        session.add(event)
        session.commit()

        logger.info("perception_ingested", extra={"counts": counts})
        return sum(counts.values())


__all__ = ["PerceptionService"]
