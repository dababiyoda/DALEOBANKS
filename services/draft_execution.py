"""Execute one approved draft under one grant — the only lawful way a
specific human-approved post reaches a platform.

Minting a publish grant for a draft pins the draft's exact text (sha256)
and its opportunity packet into the grant. Execution then refuses unless
the draft is approved, its current text still hashes to the pinned value
(a draft edited after the grant is a different act), and the platform the
draft names has an adapter. The publication itself crosses the same
BaseSocialClient.publish seam as everything else, so the grant is
validated and consumed there — this module never bypasses it. Every
attempt is recorded as an ``executed_draft_publish`` ledger event so the
DecisionEpisode shows the executed-action stage, dry run or live.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from db.models import CapabilityGrant, MediaAssetDraft
from services.ledger import get_ledger
from services.publish_authority import PUBLISH_ACTION, content_sha256


class DraftExecutionError(ValueError):
    """The draft or grant cannot lawfully be executed. Nothing was sent."""


def draft_text(draft: MediaAssetDraft) -> str:
    return draft.draft_text or draft.caption or ""


def grant_metadata_for(session: Any, action_type: str, resource: str) -> Dict[str, Any]:
    """Pin a draft's exact text and lineage into a publish grant at mint."""
    if action_type != PUBLISH_ACTION:
        return {}
    draft = session.query(MediaAssetDraft).filter(lambda d: d.id == resource).first()
    if draft is None:
        return {}
    return {
        "content_sha256": content_sha256(draft_text(draft)),
        "opportunity_packet_id": draft.source_opportunity_packet_id or "",
        "draft_id": draft.id,
    }


async def execute_approved_draft(
    session: Any, draft_id: str, grant_id: str, *, multiplexer: Optional[Any] = None,
) -> Dict[str, Any]:
    draft = session.query(MediaAssetDraft).filter(lambda d: d.id == draft_id).first()
    if draft is None:
        raise DraftExecutionError("draft not found")
    if draft.approval_status != "approved":
        raise DraftExecutionError(f"draft is '{draft.approval_status}', not approved")
    grant = session.query(CapabilityGrant).filter(lambda g: g.id == grant_id).first()
    if grant is None or grant.action_type != PUBLISH_ACTION or grant.resource != draft_id:
        raise DraftExecutionError("grant does not authorize publishing this draft")
    text = draft_text(draft)
    pinned = (grant.metadata or {}).get("content_sha256")
    if not pinned:
        raise DraftExecutionError("grant does not pin the approved text")
    if pinned != content_sha256(text):
        raise DraftExecutionError("draft text changed after the grant was minted")
    if not text.strip():
        raise DraftExecutionError("draft has no text to publish")

    if multiplexer is None:
        import runner
        multiplexer = runner.multiplexer
    client = multiplexer.clients.get(draft.platform)
    if client is None:
        raise DraftExecutionError(f"no adapter for platform '{draft.platform}'")

    result = await client.publish(
        content=text, kind="post",
        metadata={"capability_grant_id": grant_id, "draft_id": draft_id,
                  "account_lane": draft.account_lane},
    )
    record = {
        "draft_id": draft_id, "capability_grant_id": grant_id,
        "opportunity_packet_id": draft.source_opportunity_packet_id or "",
        "platform": result.platform, "post_id": result.post_id,
        "dry_run": bool(result.dry_run), "content_sha256": content_sha256(text),
    }
    get_ledger().record("executed_draft_publish", record)
    return record


__all__ = ["DraftExecutionError", "execute_approved_draft", "grant_metadata_for", "draft_text"]
