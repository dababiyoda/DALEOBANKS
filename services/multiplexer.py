"""Route social posts across multiple platform adapters."""

from __future__ import annotations

import random
from typing import Any, Dict, Iterable, Optional, List

from config import get_config, subscribe_to_updates
from services.linkedin_client import LinkedInClient
from services.mastodon_client import MastodonClient
from services.social_base import BaseSocialClient, SocialPostResult
from services.logging_utils import get_logger
from services.x_client import XClient

logger = get_logger(__name__)


class _XAdapter(BaseSocialClient):
    """Adapter to expose the XClient through the common interface."""

    platform = "x"

    def __init__(
        self,
        client: Optional[XClient],
        *,
        enabled: bool,
        live: bool,
        config=None,
    ) -> None:
        super().__init__(enabled=enabled, live=live)
        self._client = client
        self._config = config or get_config()

    async def publish(
        self,
        *,
        content: str,
        kind: str = "post",
        in_reply_to: Optional[str] = None,
        quote_to: Optional[str] = None,
        intensity: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SocialPostResult:
        if not self._client:
            logger.info("X adapter missing client; using dry run")
            return await self._dry_run(kind=kind, metadata=metadata)

        metadata = metadata or {}
        if not self._config.LIVE:
            logger.info("LIVE mode disabled; skipping X publish")
            return await self._dry_run(kind=kind, metadata=metadata)

        media_ids: List[str] = []
        if metadata.get("media"):
            media_payload = metadata.get("media")
            if isinstance(media_payload, dict):
                media_payload = [media_payload]
            for item in media_payload or []:
                if not isinstance(item, dict):
                    continue
                path = item.get("path") or item.get("filepath")
                if not path:
                    continue
                media_type = item.get("type") or item.get("media_type") or "image"
                try:
                    media_id = await self._client.upload_media(
                        media_path=path,
                        media_type=str(media_type),
                    )
                except Exception as exc:  # pragma: no cover - defensive log
                    logger.warning("Failed to upload media %s: %s", path, exc)
                    media_id = None
                if media_id:
                    media_ids.append(media_id)

        if media_ids:
            metadata = dict(metadata)
            metadata["media_ids"] = list(media_ids)

        tweet_id = await self._client.create_tweet(
            content,
            quote_tweet_id=quote_to,
            in_reply_to=in_reply_to,
            media_ids=media_ids or None,
            idempotency_key=metadata.get("idempotency_key"),
        )

        if not tweet_id or tweet_id == "dry_run_tweet_id":
            return await self._dry_run(kind=kind, metadata=metadata)

        return SocialPostResult(platform=self.platform, post_id=str(tweet_id), dry_run=False, meta=metadata)


class SocialMultiplexer:
    """Decides which social platforms receive outbound content."""

    def __init__(
        self,
        *,
        config=None,
        x_client: Optional[XClient] = None,
        linkedin_client: Optional[LinkedInClient] = None,
        mastodon_client: Optional[MastodonClient] = None,
    ) -> None:
        self.config = config or get_config()
        self.mode = (self.config.PLATFORM_MODE or "broadcast").lower()
        self.weights = dict(self.config.PLATFORM_WEIGHTS)
        self._unsubscribe = subscribe_to_updates(self._on_config_update)

        # Build adapters
        self.clients: Dict[str, BaseSocialClient] = {}
        if x_client is None:
            try:
                x_client = XClient()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to instantiate XClient: %s", exc)
                x_client = None
        self.clients["x"] = _XAdapter(
            x_client,
            enabled=True,
            live=self.config.LIVE,
            config=self.config,
        )

        linkedin_client = linkedin_client or LinkedInClient(
            enabled=self.config.ENABLE_LINKEDIN,
            live=self.config.LIVE,
        )
        if linkedin_client.enabled:
            self.clients["linkedin"] = linkedin_client

        mastodon_client = mastodon_client or MastodonClient(
            enabled=self.config.ENABLE_MASTODON,
            live=self.config.LIVE,
        )
        if mastodon_client.enabled:
            self.clients["mastodon"] = mastodon_client

    def enabled_platforms(self) -> Iterable[str]:
        return self.clients.keys()

    async def publish(
        self,
        content: str,
        *,
        kind: str = "post",
        intensity: int = 1,
        in_reply_to: Optional[str] = None,
        quote_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, SocialPostResult]:
        targets = self._select_targets()
        results: Dict[str, SocialPostResult] = {}
        for name, client in targets.items():
            results[name] = await client.publish(
                content=content,
                kind=kind,
                in_reply_to=in_reply_to,
                quote_to=quote_to,
                intensity=intensity,
                metadata=metadata,
            )
        return results

    def _select_targets(self) -> Dict[str, BaseSocialClient]:
        if not self.clients:
            return {}

        available = self.clients
        if self.mode == "broadcast":
            return available

        if self.mode == "single":
            platform = max(
                available,
                key=lambda name: self.weights.get(name, 1.0),
            )
            return {platform: available[platform]}

        if self.mode == "weighted":
            total = sum(self.weights.get(name, 1.0) for name in available)
            if total <= 0:
                return available
            choice = random.random() * total
            upto = 0.0
            for name, client in available.items():
                upto += self.weights.get(name, 1.0)
                if choice <= upto:
                    return {name: client}
            # Fallback
            name = next(iter(available))
            return {name: available[name]}

        # Unknown mode -> default broadcast
        return available

    def _on_config_update(self, cfg, changes: Dict[str, Any]) -> None:
        if "LIVE" in changes:
            for client in self.clients.values():
                client.set_live(cfg.LIVE)
        if "PLATFORM_MODE" in changes:
            self.mode = (cfg.PLATFORM_MODE or "broadcast").lower()
        if "PLATFORM_WEIGHTS" in changes:
            self.weights = dict(cfg.PLATFORM_WEIGHTS)

    def __del__(self):  # pragma: no cover - defensive cleanup
        unsubscribe = getattr(self, "_unsubscribe", None)
        if callable(unsubscribe):
            try:
                unsubscribe()
            except Exception:
                pass


__all__ = ["SocialMultiplexer"]
