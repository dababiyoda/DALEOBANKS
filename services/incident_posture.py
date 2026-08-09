"""What happens when something breaks, recorded so it can be undone.

The failure posture is easy to state and hard to keep: degrade toward pause,
then draft-only, then read-only, then silence, and never toward uncontrolled
publishing or spending. The part that gets lost is the return trip. A freeze
with no record cannot be audited, cannot be lifted deliberately, and ends up
either permanent by neglect or evaporating because nobody remembered it was
on. Both outcomes are worse than the incident that caused them.

So a posture change is a recorded event with a reason, recovery is gated on
conditions declared while the incident is still open, and an incident may be
closed unresolved — which is honest — but never closed by forgetting.

The one rule the ladder enforces mechanically: severity may loosen a posture
only through a recovery, never through a second incident. Tightening is
always allowed and never needs permission.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import IncidentRecord
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

# Ordered from most permissive to most restrictive. Degrading means moving
# right; nothing may move left except through a recorded recovery.
POSTURES = ("RUN", "PAUSE", "DRAFT_ONLY", "READ_ONLY", "SILENT")

SEVERITIES = ("low", "medium", "high", "critical")

INCIDENT_KINDS = (
    "security", "reputational", "legal", "platform",
    "data", "budget", "scheduler", "other",
)

# Severity floors. A critical incident does not sit at PAUSE because someone
# was optimistic about it.
MINIMUM_POSTURE_BY_SEVERITY = {
    "low": "RUN",
    "medium": "PAUSE",
    "high": "DRAFT_ONLY",
    "critical": "SILENT",
}

# Above this severity a human is named, always.
ESCALATION_FLOOR = "high"


class IncidentError(ValueError):
    """An incident or posture transition violated the failure posture."""


def posture_index(posture: str) -> int:
    try:
        return POSTURES.index(posture)
    except ValueError:
        return -1


def is_tightening(current: str, proposed: str) -> bool:
    return posture_index(proposed) > posture_index(current)


def minimum_posture_for(severity: str) -> str:
    return MINIMUM_POSTURE_BY_SEVERITY.get(severity, "SILENT")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentPosture:
    """Open incidents, degrade safely, and recover only on declared evidence."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def open_incident(
        self,
        session: Any,
        *,
        kind: str,
        severity: str,
        summary: str,
        detected_by: str,
        posture: str = "",
        posture_reason: str = "",
        evidence_refs: Optional[Sequence[str]] = None,
        affected_dependency_ids: Optional[Sequence[str]] = None,
        affected_account_ids: Optional[Sequence[str]] = None,
        escalated_to: str = "",
    ) -> IncidentRecord:
        """Open an incident at a posture no looser than its severity allows."""
        if kind not in INCIDENT_KINDS:
            raise IncidentError(f"kind must be one of {list(INCIDENT_KINDS)}")
        if severity not in SEVERITIES:
            raise IncidentError(f"severity must be one of {list(SEVERITIES)}")
        if not (summary or "").strip() or not (detected_by or "").strip():
            raise IncidentError("summary and detected_by are required")

        floor = minimum_posture_for(severity)
        chosen = posture or floor
        if posture_index(chosen) < 0:
            raise IncidentError(f"posture must be one of {list(POSTURES)}")
        if posture_index(chosen) < posture_index(floor):
            raise IncidentError(
                f"a {severity} incident may not sit at {chosen}; the floor is "
                f"{floor}. Optimism is not a containment strategy"
            )
        if (SEVERITIES.index(severity) >= SEVERITIES.index(ESCALATION_FLOOR)
                and not (escalated_to or "").strip()):
            raise IncidentError(
                f"a {severity} incident must name the human it escalates to"
            )

        record = IncidentRecord(
            kind=kind, severity=severity, summary=summary.strip(),
            detected_by=detected_by.strip(), detected_at=_now().isoformat(),
            posture=chosen, posture_reason=(posture_reason or f"{severity} {kind}").strip(),
            evidence_refs=list(evidence_refs or []),
            affected_dependency_ids=list(affected_dependency_ids or []),
            affected_account_ids=list(affected_account_ids or []),
            escalated_to=escalated_to.strip(),
        )
        record.posture_history.append({
            "from": "RUN", "posture": chosen, "reason": record.posture_reason,
            "at": _now().isoformat(), "actor": record.detected_by,
        })
        session.add(record)
        session.commit()
        self.ledger.record("incident_opened", {
            "incident_id": record.id, "kind": kind, "severity": severity,
            "posture": chosen, "escalated_to": record.escalated_to,
        })
        if posture_index(chosen) > posture_index("RUN"):
            self.ledger.record("posture_frozen", {
                "incident_id": record.id, "posture": chosen,
                "reason": record.posture_reason,
            })
        return record

    def tighten(
        self, session: Any, *, incident_id: str, posture: str, reason: str, actor: str
    ) -> IncidentRecord:
        """Degrade further. Always allowed, never needs permission."""
        record = self._incident(session, incident_id)
        if posture_index(posture) < 0:
            raise IncidentError(f"posture must be one of {list(POSTURES)}")
        if not is_tightening(record.posture, posture):
            raise IncidentError(
                f"{posture} is not tighter than {record.posture}; loosening "
                f"happens through recovery, not through a posture change"
            )
        if not (reason or "").strip() or not (actor or "").strip():
            raise IncidentError("tightening requires a reason and an actor")
        previous = record.posture
        record.posture = posture
        record.posture_reason = reason.strip()
        record.posture_history.append({
            "from": previous, "posture": posture, "reason": reason.strip(),
            "at": _now().isoformat(), "actor": actor.strip(),
        })
        session.commit()
        self.ledger.record("posture_frozen", {
            "incident_id": record.id, "from": previous, "posture": posture,
            "reason": reason.strip(),
        })
        return record

    def declare_recovery_conditions(
        self, session: Any, *, incident_id: str, conditions: Sequence[str]
    ) -> IncidentRecord:
        """State what would have to be true to come back, while still down.

        Declared during the incident on purpose. Conditions written after the
        pressure lifts are conditions written to be satisfiable.
        """
        record = self._incident(session, incident_id)
        stated = [str(c).strip() for c in conditions if str(c).strip()]
        if not stated:
            raise IncidentError("at least one recovery condition is required")
        if record.status in ("RECOVERED", "CLOSED_UNRESOLVED"):
            raise IncidentError("incident is already closed")
        record.recovery_conditions = stated
        record.status = "CONTAINED"
        session.commit()
        self.ledger.record("incident_contained", {
            "incident_id": record.id, "recovery_conditions": stated,
        })
        return record

    def recover(
        self,
        session: Any,
        *,
        incident_id: str,
        evidence_refs: Sequence[str],
        learning: str,
        actor: str,
    ) -> IncidentRecord:
        """Return to RUN, only against conditions declared beforehand."""
        record = self._incident(session, incident_id)
        if record.status == "RECOVERED":
            raise IncidentError("incident has already recovered")
        if not record.recovery_conditions:
            raise IncidentError(
                "recovery requires conditions declared while the incident was "
                "open; conditions written afterwards are written to be met"
            )
        refs = [str(r).strip() for r in evidence_refs if str(r).strip()]
        if len(refs) < len(record.recovery_conditions):
            raise IncidentError(
                f"{len(record.recovery_conditions)} recovery conditions were "
                f"declared and {len(refs)} pieces of evidence were supplied"
            )
        if not (learning or "").strip() or not (actor or "").strip():
            raise IncidentError("recovery requires a learning statement and an actor")

        previous = record.posture
        record.recovery_evidence_refs = refs
        record.learning = learning.strip()
        record.posture = "RUN"
        record.status = "RECOVERED"
        record.recovered_at = _now().isoformat()
        record.posture_history.append({
            "from": previous, "posture": "RUN", "reason": "recovered",
            "at": record.recovered_at, "actor": actor.strip(),
        })
        session.commit()
        self.ledger.record("incident_recovered", {
            "incident_id": record.id, "from_posture": previous,
            "evidence_refs": refs, "learning": record.learning,
        })
        return record

    def close_unresolved(
        self, session: Any, *, incident_id: str, reason: str, actor: str
    ) -> IncidentRecord:
        """Close without recovering. The posture stays where it is.

        Honest, and deliberately uncomfortable: the restriction remains until
        someone recovers it properly.
        """
        record = self._incident(session, incident_id)
        if not (reason or "").strip() or not (actor or "").strip():
            raise IncidentError("closing unresolved requires a reason and an actor")
        record.status = "CLOSED_UNRESOLVED"
        record.learning = reason.strip()
        session.commit()
        self.ledger.record("incident_closed_unresolved", {
            "incident_id": record.id, "posture_retained": record.posture,
            "reason": reason.strip(),
        })
        return record

    def effective_posture(self, session: Any) -> Dict[str, Any]:
        """The tightest posture any open incident imposes.

        Postures compose by taking the maximum. Two medium incidents do not
        cancel into a mild one.
        """
        open_incidents = [
            r for r in session.query(IncidentRecord).all()
            if r.status in ("OPEN", "CONTAINED", "CLOSED_UNRESOLVED")
        ]
        if not open_incidents:
            return {"posture": "RUN", "driven_by": None, "open_incidents": 0}
        tightest = max(open_incidents, key=lambda r: posture_index(r.posture))
        return {
            "posture": tightest.posture,
            "driven_by": tightest.id,
            "severity": tightest.severity,
            "open_incidents": len(open_incidents),
            "publishing_permitted": posture_index(tightest.posture) <= posture_index("RUN"),
            "spending_permitted": posture_index(tightest.posture) <= posture_index("RUN"),
        }

    @staticmethod
    def _incident(session: Any, incident_id: str) -> IncidentRecord:
        record = session.query(IncidentRecord).filter(
            lambda row: row.id == incident_id
        ).first()
        if record is None:
            raise IncidentError("incident is not registered")
        return record


__all__ = [
    "POSTURES", "SEVERITIES", "INCIDENT_KINDS", "MINIMUM_POSTURE_BY_SEVERITY",
    "ESCALATION_FLOOR", "IncidentError", "IncidentPosture",
    "posture_index", "is_tightening", "minimum_posture_for",
]
