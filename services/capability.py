"""Capability-based authority: narrow, expiring, revocable permissions.

A CapabilityGrant is minted only from an approved ApprovalRequest and
authorizes one exact action against one exact resource, a bounded number
of times, inside a bounded window. Validation happens at execution time,
not only at approval time; expired, revoked, mismatched, exhausted, or
replayed grants fail closed, and a broken decision-ledger chain disarms
consumption entirely. Every lifecycle event is ledgered.

This module authorizes nothing by itself — it verifies that a human did.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, UTC
from typing import Any, Dict, List, Optional

from db.models import ApprovalRequest, CapabilityGrant
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)


class CapabilityError(PermissionError):
    """A grant failed validation. Execution must not proceed."""


def _now() -> datetime:
    return datetime.now(UTC)


def default_ttl_hours() -> int:
    try:
        return int(os.getenv("CAPABILITY_TTL_HOURS", "72"))
    except ValueError:
        return 72


class CapabilityService:
    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    # ------------------------------------------------------------------ #
    # Minting: only from a human-approved request
    # ------------------------------------------------------------------ #
    def mint_from_approval(
        self,
        session: Any,
        approval_request_id: str,
        action_type: str,
        exact_action: str,
        resource: str,
        *,
        approver_identity: str = "admin",
        requester_identity: str = "daleobanks",
        account_lane_id: str = "",
        named_targets: Optional[List[str]] = None,
        max_cost: float = 0.0,
        maximum_uses: int = 1,
        ttl_hours: Optional[int] = None,
        evidence_refs: Optional[List[str]] = None,
        rollback_note: str = "",
        trace_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CapabilityGrant:
        approval = session.query(ApprovalRequest).filter(
            lambda a: a.id == approval_request_id
        ).first()
        if approval is None:
            raise CapabilityError("unknown approval request")
        if approval.status != "approved":
            raise CapabilityError(
                f"approval request is '{approval.status}' — grants mint only from approvals"
            )
        if not action_type or not resource:
            raise CapabilityError("action_type and resource are required")

        grant = CapabilityGrant(
            requester_identity=requester_identity,
            approver_identity=approver_identity,
            approval_request_id=approval_request_id,
            action_type=action_type,
            exact_action=exact_action,
            resource=resource,
            account_lane_id=account_lane_id,
            named_targets=list(named_targets or []),
            max_cost=float(max_cost),
            maximum_uses=int(maximum_uses),
            expires_at=_now() + timedelta(hours=ttl_hours or default_ttl_hours()),
            evidence_refs=list(evidence_refs or []),
            rollback_note=rollback_note,
            trace_id=trace_id,
            metadata=metadata or {},
        )
        session.add(grant)
        session.commit()
        self.ledger.record("capability_granted", {
            "id": grant.id, "approval_request_id": approval_request_id,
            "action_type": action_type, "resource": resource,
            "maximum_uses": grant.maximum_uses,
            "expires_at": grant.expires_at.isoformat(),
        })
        return grant

    # ------------------------------------------------------------------ #
    # Execution-time validation: the load-bearing gate
    # ------------------------------------------------------------------ #
    def validate_and_consume(
        self,
        session: Any,
        grant_id: str,
        action_type: str,
        resource: str,
        *,
        target: Optional[str] = None,
        cost: float = 0.0,
    ) -> CapabilityGrant:
        """Validate a grant immediately before execution and consume one
        use. Any failure raises CapabilityError — the caller must not act."""
        # A broken ledger disarms external action entirely: if the record
        # of authority can't be trusted, no authority is exercised.
        chain_ok, _ = self.ledger.verify_chain()
        if not chain_ok:
            self._reject(grant_id, "ledger_chain_broken")
            raise CapabilityError("decision ledger chain is broken — failing closed")

        grant = session.query(CapabilityGrant).filter(lambda g: g.id == grant_id).first()
        if grant is None:
            self._reject(grant_id, "unknown_grant")
            raise CapabilityError("unknown capability grant")
        if grant.revocation_status != "active":
            self._reject(grant_id, "revoked")
            raise CapabilityError("grant is revoked")
        now = _now()
        if grant.not_before and now < grant.not_before:
            self._reject(grant_id, "not_yet_valid")
            raise CapabilityError("grant is not yet valid")
        if grant.expires_at and now >= grant.expires_at:
            self._reject(grant_id, "expired")
            self.ledger.record("capability_expired", {"id": grant.id})
            raise CapabilityError("grant is expired")
        if grant.uses_consumed >= grant.maximum_uses:
            self._reject(grant_id, "exhausted")
            raise CapabilityError("grant is exhausted — replay refused")
        if grant.action_type != action_type:
            self._reject(grant_id, "action_mismatch")
            raise CapabilityError(
                f"grant authorizes '{grant.action_type}', not '{action_type}'"
            )
        if grant.resource != resource:
            self._reject(grant_id, "resource_mismatch")
            raise CapabilityError("grant does not cover this resource")
        if target is not None and grant.named_targets and target not in grant.named_targets:
            self._reject(grant_id, "target_mismatch")
            raise CapabilityError("grant does not cover this target")
        if cost and cost > grant.max_cost:
            self._reject(grant_id, "cost_exceeded")
            raise CapabilityError(
                f"cost {cost} exceeds the grant ceiling {grant.max_cost}"
            )

        grant.uses_consumed += 1
        session.commit()
        self.ledger.record("capability_consumed", {
            "id": grant.id, "action_type": action_type, "resource": resource,
            "use": grant.uses_consumed, "of": grant.maximum_uses,
        })
        return grant

    def _reject(self, grant_id: str, reason: str) -> None:
        self.ledger.record("capability_rejected", {"id": grant_id, "reason": reason})
        logger.warning(f"Capability rejected: {grant_id} ({reason})")

    # ------------------------------------------------------------------ #
    # Revocation: immediate, ledgered
    # ------------------------------------------------------------------ #
    def revoke(
        self, session: Any, grant_id: str, *, revoked_by: str = "admin", reason: str = ""
    ) -> CapabilityGrant:
        grant = session.query(CapabilityGrant).filter(lambda g: g.id == grant_id).first()
        if grant is None:
            raise CapabilityError("unknown capability grant")
        grant.revocation_status = "revoked"
        grant.revoked_at = _now()
        grant.revoked_by = revoked_by
        grant.revocation_reason = reason
        session.commit()
        self.ledger.record("capability_revoked", {
            "id": grant.id, "by": revoked_by, "reason": reason,
        })
        return grant


_SHARED: Optional[CapabilityService] = None


def get_capability_service() -> CapabilityService:
    global _SHARED
    if _SHARED is None:
        _SHARED = CapabilityService()
    return _SHARED


def set_capability_service(service: Optional[CapabilityService]) -> None:
    global _SHARED
    _SHARED = service


__all__ = [
    "CapabilityError", "CapabilityService",
    "get_capability_service", "set_capability_service", "default_ttl_hours",
]
