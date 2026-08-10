"""The layer whose job is to kill layers.

Every other module here builds something. This one asks whether what was
built earned the right to stay, and it is willing to answer no.

The work is not a masterpiece, because a masterpiece is finished and static.
It is an accumulation: action becomes asset, asset becomes system, system
becomes business, business becomes network, network becomes infrastructure,
and none of those tiers is the destination. Each is a component of a larger
thing that only exists if the components compound.

Compounding is measurable or it is a feeling. A component compounds when it
increases at least one of seven quantities: capability, knowledge, capital,
proof, distribution, autonomy, infrastructure. A component that increases
none of them is decoration, no matter how well it is engineered.

Four rules carry the weight.

Every component declares, before it is built, which of the seven it
increases and what external consequence it should produce. A component that
cannot name its consequence in advance can name any outcome afterwards as
success.

Proof must come from outside this system. A component may not cite another
component as evidence that it worked, and a file in this repository is not a
consequence in the world. Internal coherence is the exact failure mode this
module exists to catch: a system can be perfectly consistent and entirely
imaginary.

Every component carries a deadline. Past it, with no external proof, the
verdict is forced and INTEGRATE is not among the options. What remains is
modify, harvest, or kill.

Nothing is killed unharvested. The lesson is the one asset a failure
reliably produces, and discarding it means paying the tuition twice.

The ceiling is the point. When unproven components accumulate past
ARCHITECTURE_DEBT_CEILING, registration refuses: no new construction until
some of the existing construction has touched the world. Endless
architecture is the most comfortable way to fail, and comfort is what this
removes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import ComponentRecord, HarvestRecord, ProofRecord
from services.aspiration_registry import (
    EVIDENCE_HIERARCHY,
    MINIMUM_GATE_CLEARANCE_TIER,
    evidence_rank,
    is_external_evidence,
)
from services.logging_utils import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------- #

# The hierarchy, lowest to highest. Opus Maximus is not a tier: it is the
# whole, and nothing may be registered as it.
TIERS = (
    "action",
    "asset",
    "system",
    "business",
    "network",
    "infrastructure",
)

# The seven quantities a component may increase. Anything else is decoration.
COMPOUNDING_DIMENSIONS = (
    "capability",
    "knowledge",
    "capital",
    "proof",
    "distribution",
    "autonomy",
    "infrastructure",
)

COMPONENT_STATES = (
    "PROVISIONAL",
    "PROVEN",
    "MODIFIED",
    "HARVESTED",
    "KILLED",
)

# Past deadline, these are the only options. INTEGRATE is deliberately absent.
FORCED_VERDICTS = ("MODIFY", "HARVEST", "KILL")
VERDICTS = ("INTEGRATE",) + FORCED_VERDICTS

# Proof clears at the same bar the aspiration gates use. One hierarchy, one
# bar: a component cannot be easier to prove than a goal.
MINIMUM_PROOF_TIER = MINIMUM_GATE_CLEARANCE_TIER

# The growth path of a single component. The blueprint is free; every step
# above it is earned, and the last two cannot be taken from inside.
MATURITY_LEVELS = (
    "BLUEPRINT",   # mapped, nothing built — always permitted, never a claim
    "SKETCHED",    # partial implementation exists
    "BUILT",       # implemented and covered by tests inside the building
    "EXERCISED",   # ran end to end, in shadow or pilot, on real inputs
    "PROVEN",      # one external consequence recorded
    "HARDENED",    # repeated external proof, and it survived being attacked
)

# Everything from here up requires evidence from outside this system.
FIRST_EXTERNAL_LEVEL = "PROVEN"

# The levels that mean active construction: started, not finished, not proven.
IN_CONSTRUCTION = ("SKETCHED", "BUILT", "EXERCISED")

# What HARDENED costs: repeated proof, plus surviving attack.
HARDENING_PROOF_COUNT = 3
HARDENING_FAILURE_MODES = 1

# How many components may be in active construction at once. This does not
# limit the blueprint — the map should be complete, because a thing with no
# map has nowhere to grow. It limits how much may be half-finished while
# nothing has been proven.
ARCHITECTURE_DEBT_CEILING = 12

# References that describe this system rather than the world.
_INTERNAL_REFERENCE_MARKERS = (
    "services/",
    "tests/",
    "db/",
    "docs/",
    "governance/",
    "daleobanks/",
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    "localhost",
    "127.0.0.1",
    "simulation",
    "simulated",
    "mock",
    "fixture",
    "dry_run",
    "dry-run",
    "shadow",
)


class CompoundingError(ValueError):
    """Base class for refusals in this module."""


class UndeclaredCompoundingError(CompoundingError):
    """A component did not say what it increases, or what should follow."""


class ArchitectureDebtError(CompoundingError):
    """Too much unproven construction already exists to justify more."""


class SelfReferentialProofError(CompoundingError):
    """The evidence offered lives inside the system it is meant to validate."""


class InsufficientProofError(CompoundingError):
    """The evidence is real but too weak to count as external consequence."""


class PrematureMaturityError(CompoundingError):
    """A component was claimed at a level it has not paid for."""


class UnharvestedKillError(CompoundingError):
    """Something is about to be discarded along with what it taught."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def tier_rank(tier: str) -> int:
    """Position in the hierarchy, or -1 when the tier is not one of ours."""
    try:
        return TIERS.index(tier)
    except ValueError:
        return -1


def maturity_rank(level: str) -> int:
    """Position on the growth path, or -1 when the level is not one of ours."""
    try:
        return MATURITY_LEVELS.index(level)
    except ValueError:
        return -1


def requires_external_evidence(level: str) -> bool:
    """True for the levels that cannot be reached from inside the building."""
    return maturity_rank(level) >= maturity_rank(FIRST_EXTERNAL_LEVEL)


def is_internal_reference(reference: str) -> bool:
    """True when a reference points back into this system instead of the world."""
    lowered = (reference or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _INTERNAL_REFERENCE_MARKERS)


class CompoundingLedger:
    """Records components, refuses unproven accumulation, forces verdicts."""

    def __init__(self, ledger: Optional[Any] = None) -> None:
        self._ledger = ledger

    # ----------------------------------------------------------------- #
    # Registration
    # ----------------------------------------------------------------- #

    def _components(self, session: Any) -> List[ComponentRecord]:
        return list(session.query(ComponentRecord).all())

    def unproven(self, session: Any) -> List[ComponentRecord]:
        """Components still carrying a promise they have not kept."""
        return [c for c in self._components(session) if c.state == "PROVISIONAL"]

    def blueprint(self, session: Any) -> List[ComponentRecord]:
        """Everything mapped but not yet started. Always free to grow."""
        return [
            c
            for c in self._components(session)
            if c.maturity == "BLUEPRINT" and c.state != "KILLED"
        ]

    def in_construction(self, session: Any) -> List[ComponentRecord]:
        """Started, unfinished, unproven. The only thing that is rationed."""
        return [
            c
            for c in self._components(session)
            if c.maturity in IN_CONSTRUCTION and c.state != "KILLED"
        ]

    def architecture_debt(self, session: Any) -> int:
        """How much is half-built while nothing it promised has happened."""
        return len(self.in_construction(session))

    def assert_may_construct(self, session: Any) -> None:
        """Refuse to start more while too much is already started and unproven.

        This never blocks the blueprint. Mapping a component is free and
        should be: a thing with no map has nowhere to grow, and the map is
        what future work builds against. What is rationed is construction —
        how many components may sit half-finished while none of them has
        produced a consequence.
        """
        debt = self.architecture_debt(session)
        if debt >= ARCHITECTURE_DEBT_CEILING:
            raise ArchitectureDebtError(
                f"{debt} components are in construction and unproven, ceiling "
                f"is {ARCHITECTURE_DEBT_CEILING}: prove, harden, harvest, or "
                "kill one before starting another (the blueprint stays open)"
            )

    def register(
        self,
        session: Any,
        *,
        name: str,
        tier: str,
        dimensions: Sequence[str],
        expected_external_consequence: str,
        proof_deadline_days: int,
        maturity: str = "BLUEPRINT",
        parent_id: Optional[str] = None,
    ) -> ComponentRecord:
        """Admit a component only once it has said what it owes and by when."""
        if not (name or "").strip():
            raise UndeclaredCompoundingError("a component needs a name")

        if tier not in TIERS:
            raise UndeclaredCompoundingError(
                f"unknown tier {tier!r}: expected one of {', '.join(TIERS)}"
            )

        declared = [d for d in (dimensions or []) if d]
        if not declared:
            raise UndeclaredCompoundingError(
                f"{name}: declare at least one of {', '.join(COMPOUNDING_DIMENSIONS)}"
            )
        unknown = [d for d in declared if d not in COMPOUNDING_DIMENSIONS]
        if unknown:
            raise UndeclaredCompoundingError(
                f"{name}: {', '.join(unknown)} is not a compounding dimension"
            )

        if not (expected_external_consequence or "").strip():
            raise UndeclaredCompoundingError(
                f"{name}: name the external consequence before building, or any "
                "outcome can be called success afterwards"
            )

        if proof_deadline_days is None or proof_deadline_days <= 0:
            raise UndeclaredCompoundingError(
                f"{name}: a component without a proof deadline never comes due"
            )

        if parent_id is not None:
            parent = self.get(session, parent_id)
            if parent is None:
                raise UndeclaredCompoundingError(
                    f"{name}: parent {parent_id} is not in the ledger"
                )
            if tier_rank(parent.tier) < tier_rank(tier):
                raise UndeclaredCompoundingError(
                    f"{name}: a {tier} cannot compose into a {parent.tier}"
                )

        if maturity_rank(maturity) < 0:
            raise PrematureMaturityError(
                f"{name}: {maturity!r} is not on the growth path"
            )
        if requires_external_evidence(maturity):
            raise PrematureMaturityError(
                f"{name}: cannot be registered at {maturity} — that level is "
                "reached by recording external proof, never by declaring it"
            )
        record = ComponentRecord(
            name=name,
            tier=tier,
            dimensions=list(dict.fromkeys(declared)),
            expected_external_consequence=expected_external_consequence.strip(),
            proof_deadline=_now() + timedelta(days=int(proof_deadline_days)),
            state="PROVISIONAL",
            maturity=maturity,
            parent_id=parent_id,
        )
        session.add(record)
        logger.info(
            "component_registered",
            extra={
                "component": name,
                "component_tier": tier,
                "dimensions": record.dimensions,
            },
        )
        return record

    def get(self, session: Any, component_id: str) -> Optional[ComponentRecord]:
        for component in self._components(session):
            if component.id == component_id:
                return component
        return None

    def by_name(self, session: Any, name: str) -> Optional[ComponentRecord]:
        for component in self._components(session):
            if component.name == name:
                return component
        return None

    def compose(
        self, session: Any, child_id: str, parent_id: str
    ) -> ComponentRecord:
        """Attach a component to the larger thing it is part of.

        Separate from registration because the honest build order and the
        composition order run opposite ways: you register the cheapest, most
        concrete work first, and it composes upward into abstractions that do
        not exist yet when it is registered.
        """
        child = self.get(session, child_id)
        parent = self.get(session, parent_id)
        if child is None or parent is None:
            raise CompoundingError("both components must be in the ledger")
        if tier_rank(parent.tier) < tier_rank(child.tier):
            raise UndeclaredCompoundingError(
                f"{child.name}: a {child.tier} cannot compose into a {parent.tier}"
            )
        if parent.id == child.id:
            raise UndeclaredCompoundingError(
                f"{child.name}: a component cannot compose into itself"
            )
        child.parent_id = parent.id
        return child

    # ----------------------------------------------------------------- #
    # Proof
    # ----------------------------------------------------------------- #

    def record_proof(
        self,
        session: Any,
        component_id: str,
        *,
        evidence_tier: str,
        external_reference: str,
        description: str = "",
    ) -> ProofRecord:
        """Admit a consequence only when it happened outside this system."""
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")

        proof = ProofRecord(
            component_id=component_id,
            evidence_tier=evidence_tier,
            external_reference=(external_reference or "").strip(),
            description=description,
        )

        def _reject(reason: str, error: type) -> None:
            proof.admitted = False
            proof.rejection_reason = reason
            component.rejected_proof_count += 1
            session.add(proof)
            raise error(f"{component.name}: {reason}")

        if evidence_rank(evidence_tier) < 0:
            _reject(
                f"{evidence_tier!r} is not on the evidence hierarchy",
                InsufficientProofError,
            )

        if is_internal_reference(proof.external_reference):
            _reject(
                f"{proof.external_reference!r} points back into this system: "
                "a component cannot be its own evidence",
                SelfReferentialProofError,
            )

        for other in self._components(session):
            if other.name and other.name.lower() in proof.external_reference.lower():
                _reject(
                    f"cites component {other.name!r} as evidence: proof must come "
                    "from outside the work, not from another part of it",
                    SelfReferentialProofError,
                )

        if not is_external_evidence(evidence_tier):
            _reject(
                f"{evidence_tier} ranks below {MINIMUM_PROOF_TIER}: real, and "
                "still inside the building",
                InsufficientProofError,
            )

        proof.admitted = True
        component.admitted_proof_count += 1
        if evidence_rank(evidence_tier) > evidence_rank(
            component.best_evidence_tier or ""
        ):
            component.best_evidence_tier = evidence_tier
        if maturity_rank(component.maturity) < maturity_rank("PROVEN"):
            component.maturity = "PROVEN"
        if component.state == "PROVISIONAL":
            component.state = "PROVEN"
            component.verdict = "INTEGRATE"
            component.verdict_reason = (
                f"external consequence recorded at {evidence_tier}"
            )
            component.resolved_at = _now()
        session.add(proof)
        logger.info(
            "component_proven",
            extra={"component": component.name, "evidence_tier": evidence_tier},
        )
        return proof

    def proofs_for(self, session: Any, component_id: str) -> List[ProofRecord]:
        return [
            p
            for p in session.query(ProofRecord).all()
            if p.component_id == component_id
        ]

    # ----------------------------------------------------------------- #
    # Growth: blueprint → sketched → built → exercised → proven → hardened
    # ----------------------------------------------------------------- #

    def advance(
        self,
        session: Any,
        component_id: str,
        *,
        to: str,
        note: str = "",
    ) -> ComponentRecord:
        """Move a component one step up its growth path.

        Three refusals shape this. A level may not be skipped, because the
        skipped step is exactly the work nobody did. The top two levels may
        not be reached through this method at all: PROVEN comes from
        record_proof and HARDENED from harden, both of which need evidence
        from outside. And starting construction counts against the ceiling,
        so a component cannot be quietly nudged into being half-built while
        a dozen other half-built things wait on proof.
        """
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")

        target, current = maturity_rank(to), maturity_rank(component.maturity)
        if target < 0:
            raise PrematureMaturityError(f"{to!r} is not on the growth path")
        if requires_external_evidence(to):
            raise PrematureMaturityError(
                f"{component.name}: {to} is earned by evidence from outside "
                "this system, not by advancing into it"
            )
        if target <= current:
            raise PrematureMaturityError(
                f"{component.name}: already at {component.maturity}, and this "
                "path does not run backwards"
            )
        if target > current + 1:
            raise PrematureMaturityError(
                f"{component.name}: {component.maturity} to {to} skips "
                f"{MATURITY_LEVELS[current + 1]}, which is the step that "
                "would have been the work"
            )
        if to in IN_CONSTRUCTION and component.maturity not in IN_CONSTRUCTION:
            self.assert_may_construct(session)

        component.maturity = to
        if note:
            component.hardening_evidence.append(f"{to}: {note}")
        logger.info(
            "component_advanced",
            extra={"component": component.name, "maturity": to},
        )
        return component

    def harden(
        self,
        session: Any,
        component_id: str,
        *,
        survived_failure_mode: str,
    ) -> ComponentRecord:
        """The last level: proven repeatedly, and it held when attacked.

        A feature that worked once worked once. HARDENED means the external
        consequence repeated, and that the component was put under a named
        failure condition and did not collapse. Both halves are required:
        repetition without adversity is luck, and adversity without
        repetition is an anecdote.
        """
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")
        if component.maturity != "PROVEN":
            raise PrematureMaturityError(
                f"{component.name}: hardening starts from PROVEN, not "
                f"{component.maturity}"
            )
        if not (survived_failure_mode or "").strip():
            raise PrematureMaturityError(
                f"{component.name}: name the failure mode it survived, or "
                "this is a claim that nothing was ever tried against it"
            )

        admitted = [p for p in self.proofs_for(session, component_id) if p.admitted]
        if len(admitted) < HARDENING_PROOF_COUNT:
            raise PrematureMaturityError(
                f"{component.name}: {len(admitted)} external proof(s), "
                f"{HARDENING_PROOF_COUNT} required — once is luck"
            )

        component.survived_failure_modes.append(survived_failure_mode.strip())
        if len(component.survived_failure_modes) < HARDENING_FAILURE_MODES:
            raise PrematureMaturityError(
                f"{component.name}: needs {HARDENING_FAILURE_MODES} survived "
                "failure mode(s)"
            )
        component.maturity = "HARDENED"
        logger.info("component_hardened", extra={"component": component.name})
        return component

    def next_step(self, session: Any, component: ComponentRecord) -> Dict[str, Any]:
        """What this component would have to do to grow one level."""
        rank = maturity_rank(component.maturity)
        if component.maturity == "HARDENED":
            return {"level": None, "requires": "nothing: this one is finished"}
        nxt = MATURITY_LEVELS[rank + 1]
        if nxt == "PROVEN":
            requires = component.expected_external_consequence
        elif nxt == "HARDENED":
            admitted = len(
                [p for p in self.proofs_for(session, component.id) if p.admitted]
            )
            requires = (
                f"{HARDENING_PROOF_COUNT - admitted} more external proof(s), "
                "and one named failure mode survived"
            )
        else:
            requires = f"build it to {nxt.lower()}"
        return {"level": nxt, "requires": requires}

    # ----------------------------------------------------------------- #
    # Verdicts
    # ----------------------------------------------------------------- #

    def adjudicate(
        self, session: Any, *, now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Return the forced decisions on everything that came due unproven."""
        moment = _aware(now) or _now()
        due: List[Dict[str, Any]] = []
        for component in self.unproven(session):
            deadline = _aware(component.proof_deadline)
            if deadline is None or deadline > moment:
                continue
            rejected = component.rejected_proof_count
            if rejected > 0:
                required = "MODIFY"
                reason = (
                    f"{rejected} proof attempt(s) refused: the consequence was "
                    "reached for and missed, so the component is wrong rather "
                    "than untried"
                )
            else:
                required = "HARVEST"
                reason = (
                    "deadline passed with no attempt to show external "
                    "consequence: take the lesson and stop paying for it"
                )
            due.append(
                {
                    "component_id": component.id,
                    "name": component.name,
                    "tier": component.tier,
                    "expected_external_consequence": (
                        component.expected_external_consequence
                    ),
                    "allowed_verdicts": list(FORCED_VERDICTS),
                    "recommended": required,
                    "reason": reason,
                }
            )
        return due

    def modify(
        self, session: Any, component_id: str, *, change: str, extra_days: int
    ) -> ComponentRecord:
        """Keep a component alive only by changing it and re-arming the clock."""
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")
        if not (change or "").strip():
            raise UndeclaredCompoundingError(
                f"{component.name}: name what changes, or this is just an extension"
            )
        if extra_days is None or extra_days <= 0:
            raise UndeclaredCompoundingError(
                f"{component.name}: a modification needs its own deadline"
            )
        component.state = "PROVISIONAL"
        component.verdict = "MODIFY"
        component.verdict_reason = change.strip()
        component.proof_deadline = _now() + timedelta(days=int(extra_days))
        return component

    def harvest(
        self,
        session: Any,
        component_id: str,
        *,
        lesson: str,
        transferable_to: Optional[Sequence[str]] = None,
        cost_paid: str = "",
    ) -> HarvestRecord:
        """Extract what a component taught, whether or not it is kept."""
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")
        if not (lesson or "").strip():
            raise UndeclaredCompoundingError(
                f"{component.name}: a harvest without a lesson is a deletion"
            )
        record = HarvestRecord(
            component_id=component_id,
            lesson=lesson.strip(),
            transferable_to=list(transferable_to or []),
            cost_paid=cost_paid,
        )
        component.harvested = True
        if component.state == "PROVISIONAL":
            component.state = "HARVESTED"
            component.verdict = "HARVEST"
            component.verdict_reason = lesson.strip()
            component.resolved_at = _now()
        session.add(record)
        logger.info("component_harvested", extra={"component": component.name})
        return record

    def kill(self, session: Any, component_id: str, *, reason: str) -> ComponentRecord:
        """Remove a component, but never before its lesson has been taken."""
        component = self.get(session, component_id)
        if component is None:
            raise CompoundingError(f"unknown component {component_id}")
        if not component.harvested:
            raise UnharvestedKillError(
                f"{component.name}: harvest the lesson before killing, or the "
                "tuition gets paid twice"
            )
        component.state = "KILLED"
        component.verdict = "KILL"
        component.verdict_reason = reason or "killed"
        component.resolved_at = _now()
        logger.info("component_killed", extra={"component": component.name})
        return component

    def harvests(self, session: Any) -> List[HarvestRecord]:
        """The knowledge that survived its source."""
        return list(session.query(HarvestRecord).all())

    # ----------------------------------------------------------------- #
    # The honest report
    # ----------------------------------------------------------------- #

    def orphans(self, session: Any) -> List[str]:
        """Components below infrastructure that compose into nothing."""
        components = self._components(session)
        parented = {c.parent_id for c in components if c.parent_id}
        return [
            c.name
            for c in components
            if c.state not in ("KILLED", "HARVESTED")
            and c.parent_id is None
            and c.id not in parented
            and c.tier != "infrastructure"
        ]

    def compounding_report(
        self, session: Any, *, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """State the ratio of built to proven, without rounding it up."""
        components = self._components(session)
        live = [c for c in components if c.state != "KILLED"]
        proven = [c for c in live if c.state == "PROVEN"]

        by_tier: Dict[str, Dict[str, int]] = {}
        for tier in TIERS:
            tier_live = [c for c in live if c.tier == tier]
            by_tier[tier] = {
                "components": len(tier_live),
                "proven": len([c for c in tier_live if c.state == "PROVEN"]),
            }

        proven_dimensions = {d for c in proven for d in c.dimensions}
        claimed_dimensions = {d for c in live for d in c.dimensions}

        ratio = (len(proven) / len(live)) if live else 0.0
        if not live:
            verdict = "EMPTY"
        elif not proven:
            verdict = "ARCHITECTURE_ONLY"
        elif ratio < 0.5:
            verdict = "MOSTLY_UNPROVEN"
        else:
            verdict = "COMPOUNDING"

        by_maturity = {
            level: len([c for c in live if c.maturity == level])
            for level in MATURITY_LEVELS
        }
        frontier = sorted(
            (c for c in live if c.maturity != "HARDENED"),
            key=lambda c: (-maturity_rank(c.maturity), tier_rank(c.tier)),
        )[:5]

        return {
            "verdict": verdict,
            "components": len(live),
            "blueprint_size": len(live),
            "proven": len(proven),
            "by_maturity": by_maturity,
            "in_construction": self.architecture_debt(session),
            "may_construct": self.architecture_debt(session)
            < ARCHITECTURE_DEBT_CEILING,
            "growth_frontier": [
                {
                    "component": c.name,
                    "tier": c.tier,
                    "at": c.maturity,
                    "next": self.next_step(session, c),
                }
                for c in frontier
            ],
            "proof_ratio": round(ratio, 3),
            "architecture_debt": self.architecture_debt(session),
            "architecture_debt_ceiling": ARCHITECTURE_DEBT_CEILING,
            "by_tier": by_tier,
            "highest_proven_tier": max(
                (c.tier for c in proven), key=tier_rank, default=None
            ),
            "dimensions_claimed": sorted(claimed_dimensions),
            "dimensions_proven": sorted(proven_dimensions),
            "dimensions_claimed_but_unproven": sorted(
                claimed_dimensions - proven_dimensions
            ),
            "orphans": self.orphans(session),
            "overdue": self.adjudicate(session, now=now),
            "lessons_banked": len(self.harvests(session)),
        }


__all__ = [
    "ARCHITECTURE_DEBT_CEILING",
    "COMPONENT_STATES",
    "FIRST_EXTERNAL_LEVEL",
    "HARDENING_FAILURE_MODES",
    "HARDENING_PROOF_COUNT",
    "IN_CONSTRUCTION",
    "MATURITY_LEVELS",
    "PrematureMaturityError",
    "maturity_rank",
    "requires_external_evidence",
    "COMPOUNDING_DIMENSIONS",
    "CompoundingError",
    "CompoundingLedger",
    "FORCED_VERDICTS",
    "MINIMUM_PROOF_TIER",
    "TIERS",
    "VERDICTS",
    "ArchitectureDebtError",
    "InsufficientProofError",
    "SelfReferentialProofError",
    "UndeclaredCompoundingError",
    "UnharvestedKillError",
    "is_internal_reference",
    "tier_rank",
]
