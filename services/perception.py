"""Perception loop that keeps lightweight situational awareness."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

try:  # pragma: no cover - import guard for environments without PyYAML
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from services.logging_utils import get_logger
from db.models import SensedEvent

PerceptionSource = Awaitable[Dict[str, Any]] | Callable[[], Awaitable[Dict[str, Any]]] | Callable[[], Dict[str, Any]]

logger = get_logger(__name__)


class PerceptionService:
    """Loads seed data and produces synthetic perception counts."""

    def __init__(
        self,
        influencers_path: Path | str = Path("data/seed_influencers.yaml"),
        keywords_path: Path | str = Path("data/seed_keywords.yaml"),
        *,
        x_client: Any | None = None,
        limits: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.influencers_path = Path(influencers_path)
        self.keywords_path = Path(keywords_path)
        self._x_client = x_client
        self._voices = self._load_influencers()
        self._keywords = self._load_keywords()
        self._limits: Dict[str, int] = {
            "mentions": 25,
            "timeline": 25,
            "trends": 10,
            "keywords": 10,
            "voices": 5,
        }
        if limits:
            for key, value in limits.items():
                if isinstance(value, int) and value > 0:
                    self._limits[key] = value
        self._last_state: Dict[str, Any] = {}
        self._last_payload: Dict[str, Any] = {}
        self._last_counts: Dict[str, int] = {}

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

    def get_priority_accounts(
        self,
        *,
        min_authority: float = 0.75,
        max_count: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return high-authority influencer accounts suitable for outreach."""

        prioritized: List[Dict[str, Any]] = []
        for voice in self._voices:
            if not isinstance(voice, Mapping):
                continue
            authority = float(voice.get("authority_weight", 0.0))
            if authority < min_authority:
                continue
            username = voice.get("username")
            if not username:
                continue
            entry = dict(voice)
            entry.setdefault(
                "id",
                entry.get("user_id") or entry.get("id") or abs(hash(username)) % 10_000_000,
            )
            prioritized.append(entry)

        prioritized.sort(
            key=lambda item: (
                float(item.get("authority_weight", 0.0)),
                int(item.get("follower_count", 0)),
            ),
            reverse=True,
        )
        return prioritized[:max_count]

    async def ingest(
        self,
        session,
        *,
        x_client: Any | None = None,
        since_id: str | None = None,
        timeline_token: str | None = None,
        limits: Optional[Mapping[str, int]] = None,
        platform_sources: Optional[Mapping[str, PerceptionSource]] = None,
    ) -> int:
        """Collect perception signals and persist them as a ``SensedEvent``.

        Args:
            session: Database session used for persistence.
            x_client: Optional X/Twitter client used to fetch real signals.
            since_id: Cursor for mention pagination.
            timeline_token: Cursor for the home timeline pagination.
            limits: Optional overrides for per-endpoint fetch limits.
            platform_sources: Additional asynchronous fetchers keyed by
                platform name to extend perception beyond X.

        Returns:
            The total number of signals captured in this ingest.
        """

        limit_config = dict(self._limits)
        if limits:
            for key, value in limits.items():
                if isinstance(value, int) and value > 0:
                    limit_config[key] = value

        client = x_client or self._x_client

        counts: Dict[str, int] = {"voices": len(self._voices), "keywords": len(self._keywords)}
        payload: Dict[str, Any] = {
            "whitelisted_voices": self._voice_payload(),
            "keywords": self._keywords[: limit_config.get("keywords", 10)],
        }

        x_payload = {
            "mentions": [],
            "home_timeline": [],
            "trending_topics": [],
            "voices": {},
            "meta": {},
        }
        new_state: Dict[str, Any] = {}

        if client is not None:
            voice_state: Dict[str, Any] = {}
            previous_voice_state = self._last_state.get("x_voice_cursors")
            if isinstance(previous_voice_state, Mapping):
                voice_state = dict(previous_voice_state)

            mentions = await self._fetch_mentions(client, since_id=since_id, limit=limit_config["mentions"])
            timeline = await self._fetch_timeline(
                client,
                limit=limit_config["timeline"],
                pagination_token=timeline_token,
            )
            trends = await self._fetch_trends(client, limit=limit_config["trends"])
            voice_updates, voice_cursors = await self._fetch_voice_activity(
                client,
                limit=limit_config["voices"],
                state=voice_state,
            )

            x_payload.update(
                {
                    "mentions": mentions,
                    "home_timeline": timeline.get("items", []),
                    "trending_topics": trends,
                    "voices": voice_updates,
                    "meta": {k: v for k, v in timeline.items() if k != "items"},
                }
            )

            counts["x_mentions"] = len(mentions)
            counts["x_timeline"] = len(x_payload["home_timeline"])
            counts["x_trends"] = len(trends)
            counts["x_voice_updates"] = sum(
                len(info.get("posts", []))
                for info in voice_updates.values()
                if isinstance(info, Mapping)
            )

            latest_id = self._latest_id(mentions, fallback=since_id)
            if latest_id:
                new_state["x_mentions_since_id"] = latest_id
            if timeline.get("next_token"):
                new_state["x_timeline_token"] = timeline["next_token"]
            elif "x_timeline_token" in self._last_state:
                # Explicitly clear stale pagination tokens when exhausted.
                new_state["x_timeline_token"] = None
            if voice_cursors is not None:
                new_state["x_voice_cursors"] = voice_cursors
            elif "x_voice_cursors" in self._last_state:
                new_state["x_voice_cursors"] = None
        else:
            counts["x_mentions"] = 0
            counts["x_timeline"] = 0
            counts["x_trends"] = 0
            counts["x_voice_updates"] = 0

        payload["x"] = x_payload

        if platform_sources:
            platform_payloads = await self._resolve_platform_sources(platform_sources)
            if platform_payloads:
                payload.setdefault("platforms", {}).update(platform_payloads)
                for name, data in platform_payloads.items():
                    counts[f"{name}_signals"] = self._count_items(data)

        total_signals = sum(value for key, value in counts.items() if key != "signals")
        counts["signals"] = total_signals

        event = SensedEvent(
            source="perception",
            kind="ingest",
            payload=payload,
            counts=counts,
        )
        session.add(event)
        session.commit()

        self._last_payload = deepcopy(payload)
        self._last_counts = dict(counts)

        updated_state = dict(self._last_state)
        for key, value in new_state.items():
            if value is None:
                updated_state.pop(key, None)
            else:
                updated_state[key] = value
        self._last_state = updated_state
        logger.info("perception_ingested", extra={"counts": counts})
        return total_signals

    async def _fetch_mentions(self, client: Any, *, since_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        try:
            result = await client.get_mentions(since_id=since_id, max_results=limit)
            if isinstance(result, list):
                return result
            # Allow client implementations that return dict wrappers.
            if isinstance(result, Mapping) and "items" in result:
                return list(result.get("items", []))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("perception_mentions_error", extra={"error": str(exc)})
        return []

    async def _fetch_timeline(
        self,
        client: Any,
        *,
        limit: int,
        pagination_token: Optional[str],
    ) -> Dict[str, Any]:
        try:
            result = await client.get_home_timeline(limit=limit, pagination_token=pagination_token)
            if isinstance(result, Mapping):
                data: Dict[str, Any] = {
                    "items": list(result.get("items", [])),
                    "next_token": result.get("next_token"),
                }
                if "rate_limit" in result:
                    data["rate_limit"] = result["rate_limit"]
                return data
            if isinstance(result, list):
                return {"items": result}
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("perception_timeline_error", extra={"error": str(exc)})
        return {"items": []}

    async def _fetch_trends(self, client: Any, *, limit: int) -> List[Dict[str, Any]]:
        try:
            result = await client.get_trending_topics(limit=limit)
            if isinstance(result, list):
                return result
            if isinstance(result, Mapping) and "topics" in result:
                topics = result.get("topics", [])
                if isinstance(topics, list):
                    return topics
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("perception_trends_error", extra={"error": str(exc)})
        return []

    async def _fetch_voice_activity(
        self,
        client: Any,
        *,
        limit: int,
        state: Mapping[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, str]]]:
        voice_payload: Dict[str, Dict[str, Any]] = {}
        next_cursors: Dict[str, str] = {}

        for voice in self._voices:
            username = voice.get("username")
            if not isinstance(username, str) or not username:
                continue

            pagination_token: Optional[str] = None
            if isinstance(state, Mapping):
                token = state.get(username)
                if isinstance(token, str) and token:
                    pagination_token = token

            try:
                result = await client.get_user_tweets(
                    username=username,
                    limit=limit,
                    pagination_token=pagination_token,
                )
            except AttributeError:
                logger.debug(
                    "perception_voice_fetch_missing_api",
                    extra={"username": username},
                )
                break
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(
                    "perception_voice_error",
                    extra={"username": username, "error": str(exc)},
                )
                continue

            posts: List[Dict[str, Any]] = []
            meta: Dict[str, Any] = {}
            next_token: Optional[str] = None

            if isinstance(result, list):
                posts = list(result)[:limit]
            elif isinstance(result, Mapping):
                if "items" in result and isinstance(result.get("items"), list):
                    posts = list(result.get("items", []))[:limit]
                elif "tweets" in result and isinstance(result.get("tweets"), list):
                    posts = list(result.get("tweets", []))[:limit]
                elif "data" in result and isinstance(result.get("data"), list):
                    posts = list(result.get("data", []))[:limit]

                if "meta" in result and isinstance(result["meta"], Mapping):
                    meta = dict(result["meta"])
                    next_token = meta.get("next_token") or meta.get("next")
                if next_token is None:
                    token_value = result.get("next_token") or result.get("next")
                    if isinstance(token_value, str) and token_value:
                        next_token = token_value
                if "rate_limit" in result and isinstance(result["rate_limit"], Mapping):
                    meta.setdefault("rate_limit", result["rate_limit"])
            else:
                posts = []

            voice_entry: Dict[str, Any] = {"posts": posts}
            if meta:
                voice_entry["meta"] = meta
            voice_payload[username] = voice_entry

            if isinstance(next_token, str) and next_token:
                next_cursors[username] = next_token

        if not next_cursors:
            return voice_payload, None

        return voice_payload, next_cursors

    async def _resolve_platform_sources(
        self,
        platform_sources: Mapping[str, Any],
    ) -> Dict[str, Any]:
        payloads: Dict[str, Any] = {}
        for name, fetcher in platform_sources.items():
            try:
                result = fetcher
                if callable(fetcher):
                    result = fetcher()
                if asyncio.iscoroutine(result):
                    result = await result
                payloads[name] = result
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("perception_platform_error", extra={"platform": name, "error": str(exc)})
        return payloads

    def _count_items(self, data: Any) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, Mapping):
            total = 0
            for value in data.values():
                if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
                    total += len(list(value))
                elif isinstance(value, list):
                    total += len(value)
            return total
        return 0

    def _latest_id(self, items: Iterable[Mapping[str, Any]], *, fallback: Optional[str]) -> Optional[str]:
        candidate = fallback
        for item in items:
            value = item.get("id")
            if value is None:
                continue
            text = str(value)
            if candidate is None:
                candidate = text
                continue
            if text.isdigit() and candidate.isdigit():
                if int(text) > int(candidate):
                    candidate = text
            else:
                if text > candidate:
                    candidate = text
        return candidate

    def _voice_payload(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        cap = limit or len(self._voices)
        voices: List[Dict[str, Any]] = []
        for voice in self._voices[:cap]:
            voices.append(
                {
                    "username": voice.get("username"),
                    "topics": voice.get("topics", []),
                    "score": voice.get("score"),
                }
            )
        return voices

    @property
    def last_state(self) -> Dict[str, Any]:
        return dict(self._last_state)

    @property
    def last_payload(self) -> Dict[str, Any]:
        return deepcopy(self._last_payload)

    @property
    def last_counts(self) -> Dict[str, int]:
        return dict(self._last_counts)


__all__ = ["PerceptionService"]
