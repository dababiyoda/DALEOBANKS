"""Minimal Mastodon adapter used by the social multiplexer."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.logging_utils import get_logger
from services.social_base import BaseSocialClient, SocialPostResult

logger = get_logger(__name__)


class MastodonClient(BaseSocialClient):
    """Stub Mastodon client returning dry-run identifiers."""

    platform = "mastodon"

    def __init__(self, *, enabled: bool, live: bool) -> None:
        super().__init__(enabled=enabled, live=live)

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
        if not self.enabled:
            logger.info("Mastodon disabled; skipping publish")
            return await self._dry_run(kind=kind, metadata=metadata)

        # Mastodon integration is not implemented; simulate success deterministically.
        logger.info("Mastodon adapter running in dry-run mode (no API integration)")
        return await self._dry_run(kind=kind, metadata=metadata)


__all__ = ["MastodonClient"]
