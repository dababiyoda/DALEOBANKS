"""Everything this institution leans on that it does not control.

Platform adapters, model providers, production tools, and automations look
like four different problems and are one: an outside capability with declared
bounds, a revocation state, and something to fall back to. Recording them as
four registries would mean four places to forget a rate limit and four
definitions of what "revoked" means.

The reason this exists is portability. The identity is supposed to survive a
model change, a vendor change, losing a social platform, an API disappearing,
and a tool being replaced. It survives those only if every dependency was
written down as replaceable before it was needed — afterwards is too late,
because by then the thing that knew its bounds is the thing that left.

Two rules do the work. A dependency may not go live until every field an
adapter needs is present, so an integration cannot be half-declared into
production. And credential material never enters a record; only a reference
to where it lives.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import DependencyRecord
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

KINDS = ("platform_adapter", "model_provider", "production_tool", "automation")

STATUSES = ("NOT_CONFIGURED", "CONFIGURED", "ACTIVE", "DEGRADED", "REVOKED", "RETIRED")

# Only a live dependency can cause an external effect, so only a live
# dependency has to be fully declared.
LIVE_STATUSES = frozenset({"ACTIVE", "DEGRADED"})

# Credentials live somewhere else. A record holds the address, never the key.
ALLOWED_CREDENTIAL_PREFIXES = ("env:", "vault:", "secret-manager:")

# The eleven properties a platform adapter must carry before it may go live.
PLATFORM_LIVE_REQUIREMENTS = (
    "role", "authorized_capabilities", "permitted_content_classes",
    "posting_limit_per_day", "rate_limit_per_hour", "risk_class",
    "credential_owner", "credential_reference", "evidence_requirements",
    "rollback_mechanism", "freeze_mechanism",
)

# An automation must be reversible and observable, owned and documented,
# before it runs. An automation nobody can see or stop is not automation.
AUTOMATION_LIVE_REQUIREMENTS = (
    "role", "version", "owner", "documentation_ref",
    "rollback_mechanism", "reversible", "observable",
)

# A model is a replaceable reasoning engine, and replacing it means knowing
# what it costs, how it fails, and what runs instead.
MODEL_LIVE_REQUIREMENTS = (
    "role", "version", "owner", "failure_modes",
    "cost_note", "latency_note", "fallback_dependency_id",
)

PRODUCTION_TOOL_LIVE_REQUIREMENTS = (
    "role", "owner", "credential_owner", "credential_reference",
    "rollback_mechanism", "fallback_dependency_id",
)

_REQUIREMENTS = {
    "platform_adapter": PLATFORM_LIVE_REQUIREMENTS,
    "automation": AUTOMATION_LIVE_REQUIREMENTS,
    "model_provider": MODEL_LIVE_REQUIREMENTS,
    "production_tool": PRODUCTION_TOOL_LIVE_REQUIREMENTS,
}


class DependencyError(ValueError):
    """A dependency was declared or activated in a state that is not safe."""


class CredentialLeakError(DependencyError):
    """Credential material was placed in a record instead of a reference."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_credential_reference(reference: str) -> str:
    """A reference points at a secret store. It is never the secret.

    An empty reference is allowed — many dependencies need none. What is not
    allowed is something that looks like a key sitting in a record.
    """
    value = (reference or "").strip()
    if not value:
        return ""
    if not value.startswith(ALLOWED_CREDENTIAL_PREFIXES):
        raise CredentialLeakError(
            f"credential_reference must start with one of "
            f"{list(ALLOWED_CREDENTIAL_PREFIXES)}; a record holds the address of "
            f"a secret, never the secret"
        )
    return value


def missing_live_requirements(record: DependencyRecord) -> List[str]:
    """Which declared properties are still absent for this kind."""
    missing: List[str] = []
    for field_name in _REQUIREMENTS.get(record.kind, ()):
        value = getattr(record, field_name, None)
        if value is None or value == "" or value == [] or value is False:
            missing.append(field_name)
    return missing


class DependencyRegistry:
    """Declare, activate, degrade, and revoke outside capabilities."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def declare(
        self, session: Any, *, kind: str, name: str, **fields: Any
    ) -> DependencyRecord:
        """Write a dependency down. Declaring is not activating."""
        if kind not in KINDS:
            raise DependencyError(f"kind must be one of {list(KINDS)}")
        if not (name or "").strip():
            raise DependencyError("a dependency requires a name")
        if "credential_reference" in fields:
            fields["credential_reference"] = validate_credential_reference(
                fields["credential_reference"]
            )
        record = DependencyRecord(kind=kind, name=name.strip(), **fields)
        session.add(record)
        session.commit()
        self.ledger.record("dependency_declared", {
            "dependency_id": record.id, "kind": kind, "name": record.name,
            "status": record.status,
            "missing_for_live": missing_live_requirements(record),
        })
        return record

    def activate(self, session: Any, *, dependency_id: str) -> DependencyRecord:
        """Take a dependency live, only once it is completely declared.

        This is where a half-configured integration would otherwise reach
        production: the code works, so someone turns it on, and the rate
        limit nobody wrote down becomes the incident.
        """
        record = self._dependency(session, dependency_id)
        if record.revocation_state != "NOT_REVOKED":
            raise DependencyError(
                f"dependency is {record.revocation_state} and cannot be activated"
            )
        missing = missing_live_requirements(record)
        if missing:
            raise DependencyError(
                f"'{record.name}' cannot go live with undeclared properties: "
                + ", ".join(missing)
            )
        validate_credential_reference(record.credential_reference)
        record.status = "ACTIVE"
        record.updated_at = _now()
        session.commit()
        self.ledger.record("dependency_activated", {
            "dependency_id": record.id, "kind": record.kind, "name": record.name,
        })
        return record

    def revoke(
        self, session: Any, *, dependency_id: str, reason: str
    ) -> Dict[str, Any]:
        """Revoke a dependency and report what now has no fallback.

        Revocation is the moment portability is tested. Anything that pointed
        at this dependency and has no alternative is named here rather than
        discovered later.
        """
        if not (reason or "").strip():
            raise DependencyError("revocation requires a reason")
        record = self._dependency(session, dependency_id)
        record.status = "REVOKED"
        record.revocation_state = "REVOKED"
        record.updated_at = _now()

        orphaned = [
            {"id": row.id, "name": row.name, "kind": row.kind}
            for row in session.query(DependencyRecord).all()
            if row.fallback_dependency_id == record.id
        ]
        session.commit()
        result = {
            "dependency_id": record.id, "name": record.name,
            "reason": reason.strip(),
            "dependents_left_without_fallback": orphaned,
        }
        self.ledger.record("dependency_revoked", result)
        return result

    def portability_report(self, session: Any) -> Dict[str, Any]:
        """Where this institution is one outage away from being stuck."""
        records = session.query(DependencyRecord).all()
        live = [r for r in records if r.status in LIVE_STATUSES]
        return {
            "declared": len(records),
            "live": len(live),
            "by_kind": {
                kind: sum(1 for r in records if r.kind == kind) for kind in KINDS
            },
            "live_without_fallback": [
                r.name for r in live if not r.fallback_dependency_id
            ],
            "live_without_rollback": [
                r.name for r in live if not r.rollback_mechanism
            ],
            "incompletely_declared": {
                r.name: missing_live_requirements(r)
                for r in records if missing_live_requirements(r)
            },
        }

    @staticmethod
    def _dependency(session: Any, dependency_id: str) -> DependencyRecord:
        record = session.query(DependencyRecord).filter(
            lambda row: row.id == dependency_id
        ).first()
        if record is None:
            raise DependencyError("dependency is not registered")
        return record


__all__ = [
    "KINDS", "STATUSES", "LIVE_STATUSES", "ALLOWED_CREDENTIAL_PREFIXES",
    "PLATFORM_LIVE_REQUIREMENTS", "AUTOMATION_LIVE_REQUIREMENTS",
    "MODEL_LIVE_REQUIREMENTS", "PRODUCTION_TOOL_LIVE_REQUIREMENTS",
    "DependencyError", "CredentialLeakError", "DependencyRegistry",
    "validate_credential_reference", "missing_live_requirements",
]
