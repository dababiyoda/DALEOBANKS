"""The six adversarial controls the list named and the repository lacked.

Each guard fails closed and each has a case proving it refuses. They are
grouped here because they share a posture rather than a subject: when any of
them is uncertain, the answer is stop, not proceed.

Budget overrun, scheduler death, duplicate publication, unsolicited direct
messages, unsupported health claims, and reading a person's record for a
purpose they never agreed to. Different failures, one rule — degrade toward
pause, draft-only, read-only, and silence. Never toward publishing or
spending.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.logging_utils import get_logger

logger = get_logger(__name__)


class OperationalGuardError(ValueError):
    """An operational invariant would have been violated."""


class BudgetExceededError(OperationalGuardError):
    """A spend would cross a declared ceiling."""


class SchedulerStaleError(OperationalGuardError):
    """The scheduler has not checked in and must not be assumed alive."""


class DuplicatePublicationError(OperationalGuardError):
    """This exact artifact has already gone out on this surface."""


class UnsolicitedMessageError(OperationalGuardError):
    """A direct message would go to someone who did not ask for one."""


class UnsupportedHealthClaimError(OperationalGuardError):
    """A health or mental-health claim exceeds what the evidence supports."""


class PurposeViolationError(OperationalGuardError):
    """A person's record was read for a purpose they did not consent to."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------- #

def budget_check(
    *, ceiling: Optional[float], committed: float, requested: float
) -> Dict[str, Any]:
    """Would this spend cross the ceiling?

    A ceiling of None is not unlimited. It means no ceiling was declared, and
    an undeclared ceiling is zero — the founder governance model has budgets
    coming from the founder, not from whatever the code happens to allow.
    """
    if ceiling is None:
        return {"allowed": False, "reason": "no budget ceiling is declared",
                "ceiling": None, "committed": committed, "requested": requested}
    remaining = ceiling - committed
    allowed = requested <= remaining
    return {
        "allowed": allowed, "ceiling": ceiling, "committed": committed,
        "requested": requested, "remaining": remaining,
        "reason": ("within the declared ceiling" if allowed
                   else f"requested {requested} exceeds remaining {remaining}"),
    }


def assert_within_budget(
    *, ceiling: Optional[float], committed: float, requested: float, purpose: str
) -> Dict[str, Any]:
    verdict = budget_check(ceiling=ceiling, committed=committed, requested=requested)
    if not verdict["allowed"]:
        raise BudgetExceededError(f"{purpose}: {verdict['reason']}")
    return verdict


# --------------------------------------------------------------------- #
# Scheduler liveness
# --------------------------------------------------------------------- #

DEFAULT_HEARTBEAT_TOLERANCE_SECONDS = 900


def scheduler_health(
    *, last_heartbeat: Optional[datetime],
    tolerance_seconds: int = DEFAULT_HEARTBEAT_TOLERANCE_SECONDS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Is the scheduler alive, and what should happen if it is not?

    A crashed scheduler is dangerous in a specific way: work stops silently
    while the rest of the system continues believing it is scheduled. Absence
    of a heartbeat is treated as death, not as an unknown.
    """
    current = now or _now()
    if last_heartbeat is None:
        return {"alive": False, "age_seconds": None, "posture": "PAUSE",
                "reason": "no heartbeat has ever been recorded"}
    age = (current - last_heartbeat).total_seconds()
    alive = age <= tolerance_seconds
    return {
        "alive": alive, "age_seconds": age,
        "posture": "RUN" if alive else "PAUSE",
        "reason": ("heartbeat is current" if alive
                   else f"last heartbeat {age:.0f}s ago exceeds {tolerance_seconds}s"),
    }


def assert_scheduler_alive(
    *, last_heartbeat: Optional[datetime],
    tolerance_seconds: int = DEFAULT_HEARTBEAT_TOLERANCE_SECONDS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    verdict = scheduler_health(last_heartbeat=last_heartbeat,
                               tolerance_seconds=tolerance_seconds, now=now)
    if not verdict["alive"]:
        raise SchedulerStaleError(
            f"scheduler is not confirmed alive ({verdict['reason']}); "
            f"degrade to {verdict['posture']} rather than assuming it ran"
        )
    return verdict


# --------------------------------------------------------------------- #
# Duplicate publication and replay
# --------------------------------------------------------------------- #

def publication_fingerprint(*, account_id: str, surface: str, body: str) -> str:
    """Stable identity for one artifact on one surface.

    Whitespace-normalized so a reformatted repost is still the same post.
    """
    normalized = " ".join((body or "").split()).strip().lower()
    material = f"{account_id}\x1f{surface}\x1f{normalized}"
    return hashlib.sha256(material.encode()).hexdigest()


def assert_not_duplicate(
    *, account_id: str, surface: str, body: str, seen: Iterable[str]
) -> str:
    """Refuse a second publication of the same artifact to the same place."""
    fingerprint = publication_fingerprint(
        account_id=account_id, surface=surface, body=body
    )
    if fingerprint in set(seen):
        raise DuplicatePublicationError(
            f"this artifact has already been published to {surface} on account "
            f"{account_id} (fingerprint {fingerprint[:12]})"
        )
    return fingerprint


# --------------------------------------------------------------------- #
# Direct messages
# --------------------------------------------------------------------- #

def assert_dm_permitted(
    *,
    recipient_ref: str,
    inbound_initiated: bool,
    consent_evidence_ref: str = "",
    capability_grant_id: str = "",
) -> Dict[str, Any]:
    """A direct message needs a reason to exist that came from the recipient.

    Either they wrote first, or they consented. Wanting to reach someone is
    not a reason, and scale makes it worse rather than better.
    """
    if not (recipient_ref or "").strip():
        raise UnsolicitedMessageError("a recipient reference is required")
    invited = inbound_initiated or bool((consent_evidence_ref or "").strip())
    if not invited:
        raise UnsolicitedMessageError(
            "the recipient neither initiated contact nor consented; an "
            "uninvited direct message is not permitted at any scale"
        )
    if not (capability_grant_id or "").strip():
        raise UnsolicitedMessageError(
            "sending requires an exact capability grant; being invited is "
            "permission from the person, not authority from the institution"
        )
    return {"permitted": True, "inbound_initiated": inbound_initiated,
            "consented": bool(consent_evidence_ref)}


# --------------------------------------------------------------------- #
# Health and mental-health claims
# --------------------------------------------------------------------- #

_DIAGNOSTIC_MARKERS = (
    "you have", "you're suffering from", "you are suffering from",
    "diagnos", "you clearly have", "this is textbook", "symptoms mean",
)
_TREATMENT_MARKERS = (
    "will cure", "cures", "will heal you", "guaranteed to heal",
    "stop taking", "instead of therapy", "instead of medication",
    "you don't need a doctor", "you don't need therapy", "replaces therapy",
)
_HEALTH_TOPIC_MARKERS = (
    "depression", "anxiety", "adhd", "ptsd", "trauma", "bipolar",
    "medication", "diagnosis", "therapy", "disorder", "cure", "supplement",
    "treatment", "symptoms",
)
_QUALIFIER_MARKERS = (
    "not medical advice", "not a diagnosis", "speak to a", "see a clinician",
    "see a doctor", "consult a", "a professional can", "educational only",
    "this is not therapy", "if this is you, talk to",
)


def health_claim_assessment(text: str) -> Dict[str, Any]:
    """Scan for claims in what remains after the disclaimers are removed.

    Scanning the raw text would flag "this is not a diagnosis" as a diagnosis,
    which would refuse the correctly-qualified version and leave only the
    unqualified one writable. A phrase inside a disclaimer is not a claim, so
    the disclaimers come out before the scan.
    """
    lower = (text or "").lower()
    qualifiers = [q for q in _QUALIFIER_MARKERS if q in lower]
    residual = lower
    for qualifier in qualifiers:
        residual = residual.replace(qualifier, " ")
    return {
        "touches_health": any(m in lower for m in _HEALTH_TOPIC_MARKERS),
        "diagnostic": [m for m in _DIAGNOSTIC_MARKERS if m in residual],
        "treatment_claim": [m for m in _TREATMENT_MARKERS if m in residual],
        "qualifiers": qualifiers,
    }


def assert_health_claim_supported(text: str) -> Dict[str, Any]:
    """Educate, source, qualify, escalate. Never diagnose, never promise.

    The community pillar this protects is psychological self-healing, where
    the audience is by definition sometimes in distress. Getting this wrong
    costs more than being wrong about a fee schedule.
    """
    assessment = health_claim_assessment(text)
    if assessment["diagnostic"]:
        raise UnsupportedHealthClaimError(
            "content diagnoses the reader. Educate about a mechanism; do not "
            "tell someone what they have."
        )
    if assessment["treatment_claim"]:
        raise UnsupportedHealthClaimError(
            "content promises a cure or displaces professional care. No "
            "healing promises, and never in place of a clinician."
        )
    if assessment["touches_health"] and not assessment["qualifiers"]:
        raise UnsupportedHealthClaimError(
            "content touches health or mental health with no qualifier and no "
            "route to a professional. Add both or drop the claim."
        )
    return assessment


# --------------------------------------------------------------------- #
# Purpose limitation
# --------------------------------------------------------------------- #

def assert_purpose_permitted(
    *, requested_purpose: str, consented_purposes: Sequence[str], subject_ref: str
) -> Dict[str, Any]:
    """Read a person's record only for a purpose they agreed to.

    Relationship memory exists for continuity and service. The same rows read
    for an unagreed purpose are surveillance, and the difference is exactly
    this check.
    """
    requested = (requested_purpose or "").strip().lower()
    if not requested:
        raise PurposeViolationError("a stated purpose is required to read a record")
    permitted = {str(p).strip().lower() for p in consented_purposes}
    if requested not in permitted:
        raise PurposeViolationError(
            f"reading {subject_ref} for '{requested_purpose}' is outside the "
            f"consented purposes {sorted(permitted)}"
        )
    return {"permitted": True, "purpose": requested}


__all__ = [
    "OperationalGuardError", "BudgetExceededError", "SchedulerStaleError",
    "DuplicatePublicationError", "UnsolicitedMessageError",
    "UnsupportedHealthClaimError", "PurposeViolationError",
    "DEFAULT_HEARTBEAT_TOLERANCE_SECONDS",
    "budget_check", "assert_within_budget",
    "scheduler_health", "assert_scheduler_alive",
    "publication_fingerprint", "assert_not_duplicate",
    "assert_dm_permitted",
    "health_claim_assessment", "assert_health_claim_supported",
    "assert_purpose_permitted",
]
