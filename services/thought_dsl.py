"""A tiny plan DSL + interpreter: makes the agent's reasoning inspectable.

A ThoughtPlan is an ordered list of typed steps mirroring the Critic's
proposal grammar (problem → mechanism → pilot → kpi → risk → cta), plus ACT
steps that produce outbound actions. The interpreter executes steps one at a
time, gating every ACT through the EthicsGuard and logging every step to the
decision ledger — nothing acts until it has been checked and recorded. Plans
are plain data: serialisable, diffable, replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from services.ledger import DecisionLedger
from services.logging_utils import get_logger

logger = get_logger(__name__)


class StepKind(str, Enum):
    PROBLEM = "problem"
    MECHANISM = "mechanism"
    PILOT = "pilot"
    KPI = "kpi"
    RISK = "risk"
    CTA = "cta"
    ACT = "act"  # a step that produces an outbound action


# Canonical ordering of the reasoning steps (the Critic's PMPKRC grammar).
ELEMENT_ORDER = [
    StepKind.PROBLEM,
    StepKind.MECHANISM,
    StepKind.PILOT,
    StepKind.KPI,
    StepKind.RISK,
    StepKind.CTA,
]


@dataclass
class ThoughtStep:
    kind: StepKind
    text: str
    done: bool = False
    result: Optional[Dict[str, Any]] = None


@dataclass
class ThoughtPlan:
    goal: str
    steps: List[ThoughtStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [
                {"kind": s.kind.value, "text": s.text, "done": s.done}
                for s in self.steps
            ],
        }

    def add_action(self, text: str) -> "ThoughtPlan":
        """Append an outbound ACT step (e.g. the content to publish)."""
        self.steps.append(ThoughtStep(kind=StepKind.ACT, text=text))
        return self

    @staticmethod
    def from_elements(goal: str, elements: Dict[str, str]) -> "ThoughtPlan":
        """Build a plan from a problem→mechanism→pilot→kpi→risk→cta dict."""
        steps = [
            ThoughtStep(kind=kind, text=elements[kind.value])
            for kind in ELEMENT_ORDER
            if elements.get(kind.value)
        ]
        return ThoughtPlan(goal=goal, steps=steps)


class ThoughtInterpreter:
    """Executes a ThoughtPlan step-by-step, gated and logged."""

    def __init__(
        self,
        ethics_guard: Any,
        critic: Any = None,
        ledger: Optional[DecisionLedger] = None,
    ) -> None:
        self.ethics = ethics_guard
        self.critic = critic
        self.ledger = ledger or DecisionLedger()

    def run(
        self,
        plan: ThoughtPlan,
        act_handler: Optional[Callable[[ThoughtStep], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute the plan. Returns a trace. Halts on the first failed gate."""

        self.ledger.record("plan_start", plan.to_dict())
        trace: List[Dict[str, Any]] = []

        for step in plan.steps:
            self.ledger.record(
                "plan_step",
                {
                    "goal": plan.goal,
                    "kind": step.kind.value,
                    "text": step.text[:200],
                },
            )

            if step.kind == StepKind.ACT:
                halt = self._gate_action(plan, step)
                if halt is not None:
                    trace.append(halt)
                    return {
                        "completed": False,
                        "trace": trace,
                        "halted_on": step.text,
                        "reasons": halt.get("reasons", []),
                    }
                if act_handler:
                    step.result = act_handler(step)

            step.done = True
            trace.append({"kind": step.kind.value, "done": True})

        self.ledger.record("plan_done", {"goal": plan.goal, "steps": len(plan.steps)})
        return {"completed": True, "trace": trace}

    def _gate_action(self, plan: ThoughtPlan, step: ThoughtStep) -> Optional[Dict[str, Any]]:
        """Ethics (mandatory) + critic (advisory) checks before an ACT step.

        Returns a halt-trace entry when the step must not run, else None.
        """
        ethics_result = self.ethics.validate_text(step.text)
        if not ethics_result.approved:
            self.ledger.record(
                "plan_halt",
                {
                    "goal": plan.goal,
                    "reason": "ethics",
                    "details": ethics_result.reasons,
                },
            )
            logger.warning("Plan '%s' halted by ethics gate: %s", plan.goal, ethics_result.reasons)
            return {
                "kind": step.kind.value,
                "halted": "ethics",
                "reasons": list(ethics_result.reasons),
            }

        if self.critic is not None:
            try:
                critique = self.critic.analyze_quality(step.text, "proposal")
                self.ledger.record(
                    "plan_critique",
                    {
                        "goal": plan.goal,
                        "quality_score": critique.quality_score,
                        "blocking_issues": critique.blocking_issues,
                    },
                )
                if critique.blocking_issues:
                    logger.warning(
                        "Plan '%s' halted by critic: %s", plan.goal, critique.blocking_issues
                    )
                    return {
                        "kind": step.kind.value,
                        "halted": "critic",
                        "reasons": list(critique.blocking_issues),
                    }
            except Exception as exc:  # critic is advisory; never crash a plan
                logger.error(f"Critic gate failed open: {exc}")
        return None


__all__ = ["StepKind", "ThoughtStep", "ThoughtPlan", "ThoughtInterpreter", "ELEMENT_ORDER"]
