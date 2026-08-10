"""The loop driver for the Infinite Goal Chase.

The loop is: aspiration → observable success → gap map → active gate → shared
primitives → backcast → route tournament → Tiny Yes → external evidence →
learning → capability retained → gate cleared, rerouted, or deferred → harder
aspiration → repeat.

What makes this a scheduler rather than a to-do list is what "infinite" is
not. It is not blind persistence, not machine self-preservation, not
unlimited budget, not unlimited authority, not ignoring falsification, and
not attacking every aspiration at once. Each of those is a way a loop like
this eats an institution, and each is refused here.

So the driver's real output is usually a refusal with a named blocker. It
computes the next legitimate move and declines to invent one when none
exists. A scheduler that always finds something to do is not scheduling; it
is manufacturing motion.

Nothing here executes, publishes, spends, or grants authority. It reads the
registry and says what may happen next.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from db.models import (
    AspirationCampaign,
    AspirationGateEvent,
    AspirationRecord,
    SharedPrimitive,
)
from services.aspiration_registry import (
    BLOCKED_STATUSES,
    TERMINAL_STATUSES,
    AspirationRegistry,
    is_external_evidence,
)
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger
from services.operational_guards import budget_check

logger = get_logger(__name__)

# One aspiration carries the active campaign at a time. Attacking several at
# once is how a portfolio becomes a rout.
MAX_CONCURRENT_CAMPAIGNS = 1

# A route that reality has falsified is not retried. Persistence past a
# falsification is the definition of blind persistence.
FALSIFIED_ROUTES_ARE_FINAL = True


class GoalChaseError(ValueError):
    """The loop was asked to do something the loop is not allowed to do."""


class GoalChaseScheduler:
    """Computes the next legitimate move, or names why there isn't one."""

    def __init__(
        self,
        *,
        registry: Optional[AspirationRegistry] = None,
        ledger: Optional[DecisionLedger] = None,
    ) -> None:
        self.registry = registry or AspirationRegistry(ledger=ledger)
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    # ----------------------------------------------------------------- #
    # Reading the field
    # ----------------------------------------------------------------- #

    def gap_map(self, session: Any) -> Dict[str, Any]:
        """What stands between the current aspirations and reality."""
        aspirations = session.query(AspirationRecord).all()
        live = [a for a in aspirations if a.status not in TERMINAL_STATUSES]
        blocked = [a for a in live if a.status in BLOCKED_STATUSES]
        return {
            "total": len(aspirations),
            "live": len(live),
            "blocked": len(blocked),
            "blocked_by_reason": {
                status: sum(1 for a in blocked if a.status == status)
                for status in sorted({a.status for a in blocked})
            },
            "without_backcast": [a.id for a in live if not a.active_backcast_id],
            "primitives_ranked": self.registry.ranked_primitives(session)[:5],
            "gates_cleared": self.registry.verified_gates_cleared(session),
        }

    def route_tournament(self, session: Any) -> List[Dict[str, Any]]:
        """Rank candidate routes by leverage, not by appeal.

        Leverage is how many live aspirations a primitive unlocks. A route
        whose only dependents are retired is not a route worth walking, and a
        falsified route does not re-enter the tournament.
        """
        falsified_gates = {
            event.gate for event in session.query(AspirationGateEvent).all()
            if event.outcome == "FALSIFIED"
        }
        candidates: List[Dict[str, Any]] = []
        for primitive in session.query(SharedPrimitive).all():
            if primitive.status == "ABANDONED":
                continue
            live_unlocks = 0
            gates: List[str] = []
            for aspiration_id in primitive.unlocks:
                record = session.query(AspirationRecord).filter(
                    lambda row: row.id == aspiration_id
                ).first()
                if record is None or record.status in TERMINAL_STATUSES:
                    continue
                live_unlocks += 1
                if record.current_gate:
                    gates.append(record.current_gate)
            walkable = [g for g in gates
                        if not (FALSIFIED_ROUTES_ARE_FINAL and g in falsified_gates)]
            if not walkable and gates:
                continue  # every gate this primitive fronts has been falsified
            candidates.append({
                "primitive_id": primitive.id,
                "name": primitive.name,
                "disposition": primitive.disposition,
                "live_unlocks": live_unlocks,
                "gates": walkable,
            })
        candidates.sort(key=lambda row: (-row["live_unlocks"], row["name"]))
        return candidates

    # ----------------------------------------------------------------- #
    # The tick
    # ----------------------------------------------------------------- #

    def next_move(
        self,
        session: Any,
        *,
        budget_ceiling: Optional[float] = None,
        budget_committed: float = 0.0,
    ) -> Dict[str, Any]:
        """One tick. Returns the next legitimate move, or the blocker.

        The common outcome is a refusal, and that is correct. Most of the time
        the honest next move belongs to a human.
        """
        live_campaigns = [
            c for c in session.query(AspirationCampaign).all()
            if c.status in ("PREDECLARED", "RUNNING")
        ]

        if len(live_campaigns) >= MAX_CONCURRENT_CAMPAIGNS:
            campaign = live_campaigns[0]
            move = {
                "action": "AWAIT_OUTCOME",
                "campaign_id": campaign.id,
                "aspiration_id": campaign.aspiration_id,
                "gate": campaign.gate,
                "sbm": campaign.sbm,
                "stop_condition": campaign.stop_condition,
                "reason": (
                    "a campaign is already live; the loop runs one gate at a "
                    "time, and attacking several at once is how a portfolio "
                    "becomes a rout"
                ),
            }
            self._record(move)
            return move

        aspirations = session.query(AspirationRecord).all()
        live = [a for a in aspirations if a.status not in TERMINAL_STATUSES]

        if not live:
            return self._blocked(
                "NO_LIVE_ASPIRATION",
                "no aspiration is registered and live; the loop has nothing to "
                "reduce and must not invent something to do",
            )

        actionable = [a for a in live if a.status not in BLOCKED_STATUSES]
        if not actionable:
            return self._blocked(
                "ALL_ASPIRATIONS_BLOCKED",
                "every live aspiration is blocked; the loop does not route "
                "around a wall it has recorded",
                detail={"blocked": {a.id: a.status for a in live}},
            )

        needs_backcast = [a for a in actionable if not a.active_backcast_id]
        if needs_backcast:
            move = {
                "action": "SET_BACKCAST",
                "aspiration_id": needs_backcast[0].id,
                "reason": (
                    "no backcast path exists, so no gate is identified and no "
                    "campaign can name what it is attacking"
                ),
            }
            self._record(move)
            return move

        budget = budget_check(
            ceiling=budget_ceiling, committed=budget_committed, requested=0.0
        )
        if not budget["allowed"] and budget_ceiling is None:
            return self._blocked(
                "NO_BUDGET_CEILING",
                "no resource ceiling is declared; an unbounded loop is the "
                "failure mode, not the feature",
            )

        target = sorted(
            actionable,
            key=lambda a: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.importance, 2),
                a.created_at,
            ),
        )[0]
        move = {
            "action": "PREDECLARE_CAMPAIGN",
            "aspiration_id": target.id,
            "gate": target.current_gate,
            "reason": (
                "one gate, chosen by importance; predeclare all six answers "
                "before anything runs"
            ),
            "required_predeclarations": [
                "aspiration_id", "gate", "sbm",
                "evidence_threshold", "resource_ceiling", "stop_condition",
            ],
            "route_tournament": self.route_tournament(session)[:3],
        }
        self._record(move)
        return move

    def absorb_outcome(self, session: Any, *, event_id: str) -> Dict[str, Any]:
        """Turn a recorded gate outcome into what the loop does next.

        A cleared gate makes the next aspiration harder. A falsified route is
        retired rather than retried. A deferral names what it is waiting for.
        """
        event = session.query(AspirationGateEvent).filter(
            lambda row: row.id == event_id
        ).first()
        if event is None:
            raise GoalChaseError("gate event is not registered")

        if event.outcome == "CLEARED" and is_external_evidence(event.evidence_tier):
            follow_up = {
                "next": "RAISE_AMBITION",
                "rationale": (
                    "capability is retained and becomes substrate; the next "
                    "aspiration on this line should be harder, not a repeat"
                ),
            }
        elif event.outcome == "FALSIFIED":
            follow_up = {
                "next": "RETIRE_ROUTE",
                "rationale": (
                    "reality closed this route; retrying it is blind "
                    "persistence, and the finding is kept so it is not "
                    "rediscovered as new"
                ),
            }
        elif event.outcome == "REROUTED":
            follow_up = {"next": "SET_BACKCAST",
                         "rationale": "the path changed; the gate must be re-derived"}
        else:
            follow_up = {
                "next": "AWAIT_INPUT",
                "rationale": (
                    "deferred without external evidence; name what is being "
                    "waited on rather than looping"
                ),
            }

        result = {
            "event_id": event.id, "aspiration_id": event.aspiration_id,
            "outcome": event.outcome, "evidence_tier": event.evidence_tier,
            "external_evidence": is_external_evidence(event.evidence_tier),
            **follow_up,
        }
        self.ledger.record("goal_chase_outcome_absorbed", result)
        return result

    # ----------------------------------------------------------------- #
    # Internals
    # ----------------------------------------------------------------- #

    def _blocked(
        self, code: str, reason: str, detail: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        move = {"action": "BLOCKED", "code": code, "reason": reason}
        if detail:
            move["detail"] = detail
        self._record(move)
        return move

    def _record(self, move: Dict[str, Any]) -> None:
        self.ledger.record("goal_chase_tick", {
            "action": move.get("action"), "code": move.get("code"),
            "aspiration_id": move.get("aspiration_id"),
            "authority_created": False, "executed": False,
        })


__all__ = [
    "MAX_CONCURRENT_CAMPAIGNS", "FALSIFIED_ROUTES_ARE_FINAL",
    "GoalChaseError", "GoalChaseScheduler",
]
