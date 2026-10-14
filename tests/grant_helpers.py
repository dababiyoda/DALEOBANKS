"""Mint a real publish grant the way production must: an ApprovalRequest
naming the draft, a human YES, then a grant narrower than the approval."""

from db.session import get_db_session
from services.capability import get_capability_service
from services.ledger import get_kill_switch, get_ledger
from services.operator_line import OperatorLine
from services.publish_authority import PUBLISH_ACTION, content_sha256


def mint_publish_grant(platform: str, content: str, *, draft_id: str = "draft-1",
                       uses: int = 1, bind_content: bool = True):
    line = OperatorLine(ledger=get_ledger(), kill_switch=get_kill_switch())
    with get_db_session() as session:
        request = line.request_approval(
            session, kind="publish", summary=f"Publish {draft_id} on {platform}",
            payload={"draft_id": draft_id, "action_type": PUBLISH_ACTION},
        )
        line.handle_command(session, f"YES {request.code}")
        grant = get_capability_service().mint_from_approval(
            session, request.id, PUBLISH_ACTION, f"publish {draft_id}", draft_id,
            named_targets=[platform], maximum_uses=uses,
            metadata={"content_sha256": content_sha256(content)} if bind_content else {},
        )
    return grant


def grant_metadata(grant, draft_id: str = "draft-1", **extra):
    return {"capability_grant_id": grant.id, "draft_id": draft_id, **extra}
