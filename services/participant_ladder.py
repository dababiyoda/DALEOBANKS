"""The ladder a person can climb through this network, and what each rung costs.

viewer → learner → member → contributor → collaborator → builder → founder →
partner → expert → funder → creator of new infrastructure.

Owned distribution, advancement measurement, community progression, commerce,
collaboration, and venture handoffs are not six systems. They are stages and
transitions on one ladder, and building them separately would mean six copies
of the same person.

What this module is for is refusing claims about people that they did not
earn and did not agree to:

A rung is not reached by being counted. It is reached by a verified,
voluntary action, and an unverified claim stays a claim.

An owned relationship requires recorded consent. Migration off a rented
platform is offered. It is never forced, never tricked, and it is reversible
by the person at any time.

Revenue exists when money moved and was reconciled. An intent, a projection,
and a test fixture are none of those things.

A venture handoff requires six things before it happens, and the sixth is a
place to record that it went badly.

Nobody advances by being enthusiastic, and nobody is retained by being
trapped. Status here rewards contribution, never conformity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import (
    AdvancementAction,
    AudienceSegment,
    CollaborationLink,
    CommerceRecord,
    OwnedRelationship,
    ParticipantRecord,
    TerritoryNode,
    VentureHandoff,
)
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

# The ladder, in order. Position matters: you may skip rungs, but the record
# says which rung and why.
RUNGS = (
    "viewer", "learner", "member", "contributor", "collaborator",
    "builder", "founder", "partner", "expert", "funder", "infrastructure_creator",
)

# Rungs that describe a real relationship rather than passive consumption.
# Reaching one requires consent on record.
CONSENT_REQUIRED_FROM = "member"

CONSENT_STATES = ("NONE", "CONTACT", "RESEARCH", "WITHDRAWN")

# Advancement action types. Each leaves someone more able to act without us.
ADVANCEMENT_TYPES = (
    "emergency_fund_started", "learning_module_completed", "fire_plan_completed",
    "business_validation_started", "credential_obtained", "cohort_joined",
    "opportunity_entered", "collaboration_formed", "practice_completed",
    "ownership_step_taken",
)

HANDOFF_DESTINATIONS = ("pumpstation", "venture_cell", "partner")

# A segment smaller than this identifies people rather than describing a group.
MIN_SEGMENT_POPULATION = 25


class ParticipantLadderError(ValueError):
    """A claim about a person was not earned, not consented to, or not verified."""


class ConsentError(ParticipantLadderError):
    """An action required consent that is not on record."""


class UnreconciledRevenueError(ParticipantLadderError):
    """Money was claimed that has not been reconciled."""


class PrivacyError(ParticipantLadderError):
    """Data was recorded without a stated purpose or retention limit."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def rung_index(rung: str) -> int:
    try:
        return RUNGS.index(rung)
    except ValueError:
        return -1


def consent_required(rung: str) -> bool:
    return rung_index(rung) >= rung_index(CONSENT_REQUIRED_FROM)


class ParticipantLadder:
    """Rungs, advancement, owned relationships, commerce, and handoffs."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    # ----------------------------------------------------------------- #
    # Participants
    # ----------------------------------------------------------------- #

    def register(
        self,
        session: Any,
        *,
        handle_ref: str,
        purposes: Sequence[str],
        retention_until: str,
        language: str = "",
        region: str = "",
    ) -> ParticipantRecord:
        """Record a participant at the bottom rung, with a stated purpose.

        Purpose and retention are required at creation. A record kept because
        it might be useful later is the thing this refuses.
        """
        if not (handle_ref or "").strip():
            raise ParticipantLadderError("handle_ref is required")
        stated = [p for p in purposes if str(p).strip()]
        if not stated:
            raise PrivacyError(
                "a participant record requires at least one stated purpose; "
                "data kept in case it becomes useful is not minimized data"
            )
        if not (retention_until or "").strip():
            raise PrivacyError("a participant record requires a retention limit")

        record = ParticipantRecord(
            handle_ref=handle_ref.strip(), purposes=stated,
            retention_until=retention_until.strip(),
            language=language.strip(), region=region.strip(),
        )
        record.rung_history.append(
            {"rung": "viewer", "reason": "registered", "at": _now().isoformat()}
        )
        session.add(record)
        session.commit()
        self.ledger.record("participant_registered", {
            "participant_id": record.id, "rung": "viewer",
            "purposes": stated, "retention_until": record.retention_until,
        })
        return record

    def record_consent(
        self,
        session: Any,
        *,
        participant_id: str,
        consent_state: str,
        evidence_ref: str,
    ) -> ParticipantRecord:
        """Record consent, or its withdrawal, with evidence."""
        if consent_state not in CONSENT_STATES:
            raise ConsentError(f"consent_state must be one of {list(CONSENT_STATES)}")
        if consent_state != "WITHDRAWN" and not (evidence_ref or "").strip():
            raise ConsentError("granting consent requires an evidence reference")

        record = self._participant(session, participant_id)
        record.consent_state = consent_state
        record.consent_recorded_at = _now().isoformat()
        record.updated_at = _now()

        if consent_state == "WITHDRAWN":
            # Withdrawal is immediate and total across owned channels.
            for rel in session.query(OwnedRelationship).filter(
                lambda row: row.participant_id == record.id and not row.withdrawn
            ).all():
                rel.withdrawn = True
                rel.withdrawn_at = _now().isoformat()
        session.commit()
        self.ledger.record("participant_consent_recorded", {
            "participant_id": record.id, "consent_state": consent_state,
            "owned_relationships_withdrawn": consent_state == "WITHDRAWN",
        })
        return record

    def advance_rung(
        self,
        session: Any,
        *,
        participant_id: str,
        rung: str,
        reason: str,
    ) -> ParticipantRecord:
        """Move someone up the ladder, only on verified evidence.

        A rung above viewer requires at least one verified advancement action.
        A rung at or above member also requires consent on record: a real
        relationship that the person never agreed to is not a relationship.
        """
        if rung_index(rung) < 0:
            raise ParticipantLadderError(f"rung must be one of {list(RUNGS)}")
        if not (reason or "").strip():
            raise ParticipantLadderError("advancing a rung requires a reason")

        record = self._participant(session, participant_id)
        if rung_index(rung) > rung_index("viewer"):
            verified = [
                a for a in session.query(AdvancementAction).filter(
                    lambda row: row.participant_id == record.id
                ).all() if a.verified
            ]
            if not verified:
                raise ParticipantLadderError(
                    f"cannot advance to '{rung}' with no verified advancement action; "
                    f"enthusiasm is not advancement"
                )
        if consent_required(rung) and record.consent_state not in ("CONTACT", "RESEARCH"):
            raise ConsentError(
                f"rung '{rung}' describes a real relationship and requires consent "
                f"on record; current state is '{record.consent_state}'"
            )

        previous = record.rung
        record.rung_history.append({
            "from": previous, "rung": rung, "reason": reason.strip(),
            "at": _now().isoformat(),
        })
        record.rung = rung
        record.updated_at = _now()
        session.commit()
        self.ledger.record("participant_rung_changed", {
            "participant_id": record.id, "from": previous, "to": rung,
            "reason": reason.strip(),
        })
        return record

    # ----------------------------------------------------------------- #
    # Advancement
    # ----------------------------------------------------------------- #

    def record_advancement(
        self,
        session: Any,
        *,
        participant_id: str,
        action_type: str,
        description: str,
        voluntary: bool,
        verification_method: str = "",
        verification_evidence_ref: str = "",
        harm_reported: bool = False,
        recorded_by: str = "",
    ) -> AdvancementAction:
        """Record something a person did. Verified only if evidence exists.

        An involuntary action is never advancement, whatever it produced.
        """
        if action_type not in ADVANCEMENT_TYPES:
            raise ParticipantLadderError(
                f"action_type must be one of {list(ADVANCEMENT_TYPES)}"
            )
        if not voluntary:
            raise ParticipantLadderError(
                "an action the participant did not take voluntarily is not "
                "advancement, regardless of its outcome"
            )
        record = self._participant(session, participant_id)
        verified = bool(
            (verification_method or "").strip()
            and (verification_evidence_ref or "").strip()
            and not harm_reported
        )
        action = AdvancementAction(
            participant_id=record.id, action_type=action_type,
            description=description.strip(), voluntary=True,
            verification_method=verification_method.strip(),
            verification_evidence_ref=verification_evidence_ref.strip(),
            verified=verified, harm_reported=harm_reported,
            occurred_at=_now().isoformat(), recorded_by=recorded_by.strip(),
        )
        session.add(action)
        record.advancement_action_ids.append(action.id)
        record.updated_at = _now()
        session.commit()
        self.ledger.record("advancement_action_recorded", {
            "action_id": action.id, "participant_id": record.id,
            "action_type": action_type, "verified": verified,
            "harm_reported": harm_reported,
            "counts_toward_advancement_rate": verified,
        })
        return action

    def verified_advancement_rate_30d(self, session: Any) -> Dict[str, Any]:
        """VERIFIED_ADVANCEMENT_ACTION_RATE_30D over active participants.

        Counts verified actions only. Returns None rather than 0.0 when there
        is no population — an empty denominator is not a rate of zero.
        """
        cutoff = _now() - timedelta(days=30)
        participants = session.query(ParticipantRecord).all()
        active = [p for p in participants if p.consent_state != "WITHDRAWN"]
        if not active:
            return {"rate": None, "active": 0, "advanced": 0,
                    "note": "no active participants; an empty denominator is not a rate"}
        advanced = 0
        for participant in active:
            actions = session.query(AdvancementAction).filter(
                lambda row: row.participant_id == participant.id
            ).all()
            if any(a.verified and a.occurred_at and a.occurred_at >= cutoff.isoformat()
                   for a in actions):
                advanced += 1
        return {"rate": round(advanced / len(active), 4),
                "active": len(active), "advanced": advanced}

    # ----------------------------------------------------------------- #
    # Owned distribution
    # ----------------------------------------------------------------- #

    def record_owned_relationship(
        self,
        session: Any,
        *,
        participant_id: str,
        channel: str,
        destination_ref: str,
        consent_evidence_ref: str,
        source_surface: str,
        migrated_voluntarily: bool,
    ) -> OwnedRelationship:
        """Record a direct relationship. Consent and volition are required."""
        record = self._participant(session, participant_id)
        if not migrated_voluntarily:
            raise ConsentError(
                "an owned relationship must be entered voluntarily; migration off "
                "a rented platform is offered, never forced or tricked"
            )
        if not (consent_evidence_ref or "").strip():
            raise ConsentError("an owned relationship requires consent evidence")
        if record.consent_state not in ("CONTACT", "RESEARCH"):
            raise ConsentError(
                f"participant consent state is '{record.consent_state}'"
            )
        relationship = OwnedRelationship(
            participant_id=record.id, channel=channel.strip(),
            destination_ref=destination_ref.strip(),
            consent_evidence_ref=consent_evidence_ref.strip(),
            source_surface=source_surface.strip(), migrated_voluntarily=True,
        )
        session.add(relationship)
        session.commit()
        self.ledger.record("owned_relationship_recorded", {
            "relationship_id": relationship.id, "participant_id": record.id,
            "channel": relationship.channel, "voluntary": True,
        })
        return relationship

    def owned_audience_size(self, session: Any) -> int:
        """Live owned relationships. Withdrawn relationships do not count."""
        return sum(
            1 for rel in session.query(OwnedRelationship).all() if not rel.withdrawn
        )

    # ----------------------------------------------------------------- #
    # Commerce
    # ----------------------------------------------------------------- #

    def record_commerce(
        self,
        session: Any,
        *,
        participant_id: str,
        offer: str,
        amount: float,
        reconciliation_ref: str,
        delivered: bool,
        accepted: bool,
        direct_cost: float = 0.0,
        currency: str = "USD",
        repeat: bool = False,
    ) -> CommerceRecord:
        """Record money that actually moved and was reconciled."""
        record = self._participant(session, participant_id)
        if amount <= 0:
            raise UnreconciledRevenueError("a commerce record requires a positive amount")
        if not (reconciliation_ref or "").strip():
            raise UnreconciledRevenueError(
                "revenue requires a reconciliation reference; an intent, a "
                "projection, and a fixture are not payments"
            )
        if not (delivered and accepted):
            raise UnreconciledRevenueError(
                "revenue counts after delivery and acceptance, not at checkout"
            )
        entry = CommerceRecord(
            participant_id=record.id, offer=offer.strip(), amount=float(amount),
            currency=currency, delivered=True, accepted=True, reconciled=True,
            reconciliation_ref=reconciliation_ref.strip(),
            direct_cost=float(direct_cost), repeat=repeat,
            occurred_at=_now().isoformat(),
        )
        session.add(entry)
        session.commit()
        self.ledger.record("commerce_recorded", {
            "commerce_id": entry.id, "participant_id": record.id,
            "amount": entry.amount, "currency": currency, "reconciled": True,
            "repeat": repeat,
        })
        return entry

    def commercial_scorecard(self, session: Any) -> Dict[str, Any]:
        """Reconciled revenue and contribution margin. Refunds subtract."""
        rows = [r for r in session.query(CommerceRecord).all()
                if r.reconciled and not r.refunded]
        revenue = round(sum(r.amount for r in rows), 2)
        cost = round(sum(r.direct_cost for r in rows), 2)
        margin = round(revenue - cost, 2)
        return {
            "reconciled_revenue": revenue,
            "direct_cost": cost,
            "contribution_margin": margin,
            "contribution_margin_ratio": (
                round(margin / revenue, 4) if revenue else None
            ),
            "paying_participants": len({r.participant_id for r in rows}),
            "repeat_purchases": sum(1 for r in rows if r.repeat),
        }

    # ----------------------------------------------------------------- #
    # Collaboration
    # ----------------------------------------------------------------- #

    def record_collaboration(
        self,
        session: Any,
        *,
        participant_ids: Sequence[str],
        kind: str,
        description: str,
        outcome: str = "",
        verification_evidence_ref: str = "",
    ) -> CollaborationLink:
        """Record two or more people who found each other and built something."""
        ids = list(dict.fromkeys(participant_ids))
        if len(ids) < 2:
            raise ParticipantLadderError("a collaboration needs at least two participants")
        for participant_id in ids:
            self._participant(session, participant_id)
        link = CollaborationLink(
            participant_ids=ids, kind=kind.strip(), description=description.strip(),
            outcome=outcome.strip(),
            verification_evidence_ref=verification_evidence_ref.strip(),
            verified=bool((verification_evidence_ref or "").strip()),
        )
        session.add(link)
        session.commit()
        self.ledger.record("collaboration_recorded", {
            "collaboration_id": link.id, "participants": len(ids),
            "kind": link.kind, "verified": link.verified,
        })
        return link

    # ----------------------------------------------------------------- #
    # Venture handoff
    # ----------------------------------------------------------------- #

    def prepare_handoff(
        self,
        session: Any,
        *,
        participant_id: str,
        destination: str,
        need_detected: str,
        eligibility_checked: bool,
        eligibility_note: str,
        disclosure_text: str,
        consent_evidence_ref: str,
        evidence_refs: Optional[Sequence[str]] = None,
    ) -> VentureHandoff:
        """Prepare a warm introduction. Six things must exist first.

        The handoff is prepared, never sent from here. Nothing in this module
        contacts anyone.
        """
        record = self._participant(session, participant_id)
        destination = destination.strip().lower()
        if destination not in HANDOFF_DESTINATIONS:
            raise ParticipantLadderError(
                f"destination must be one of {list(HANDOFF_DESTINATIONS)}"
            )
        missing = []
        if not (need_detected or "").strip():
            missing.append("a detected need")
        if not eligibility_checked:
            missing.append("an eligibility check")
        if not (disclosure_text or "").strip():
            missing.append("a disclosure of the material relationship")
        if not (consent_evidence_ref or "").strip():
            missing.append("recorded consent")
        if missing:
            raise ParticipantLadderError(
                "a handoff requires all of them before it is prepared; missing: "
                + ", ".join(missing)
            )
        if record.consent_state not in ("CONTACT", "RESEARCH"):
            raise ConsentError(
                f"participant consent state is '{record.consent_state}'"
            )

        handoff = VentureHandoff(
            participant_id=record.id, destination=destination,
            need_detected=need_detected.strip(), eligibility_checked=True,
            eligibility_note=eligibility_note.strip(),
            disclosure_text=disclosure_text.strip(),
            consent_evidence_ref=consent_evidence_ref.strip(),
            evidence_refs=list(evidence_refs or []),
        )
        session.add(handoff)
        session.commit()
        self.ledger.record("venture_handoff_prepared", {
            "handoff_id": handoff.id, "participant_id": record.id,
            "destination": destination, "disclosed": True, "consented": True,
            "sent": False,
        })
        return handoff

    def record_handoff_outcome(
        self, session: Any, *, handoff_id: str, status: str, outcome: str
    ) -> VentureHandoff:
        """Record what happened, including when it went badly."""
        allowed = ("SENT", "ACCEPTED", "DECLINED", "WITHDRAWN")
        if status not in allowed:
            raise ParticipantLadderError(f"status must be one of {list(allowed)}")
        handoff = session.query(VentureHandoff).filter(
            lambda row: row.id == handoff_id
        ).first()
        if handoff is None:
            raise ParticipantLadderError("handoff is not registered")
        handoff.status = status
        handoff.outcome = outcome.strip()
        handoff.outcome_recorded_at = _now().isoformat()
        session.commit()
        self.ledger.record("venture_handoff_outcome", {
            "handoff_id": handoff.id, "status": status,
        })
        return handoff

    # ----------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------- #

    @staticmethod
    def _participant(session: Any, participant_id: str) -> ParticipantRecord:
        record = session.query(ParticipantRecord).filter(
            lambda row: row.id == participant_id
        ).first()
        if record is None:
            raise ParticipantLadderError("participant is not registered")
        return record


# --------------------------------------------------------------------- #
# Audience intelligence: aggregate only
# --------------------------------------------------------------------- #

def register_segment(
    session: Any,
    *,
    name: str,
    population: int,
    purpose: str,
    language: str = "",
    region: str = "",
    attributes: Optional[Dict[str, Any]] = None,
    ledger: Optional[DecisionLedger] = None,
) -> AudienceSegment:
    """Record an aggregated segment. Small groups are not segments.

    A segment describing few enough people identifies them, which turns
    audience intelligence into a dossier by arithmetic rather than intent.
    """
    if not (name or "").strip():
        raise ParticipantLadderError("a segment requires a name")
    if not (purpose or "").strip():
        raise PrivacyError("a segment requires a stated purpose")
    if population < MIN_SEGMENT_POPULATION:
        raise PrivacyError(
            f"a segment of {population} identifies people rather than describing "
            f"a group; the floor is {MIN_SEGMENT_POPULATION}"
        )
    segment = AudienceSegment(
        name=name.strip(), population=int(population), purpose=purpose.strip(),
        language=language.strip(), region=region.strip(),
        attributes=dict(attributes or {}),
    )
    session.add(segment)
    session.commit()
    (ledger or get_ledger()).record("audience_segment_registered", {
        "segment_id": segment.id, "name": segment.name,
        "population": segment.population, "purpose": segment.purpose,
    })
    return segment


# --------------------------------------------------------------------- #
# The rabbit hole: a graph that has to let people leave
# --------------------------------------------------------------------- #

def register_territory_node(
    session: Any,
    *,
    title: str,
    surface: str,
    depth: int,
    thesis: str,
    counterargument: str,
    off_ramp: str,
    capability_payload: str,
    content_id: str = "",
    next_node_ids: Optional[Sequence[str]] = None,
    terminal_action: str = "",
    ledger: Optional[DecisionLedger] = None,
) -> TerritoryNode:
    """Add a stop to the participation graph.

    Counterargument, off-ramp, and capability payload are all required. A
    harmful echo chamber narrows what someone can believe; a regenerative
    rabbit hole deepens what they can do. The difference is enforced here
    rather than hoped for.
    """
    missing = []
    if not (thesis or "").strip():
        missing.append("a thesis")
    if not (counterargument or "").strip():
        missing.append("the strongest opposing case")
    if not (off_ramp or "").strip():
        missing.append("an off-ramp")
    if not (capability_payload or "").strip():
        missing.append("something the reader can do")
    if missing:
        raise ParticipantLadderError(
            "a territory node requires all of them; missing: " + ", ".join(missing)
        )
    node = TerritoryNode(
        title=title.strip(), surface=surface.strip(), depth=int(depth),
        thesis=thesis.strip(), counterargument=counterargument.strip(),
        off_ramp=off_ramp.strip(), capability_payload=capability_payload.strip(),
        content_id=content_id.strip(), next_node_ids=list(next_node_ids or []),
        terminal_action=terminal_action.strip(),
    )
    session.add(node)
    session.commit()
    (ledger or get_ledger()).record("territory_node_registered", {
        "node_id": node.id, "depth": node.depth, "surface": node.surface,
        "has_counterargument": True, "has_off_ramp": True,
    })
    return node


_SHARED_LADDER: Optional[ParticipantLadder] = None


def get_participant_ladder() -> ParticipantLadder:
    global _SHARED_LADDER
    if _SHARED_LADDER is None:
        _SHARED_LADDER = ParticipantLadder()
    return _SHARED_LADDER


__all__ = [
    "RUNGS", "CONSENT_STATES", "CONSENT_REQUIRED_FROM", "ADVANCEMENT_TYPES",
    "HANDOFF_DESTINATIONS", "MIN_SEGMENT_POPULATION",
    "ParticipantLadderError", "ConsentError", "UnreconciledRevenueError",
    "PrivacyError", "ParticipantLadder", "rung_index", "consent_required",
    "register_segment", "register_territory_node", "get_participant_ladder",
]
