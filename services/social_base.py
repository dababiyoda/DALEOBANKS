"""Common utilities for multi-platform social clients.

``BaseSocialClient.publish`` is a template method: it runs the safety gate
(ledger record, kill switch, rate governor) and then delegates to the
subclass's ``_publish_impl``. Any new platform adapter is therefore logged,
kill-switched, and rate-governed the moment it inherits the base class —
safety is inherited, never re-implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import uuid

from services.ledger import get_kill_switch, get_ledger, get_rate_governor
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

    def set_live(self, live: bool) -> None:
        """Update the live flag for the adapter."""

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
        """Gated publish: ledger every attempt, honor the kill switch and
        rate governor, then delegate to the platform's ``_publish_impl``."""

        ledger = get_ledger()
        ledger.record(
            "publish_attempt",
            {
                "platform": self.platform,
                "kind": kind,
                "intensity": intensity,
                "live": self.live,
                "chars": len(content),
            },
        )

        if not get_kill_switch().armed:
            # Fail-safe to silence: nothing goes live while disarmed, even if
            # a subclass forgets its own LIVE check.
            result = await self._dry_run(kind=kind, metadata=metadata)
        elif not get_rate_governor().allow(self.platform):
            ledger.record(
                "publish_gated",
                {"platform": self.platform, "kind": kind, "reason": "rate_governor"},
            )
            logger.warning("Rate governor blocked live %s on %s", kind, self.platform)
            result = await self._dry_run(kind=kind, metadata=metadata)
        else:
            result = await self._publish_impl(
                content=content,
                kind=kind,
                in_reply_to=in_reply_to,
                quote_to=quote_to,
                intensity=intensity,
                metadata=metadata,
            )

        ledger.record(
            "publish_result",
            {
                "platform": result.platform,
                "kind": kind,
                "post_id": result.post_id,
                "dry_run": result.dry_run,
            },
        )
        return result

    async def _publish_impl(
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
