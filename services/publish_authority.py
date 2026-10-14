"""The one seam every live publication crosses.

A live post or reply needs a human-approved CapabilityGrant: one exact
action (``publish_post``), one approved resource (the draft id the human
saw), the platform as a named target and, when the grant records it, the
sha256 of the exact text that was approved. Anything else is refused and
the caller falls back to a dry run — fail toward silence.

This is the organ-local approximation of Kernel ConsequenceGate mediation
(DALEOBANKS #61/#73 on Kernel #11→#25). The shared Kernel boundary
package on main does not yet carry the gate; when it does, the gate
replaces ``authorize_publish`` at this seam and nothing else moves. It
creates no authority: grants still mint only from approved requests, and
validation still runs the ledger-chain, crisis, revocation, expiry, use,
action, resource, target and cost checks in services/capability.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

PUBLISH_ACTION = "publish_post"


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PublishDecision:
    allowed: bool
    reason: str
    grant_id: str = ""


def authorize_publish(
    *, platform: str, kind: str, content: str, metadata: Optional[Dict[str, Any]]
) -> PublishDecision:
    """Validate and consume the grant for one live publication."""
    from db.models import CapabilityGrant
    from db.session import get_db_session
    from services.capability import CapabilityError, get_capability_service

    meta = metadata or {}
    grant_id = meta.get("capability_grant_id") or ""
    draft_id = meta.get("draft_id") or ""
    if not grant_id or not draft_id:
        return PublishDecision(False, "no_capability_grant")

    digest = content_sha256(content)
    with get_db_session() as session:
        grant = session.query(CapabilityGrant).filter(lambda g: g.id == grant_id).first()
        approved = ((grant.metadata or {}).get("content_sha256") if grant else None)
        if approved and approved != digest:
            # The words differ from the words a human approved: refuse
            # before consuming a use, and ledger the refusal.
            get_capability_service()._reject(grant_id, "content_outside_approved_intent")
            return PublishDecision(False, "content_outside_approved_intent", grant_id)
        try:
            get_capability_service().validate_and_consume(
                session, grant_id, PUBLISH_ACTION, draft_id, target=platform,
            )
        except CapabilityError as exc:
            return PublishDecision(False, f"capability_rejected: {exc}", grant_id)
    return PublishDecision(True, "granted", grant_id)


__all__ = ["PUBLISH_ACTION", "PublishDecision", "authorize_publish", "content_sha256"]
