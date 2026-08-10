"""The Infinite Goal Chase, made refusable.

An aspiration registry that only stores goals is a wishlist. The reason this
exists is the opposite of storage: it decides what may not be recorded as
progress.

Three rules carry the weight.

Aspirations are never deleted. A blocked aspiration is a finding about the
world — which primitive is missing, which permission is absent, which
coordination failed. Deleting it discards the finding and invites the same
route to be tried again later as though it were new.

A campaign predeclares all six answers before it runs: which aspiration,
which gate, which SBM, which evidence threshold, which resource ceiling,
which stop condition. A campaign that picks its success threshold afterwards
is not evidence; it is a story told about whatever happened.

A gate is cleared only by evidence from outside this process. Simulations,
passing tests, and internal reasoning are legitimate inputs to a decision and
are never the outcome of one. The evidence hierarchy below is the founder's,
transcribed: reconciled real outcome outranks external acceptance outranks
real user behavior, and everything at or below a reproduced test is inside
the building.

Nothing here publishes, spends, or grants authority. It records, and it
refuses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import (
    AspirationCampaign,
    AspirationGateEvent,
    AspirationRecord,
    BackcastPath,
    SharedPrimitive,
)
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------- #

ASPIRATION_STATUSES = (
    "ACTIVE",
    "ACHIEVED",
    "PARTIALLY_ACHIEVED",
    "NEEDS_EVIDENCE",
    "EXPLORATORY",
    "BLOCKED_CURRENT_TECH",
    "BLOCKED_CAPITAL",
    "BLOCKED_PERMISSION",
    "BLOCKED_COORDINATION",
    "BLOCKED_DISTRIBUTION",
    "SUPERSEDED",
    "PROHIBITED_ROUTE",
    "RETIRED",
)

# Statuses that record a wall rather than a conclusion. These are the ones
# most likely to be quietly dropped, so they are named and protected.
BLOCKED_STATUSES = frozenset({
    "BLOCKED_CURRENT_TECH",
    "BLOCKED_CAPITAL",
    "BLOCKED_PERMISSION",
    "BLOCKED_COORDINATION",
    "BLOCKED_DISTRIBUTION",
})

TERMINAL_STATUSES = frozenset({"ACHIEVED", "SUPERSEDED", "PROHIBITED_ROUTE", "RETIRED"})

# Ownership dispositions. Mission progress can exceed ownership value, so
# BUILD is one option among seven rather than the default.
DISPOSITIONS = (
    "BUILD", "PARTNER", "FUND", "OPEN_SOURCE",
    "POPULARIZE", "STANDARDIZE", "PURCHASE", "UNDECIDED",
)

GATE_OUTCOMES = ("CLEARED", "REROUTED", "DEFERRED", "FALSIFIED")

# The founder's business-reality hierarchy, weakest first. Index is rank.
EVIDENCE_HIERARCHY = (
    "aspiration",
    "document",
    "model_reasoning",
    "simulation",
    "reproduced_test",
    "working_prototype",
    "authorized_pilot",
    "real_payment",
    "real_user_behavior",
    "external_acceptance",
    "reconciled_real_outcome",
)

# A gate clears only on evidence at or above this rank. Everything weaker
# happened inside the building.
MINIMUM_GATE_CLEARANCE_TIER = "authorized_pilot"

# The six questions a campaign must answer before it starts.
REQUIRED_PREDECLARATIONS = (
    "aspiration_id", "gate", "sbm",
    "evidence_threshold", "resource_ceiling", "stop_condition",
)


class AspirationRegistryError(ValueError):
    """An aspiration record or claim violated a registry invariant."""


def evidence_rank(tier: str) -> int:
    """Rank a tier in the hierarchy. Unknown tiers rank lowest, not highest."""
    try:
        return EVIDENCE_HIERARCHY.index(tier)
    except ValueError:
        return -1


def is_external_evidence(tier: str) -> bool:
    """True when the tier describes something that happened outside this process."""
    return evidence_rank(tier) >= evidence_rank(MINIMUM_GATE_CLEARANCE_TIER)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AspirationRegistry:
    """Durable aspirations, backcast paths, primitives, and gate outcomes."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    # ----------------------------------------------------------------- #
    # Aspirations
    # ----------------------------------------------------------------- #

    def register(
        self,
        session: Any,
        *,
        founder_statement: str,
        success_state: str,
        owner: str,
        source_lineage: Optional[Sequence[str]] = None,
        importance: str = "medium",
        status: str = "EXPLORATORY",
        **fields: Any,
    ) -> AspirationRecord:
        """Record an aspiration with an observable success state.

        The success state must be observable. "Become influential" is not a
        success state; it is the aspiration restated, and it can never be
        cleared because nothing would count as clearing it.
        """
        statement = (founder_statement or "").strip()
        observable = (success_state or "").strip()
        if not statement:
            raise AspirationRegistryError("founder_statement is required")
        if not observable:
            raise AspirationRegistryError(
                "success_state is required and must describe an observable outcome"
            )
        if not (owner or "").strip():
            raise AspirationRegistryError("owner is required")
        self._validate_status(status)

        record = AspirationRecord(
            founder_statement=statement,
            success_state=observable,
            owner=owner.strip(),
            source_lineage=list(source_lineage or []),
            importance=importance,
            status=status,
            **fields,
        )
        record.status_history.append({
            "status": status, "reason": "registered",
            "at": _now().isoformat(), "actor": owner.strip(),
        })
        session.add(record)
        session.commit()
        self.ledger.record("aspiration_registered", {
            "aspiration_id": record.id, "status": status,
            "importance": importance, "owner": record.owner,
        })
        return record

    def set_status(
        self,
        session: Any,
        *,
        aspiration_id: str,
        status: str,
        reason: str,
        actor: str,
    ) -> AspirationRecord:
        """Change status, keeping the prior status and the reason.

        There is no delete. A blocked aspiration that stops being visible
        stops being a finding, and the same route gets rediscovered later as
        though nobody had tried it.
        """
        self._validate_status(status)
        if not (reason or "").strip():
            raise AspirationRegistryError("a status change requires a reason")
        if not (actor or "").strip():
            raise AspirationRegistryError("a status change requires an actor")

        record = self._aspiration(session, aspiration_id)
        previous = record.status
        record.status_history.append({
            "from": previous, "status": status, "reason": reason.strip(),
            "at": _now().isoformat(), "actor": actor.strip(),
        })
        record.status = status
        record.updated_at = _now()
        session.commit()
        self.ledger.record("aspiration_status_changed", {
            "aspiration_id": record.id, "from": previous, "to": status,
            "reason": reason.strip(), "actor": actor.strip(),
            "was_blocked": previous in BLOCKED_STATUSES,
            "history_preserved": True,
        })
        return record

    # ----------------------------------------------------------------- #
    # Backcast GPS
    # ----------------------------------------------------------------- #

    def set_backcast(
        self,
        session: Any,
        *,
        aspiration_id: str,
        success_state: str,
        stages: Sequence[Dict[str, Any]],
        repeatable_system: str,
    ) -> BackcastPath:
        """Attach G, P, S. Revising supersedes rather than overwrites.

        The nearest stage is last: the path is walked backwards from the
        success state, and the gate standing closest to today is the one any
        campaign is allowed to attack.
        """
        record = self._aspiration(session, aspiration_id)
        if not (success_state or "").strip():
            raise AspirationRegistryError("backcast requires an observable success state (G)")
        staged = [dict(stage) for stage in stages]
        if not staged:
            raise AspirationRegistryError("backcast requires at least one stage (P)")
        for index, stage in enumerate(staged):
            if not str(stage.get("gate", "")).strip():
                raise AspirationRegistryError(f"stage {index} is missing a gate")
        if not (repeatable_system or "").strip():
            raise AspirationRegistryError(
                "backcast requires a small repeatable system that weakens the current gate (S)"
            )

        nearest_gate = str(staged[-1]["gate"]).strip()
        path = BackcastPath(
            aspiration_id=record.id,
            success_state=success_state.strip(),
            stages=staged,
            repeatable_system=repeatable_system.strip(),
            current_gate=nearest_gate,
        )
        session.add(path)

        if record.active_backcast_id:
            prior = session.query(BackcastPath).filter(
                lambda row: row.id == record.active_backcast_id
            ).first()
            if prior is not None:
                prior.superseded_by = path.id

        record.active_backcast_id = path.id
        record.current_gate = nearest_gate
        record.updated_at = _now()
        session.commit()
        self.ledger.record("backcast_path_set", {
            "aspiration_id": record.id, "backcast_id": path.id,
            "current_gate": nearest_gate, "stage_count": len(staged),
        })
        return path

    # ----------------------------------------------------------------- #
    # Shared primitives
    # ----------------------------------------------------------------- #

    def register_primitive(
        self,
        session: Any,
        *,
        name: str,
        description: str,
        unlocks: Sequence[str],
        category: str = "",
        disposition: str = "UNDECIDED",
        disposition_rationale: str = "",
    ) -> SharedPrimitive:
        """Record a bottleneck and which aspirations it stands in front of."""
        if not (name or "").strip():
            raise AspirationRegistryError("primitive name is required")
        if disposition not in DISPOSITIONS:
            raise AspirationRegistryError(
                f"disposition must be one of {sorted(DISPOSITIONS)}"
            )
        if disposition != "UNDECIDED" and not (disposition_rationale or "").strip():
            raise AspirationRegistryError(
                "choosing a disposition requires a rationale"
            )
        unlock_ids = list(dict.fromkeys(unlocks))
        for aspiration_id in unlock_ids:
            self._aspiration(session, aspiration_id)  # must exist

        primitive = SharedPrimitive(
            name=name.strip(), description=description.strip(),
            category=category.strip(), unlocks=unlock_ids,
            disposition=disposition,
            disposition_rationale=disposition_rationale.strip(),
        )
        session.add(primitive)
        for aspiration_id in unlock_ids:
            record = self._aspiration(session, aspiration_id)
            if primitive.name not in record.missing_primitives:
                record.missing_primitives.append(primitive.name)
                record.updated_at = _now()
        session.commit()
        self.ledger.record("shared_primitive_registered", {
            "primitive_id": primitive.id, "name": primitive.name,
            "unlock_count": len(unlock_ids), "disposition": disposition,
        })
        return primitive

    def ranked_primitives(self, session: Any) -> List[Dict[str, Any]]:
        """Primitives ordered by how many live aspirations they unlock.

        Terminal aspirations do not count toward leverage — a primitive whose
        only dependents are retired or achieved is not a bottleneck.
        """
        primitives = session.query(SharedPrimitive).all()
        ranked = []
        for primitive in primitives:
            live = 0
            for aspiration_id in primitive.unlocks:
                record = session.query(AspirationRecord).filter(
                    lambda row: row.id == aspiration_id
                ).first()
                if record is not None and record.status not in TERMINAL_STATUSES:
                    live += 1
            ranked.append({
                "id": primitive.id, "name": primitive.name,
                "disposition": primitive.disposition, "status": primitive.status,
                "unlocks_total": len(primitive.unlocks),
                "unlocks_live": live,
            })
        ranked.sort(key=lambda row: (-row["unlocks_live"], row["name"]))
        return ranked

    # ----------------------------------------------------------------- #
    # Campaigns
    # ----------------------------------------------------------------- #

    def predeclare_campaign(
        self,
        session: Any,
        *,
        aspiration_id: str,
        gate: str,
        sbm: str,
        evidence_threshold: str,
        resource_ceiling: str,
        stop_condition: str,
        hypothesis: str = "",
    ) -> AspirationCampaign:
        """Predeclare a campaign. All six answers, before anything runs."""
        record = self._aspiration(session, aspiration_id)
        candidate = {
            "aspiration_id": aspiration_id, "gate": gate, "sbm": sbm,
            "evidence_threshold": evidence_threshold,
            "resource_ceiling": resource_ceiling,
            "stop_condition": stop_condition,
        }
        missing = [key for key in REQUIRED_PREDECLARATIONS
                   if not str(candidate.get(key) or "").strip()]
        if missing:
            raise AspirationRegistryError(
                "a campaign must predeclare all six answers before it runs; missing: "
                + ", ".join(sorted(missing))
            )
        if record.status in TERMINAL_STATUSES:
            raise AspirationRegistryError(
                f"aspiration is {record.status}; a terminal aspiration cannot run a campaign"
            )
        if record.current_gate and gate.strip() != record.current_gate:
            raise AspirationRegistryError(
                f"campaign attacks '{gate.strip()}' but the aspiration's current gate is "
                f"'{record.current_gate}'; reroute the backcast first"
            )

        # One dominant SBM per operating period. A second live campaign under
        # a different SBM means nothing is actually the bottleneck.
        live = [row for row in session.query(AspirationCampaign).all()
                if row.status in ("PREDECLARED", "RUNNING")]
        conflicting = [row.sbm for row in live if row.sbm != sbm.strip()]
        if conflicting:
            raise AspirationRegistryError(
                f"an operating period carries one dominant SBM; '{sorted(set(conflicting))[0]}' "
                f"is already live. Conclude it before predeclaring '{sbm.strip()}'"
            )

        campaign = AspirationCampaign(
            aspiration_id=record.id, gate=gate.strip(), sbm=sbm.strip(),
            evidence_threshold=evidence_threshold.strip(),
            resource_ceiling=resource_ceiling.strip(),
            stop_condition=stop_condition.strip(),
            hypothesis=hypothesis.strip(),
        )
        session.add(campaign)
        record.active_sbm = campaign.sbm
        record.updated_at = _now()
        session.commit()
        self.ledger.record("aspiration_campaign_predeclared", {
            "campaign_id": campaign.id, "aspiration_id": record.id,
            "gate": campaign.gate, "sbm": campaign.sbm,
            "evidence_threshold": campaign.evidence_threshold,
            "resource_ceiling": campaign.resource_ceiling,
            "stop_condition": campaign.stop_condition,
            "authority_created": False,
        })
        return campaign

    # ----------------------------------------------------------------- #
    # Outcomes
    # ----------------------------------------------------------------- #

    def record_gate_outcome(
        self,
        session: Any,
        *,
        campaign_id: str,
        outcome: str,
        evidence_tier: str,
        narrative: str,
        recorded_by: str,
        external_evidence_refs: Optional[Sequence[str]] = None,
    ) -> AspirationGateEvent:
        """Record what reality said. CLEARED needs evidence from outside.

        REROUTED, DEFERRED, and FALSIFIED are first-class results and accept
        any evidence tier — learning that a route does not work is a real
        outcome. Only CLEARED makes a claim about the world, so only CLEARED
        has to prove it.
        """
        outcome = (outcome or "").strip().upper()
        if outcome not in GATE_OUTCOMES:
            raise AspirationRegistryError(f"outcome must be one of {sorted(GATE_OUTCOMES)}")
        if evidence_rank(evidence_tier) < 0:
            raise AspirationRegistryError(
                f"evidence_tier must be one of {list(EVIDENCE_HIERARCHY)}"
            )
        if not (narrative or "").strip() or not (recorded_by or "").strip():
            raise AspirationRegistryError("narrative and recorded_by are required")

        campaign = session.query(AspirationCampaign).filter(
            lambda row: row.id == campaign_id
        ).first()
        if campaign is None:
            raise AspirationRegistryError("campaign is not registered")
        if campaign.status == "CONCLUDED":
            raise AspirationRegistryError("campaign already concluded")

        refs = list(dict.fromkeys(external_evidence_refs or []))
        if outcome == "CLEARED":
            if not is_external_evidence(evidence_tier):
                raise AspirationRegistryError(
                    f"a gate cannot be cleared on '{evidence_tier}' evidence; clearing requires "
                    f"'{MINIMUM_GATE_CLEARANCE_TIER}' or stronger. Internal results are inputs "
                    f"to a decision, never the outcome of one"
                )
            if not refs:
                raise AspirationRegistryError(
                    "clearing a gate requires at least one external evidence reference"
                )

        event = AspirationGateEvent(
            aspiration_id=campaign.aspiration_id, campaign_id=campaign.id,
            gate=campaign.gate, outcome=outcome, evidence_tier=evidence_tier,
            external_evidence_refs=refs, narrative=narrative.strip(),
            recorded_by=recorded_by.strip(),
        )
        session.add(event)
        campaign.status = "CONCLUDED"
        campaign.outcome_event_id = event.id
        campaign.concluded_at = _now()

        record = self._aspiration(session, campaign.aspiration_id)
        record.active_sbm = ""
        if outcome == "CLEARED":
            record.current_evidence.extend(refs)
        record.updated_at = _now()
        session.commit()
        self.ledger.record("aspiration_gate_outcome", {
            "event_id": event.id, "campaign_id": campaign.id,
            "aspiration_id": record.id, "gate": event.gate, "outcome": outcome,
            "evidence_tier": evidence_tier,
            "external_evidence": is_external_evidence(evidence_tier),
            "counts_toward_verified_gates_cleared": outcome == "CLEARED",
        })
        return event

    def verified_gates_cleared(self, session: Any) -> int:
        """VERIFIED_ASPIRATION_GATES_CLEARED. Counts only external clearances."""
        return sum(
            1 for event in session.query(AspirationGateEvent).all()
            if event.outcome == "CLEARED" and is_external_evidence(event.evidence_tier)
        )

    def public_aspiration(self, session: Any, aspiration_id: str) -> Dict[str, Any]:
        record = self._aspiration(session, aspiration_id)
        return {
            "id": record.id,
            "founder_statement": record.founder_statement,
            "success_state": record.success_state,
            "status": record.status,
            "importance": record.importance,
            "current_gate": record.current_gate,
            "active_sbm": record.active_sbm,
            "active_backcast_id": record.active_backcast_id,
            "missing_primitives": list(record.missing_primitives),
            "current_evidence": list(record.current_evidence),
            "dependencies": list(record.dependencies),
            "legal_constraints": list(record.legal_constraints),
            "safety_constraints": list(record.safety_constraints),
            "unlock_relationships": list(record.unlock_relationships),
            "resource_budget": record.resource_budget,
            "review_trigger": record.review_trigger,
            "owner": record.owner,
            "status_history": list(record.status_history),
            "source_lineage": list(record.source_lineage),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    # ----------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------- #

    @staticmethod
    def _validate_status(status: str) -> str:
        if status not in ASPIRATION_STATUSES:
            raise AspirationRegistryError(
                f"status must be one of {list(ASPIRATION_STATUSES)}"
            )
        return status

    @staticmethod
    def _aspiration(session: Any, aspiration_id: str) -> AspirationRecord:
        record = session.query(AspirationRecord).filter(
            lambda row: row.id == aspiration_id
        ).first()
        if record is None:
            raise AspirationRegistryError("aspiration is not registered")
        return record


_SHARED_REGISTRY: Optional[AspirationRegistry] = None


def get_aspiration_registry() -> AspirationRegistry:
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = AspirationRegistry()
    return _SHARED_REGISTRY


__all__ = [
    "ASPIRATION_STATUSES", "BLOCKED_STATUSES", "TERMINAL_STATUSES",
    "DISPOSITIONS", "GATE_OUTCOMES", "EVIDENCE_HIERARCHY",
    "MINIMUM_GATE_CLEARANCE_TIER", "REQUIRED_PREDECLARATIONS",
    "AspirationRegistry", "AspirationRegistryError",
    "evidence_rank", "is_external_evidence", "get_aspiration_registry",
]
