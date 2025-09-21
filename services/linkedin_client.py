"""Minimal LinkedIn adapter used by the social multiplexer."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.logging_utils import get_logger
from services.social_base import BaseSocialClient, SocialPostResult

logger = get_logger(__name__)


class LinkedInClient(BaseSocialClient):
    """Stub LinkedIn client that always operates in dry-run mode."""

    platform = "linkedin"

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
            logger.info("LinkedIn disabled; skipping publish")
            return await self._dry_run(kind=kind, metadata=metadata)

        # Full LinkedIn API integration is out of scope for tests; always dry run.
        logger.info("LinkedIn adapter running in dry-run mode (no API integration)")
        return await self._dry_run(kind=kind, metadata=metadata)


__all__ = ["LinkedInClient"]
