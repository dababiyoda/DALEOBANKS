"""Canonical registry for every official DALEOBANKS public surface.

The historical ``AccountLane`` model remains the storage object.  This
service makes its lifecycle and authority fields executable: official
handles are never inferred, credential *references* are stored instead of
secrets, and a registry entry can narrow external authority but can never
create it.  Live publication still requires the consequence gates in
``services.capability`` and ``services.social_base``.
"""

from __future__ import annotations

import re
from datetime import datetime, UTC
from typing import Any, Dict, Iterable, Optional

from db.models import AccountLane
from services.ledger import DecisionLedger, get_ledger
from services.venture_protocol import validate_identity_type


ACCOUNT_STATUSES = frozenset({
    "PLANNED", "SHADOW", "ACTIVE", "PAUSED", "FROZEN", "RETIRED",
    "COMPROMISED",
})

AUTHORIZATION_STATES = frozenset({
    "NONE", "SHADOW_ONLY", "APPROVAL_REQUIRED", "STANDING_MANDATE",
})

_LIVE_AUTHORIZATION = frozenset({"APPROVAL_REQUIRED", "STANDING_MANDATE"})
_CREDENTIAL_REF_PREFIXES = ("env:", "vault:", "secret-manager:")
_SECRET_SHAPED = re.compile(
    r"(?:bearer\s+|token\s*[=:]|secret\s*[=:]|password\s*[=:])",
    re.IGNORECASE,
)


class AccountRegistryError(ValueError):
    """An account record or lifecycle transition violates registry policy."""


def _now() -> datetime:
    return datetime.now(UTC)


class AccountRegistry:
    """Validate, persist, resolve, and lifecycle official account records."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def register(self, session: Any, **fields: Any) -> AccountLane:
        """Register one declared surface; no public search or inference."""
        lane = AccountLane(**fields)
        self.validate(lane)
        duplicates = session.query(AccountLane).filter(
            lambda existing: existing.id == lane.id
            or (
                bool(lane.handle)
                and existing.platform.lower() == lane.platform.lower()
                and existing.handle.lower() == lane.handle.lower()
            )
        ).all()
        if duplicates:
            raise AccountRegistryError("account id or platform handle is already registered")
        lane.active = lane.status == "ACTIVE"
        session.add(lane)
        session.commit()
        self.ledger.record("account_registered", self.public_record(lane))
        return lane

    def validate(self, lane: AccountLane) -> AccountLane:
        validate_identity_type(lane.identity_type)
        lane.status = str(lane.status or "").upper()
        lane.current_authorization = str(lane.current_authorization or "").upper()
        if lane.status not in ACCOUNT_STATUSES:
            raise AccountRegistryError(
                f"status must be one of {sorted(ACCOUNT_STATUSES)}"
            )
        if lane.current_authorization not in AUTHORIZATION_STATES:
            raise AccountRegistryError(
                "current_authorization must be one of "
                f"{sorted(AUTHORIZATION_STATES)}"
            )
        if lane.parent_identity != "DALEOBANKS":
            raise AccountRegistryError(
                "every official surface must name DALEOBANKS as parent_identity"
            )
        if not lane.name.strip() or not lane.platform.strip():
            raise AccountRegistryError("name and platform are required")
        if _SECRET_SHAPED.search(lane.credential_ref or ""):
            raise AccountRegistryError(
                "credential_ref must point to a secret; never store credential material"
            )
        if lane.credential_ref and not lane.credential_ref.startswith(_CREDENTIAL_REF_PREFIXES):
            raise AccountRegistryError(
                "credential_ref must start with env:, vault:, or secret-manager:"
            )
        if lane.status == "ACTIVE":
            self._validate_active(lane)
        elif lane.current_authorization in _LIVE_AUTHORIZATION:
            raise AccountRegistryError(
                "non-ACTIVE accounts may only hold NONE or SHADOW_ONLY authorization"
            )
        return lane

    def _validate_active(self, lane: AccountLane) -> None:
        missing = [name for name, value in (
            ("handle", lane.handle),
            ("legal_principal", lane.legal_principal),
            ("credential_ref", lane.credential_ref),
            ("authorization_ref", lane.authorization_ref),
            ("last_verified", lane.last_verified),
        ) if not value]
        if missing:
            raise AccountRegistryError(
                f"ACTIVE account is missing verified fields: {', '.join(missing)}"
            )
        if lane.current_authorization not in _LIVE_AUTHORIZATION:
            raise AccountRegistryError(
                "ACTIVE account requires APPROVAL_REQUIRED or STANDING_MANDATE"
            )
        max_per_day = (lane.posting_limits or {}).get("max_per_day")
        if not isinstance(max_per_day, int) or max_per_day <= 0:
            raise AccountRegistryError(
                "ACTIVE account requires a positive integer posting_limits.max_per_day"
            )

    def transition(
        self,
        session: Any,
        account_id: str,
        status: str,
        *,
        actor: str,
        authorization_ref: str = "",
        last_verified: Optional[datetime] = None,
    ) -> AccountLane:
        lane = self.get(session, account_id)
        previous = lane.status
        lane.status = status.upper()
        if lane.status in {"PAUSED", "FROZEN", "RETIRED", "COMPROMISED"}:
            # A safety transition must never be blocked by stale live
            # authorization metadata.  Preserve the authorization reference
            # for audit, but collapse executable state immediately.
            lane.current_authorization = "NONE"
        elif lane.status == "SHADOW":
            lane.current_authorization = "SHADOW_ONLY"
        if authorization_ref:
            lane.authorization_ref = authorization_ref
        if last_verified is not None:
            lane.last_verified = last_verified
        self.validate(lane)
        lane.active = lane.status == "ACTIVE"
        session.commit()
        self.ledger.record("account_status_changed", {
            "account_id": lane.id,
            "from": previous,
            "to": lane.status,
            "actor": actor,
            "authorization_ref": authorization_ref,
        })
        return lane

    @staticmethod
    def get(session: Any, account_id: str) -> AccountLane:
        lane = session.query(AccountLane).filter(lambda row: row.id == account_id).first()
        if lane is None:
            raise AccountRegistryError("account is not registered")
        return lane

    @staticmethod
    def list(session: Any, statuses: Optional[Iterable[str]] = None) -> list[AccountLane]:
        allowed = {s.upper() for s in statuses} if statuses else None
        return session.query(AccountLane).filter(
            lambda row: allowed is None or row.status in allowed
        ).all()

    def evaluate_authority(
        self,
        session: Any,
        account_id: str,
        *,
        platform: str,
        external_effect: bool,
    ) -> Dict[str, Any]:
        """Return the account-layer decision without widening authority.

        A positive external account decision is only a prerequisite.  The
        caller must still validate and consume an exact CapabilityGrant at
        the consequence gate immediately before a live action.
        """
        lane = self.get(session, account_id)
        self.validate(lane)
        if lane.status in {"PAUSED", "FROZEN", "RETIRED", "COMPROMISED"}:
            return self._decision(lane, False, "account lifecycle blocks action")
        if lane.platform.lower() != platform.lower():
            return self._decision(lane, False, "platform does not match registry")
        if not external_effect:
            allowed = lane.status in {"SHADOW", "ACTIVE"}
            return self._decision(
                lane, allowed,
                "shadow action permitted" if allowed else "account is not in SHADOW or ACTIVE",
            )
        if lane.status != "ACTIVE" or lane.current_authorization not in _LIVE_AUTHORIZATION:
            return self._decision(lane, False, "account has no current external authority")
        return self._decision(
            lane, True,
            "account prerequisite satisfied; exact capability grant still required",
            requires_capability_grant=True,
        )

    @staticmethod
    def _decision(
        lane: AccountLane,
        allowed: bool,
        reason: str,
        *,
        requires_capability_grant: bool = False,
    ) -> Dict[str, Any]:
        return {
            "allowed": allowed,
            "reason": reason,
            "account_id": lane.id,
            "status": lane.status,
            "authorization": lane.current_authorization,
            "requires_capability_grant": requires_capability_grant,
        }

    @staticmethod
    def public_record(lane: AccountLane) -> Dict[str, Any]:
        """Serialize registry metadata without exposing credential material."""
        return {
            "account_id": lane.id,
            "platform": lane.platform,
            "handle": lane.handle,
            "language": lane.language,
            "region": lane.region,
            "topic_lane": lane.topic_lane,
            "public_brand_name": lane.public_brand_name,
            "parent_identity": lane.parent_identity,
            "legal_principal": lane.legal_principal,
            "credential_configured": bool(lane.credential_ref),
            "current_authorization": lane.current_authorization,
            "authorization_ref": lane.authorization_ref,
            "posting_limits": dict(lane.posting_limits or {}),
            "risk_class": lane.risk_class,
            "commercial_disclosure_requirements": list(
                lane.commercial_disclosure_requirements or []
            ),
            "status": lane.status,
            "created_at": lane.created_at.isoformat(),
            "last_verified": lane.last_verified.isoformat() if lane.last_verified else None,
        }


__all__ = [
    "ACCOUNT_STATUSES", "AUTHORIZATION_STATES", "AccountRegistry",
    "AccountRegistryError",
]
