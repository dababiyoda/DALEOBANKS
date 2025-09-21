"""Common utilities for multi-platform social clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import uuid

from services.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SocialPostResult:
    """Normalized response from a social platform write."""

    platform: str
    post_id: str
    dry_run: bool
    meta: Optional[Dict[str, Any]] = None


def dry_run_identifier(platform: str, kind: str = "post") -> str:
    """Return a deterministic-looking identifier for dry run writes."""

    return f"{platform}:{kind}/md_dry_{uuid.uuid4().hex[:8]}"


class BaseSocialClient:
    """Interface and helpers for social network adapters."""

    platform: str = "base"

    def __init__(self, *, enabled: bool, live: bool) -> None:
        self.enabled = enabled
        self.live = live

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
        raise NotImplementedError

    async def _dry_run(
        self,
        *,
        kind: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SocialPostResult:
        post_id = dry_run_identifier(self.platform, kind)
        logger.info("DRY RUN - %s would create %s", self.platform, kind)
        return SocialPostResult(platform=self.platform, post_id=post_id, dry_run=True, meta=metadata)


__all__ = ["BaseSocialClient", "SocialPostResult", "dry_run_identifier"]
