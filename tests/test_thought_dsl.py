"""Tests for the thought DSL and its gated interpreter."""

from services.ethics_guard import EthicsGuard
from services.ledger import DecisionLedger
from services.thought_dsl import StepKind, ThoughtPlan, ThoughtInterpreter


def _ledger(tmp_path):
    return DecisionLedger(path=str(tmp_path / "ledger.jsonl"))


def test_from_elements_builds_ordered_plan():
    plan = ThoughtPlan.from_elements(
        "improve grid coordination",
        {
            "cta": "join the pilot",
            "problem": "grid operators cannot coordinate",
            "mechanism": "shared dispatch protocol",
            "kpi": "20% fewer curtailments",
            # no pilot, no risk -> skipped, order preserved for the rest
        },
    )

    kinds = [step.kind for step in plan.steps]
    assert kinds == [StepKind.PROBLEM, StepKind.MECHANISM, StepKind.KPI, StepKind.CTA]
    assert plan.to_dict()["goal"] == "improve grid coordination"


def test_interpreter_runs_plan_and_ledgers_every_step(tmp_path):
    ledger = _ledger(tmp_path)
    interpreter = ThoughtInterpreter(EthicsGuard(), ledger=ledger)

    plan = ThoughtPlan.from_elements(
        "test goal",
        {"problem": "a gap", "mechanism": "a fix", "cta": "try it"},
    )
    acted = []
    plan.add_action("Pilot the fix with three cohorts. Rollback if KPIs miss.")

    result = interpreter.run(plan, act_handler=lambda step: acted.append(step.text) or {"ok": True})

    assert result["completed"] is True
    assert len(acted) == 1
    assert all(step.done for step in plan.steps)

    events = [e["event"] for e in ledger.replay()]
    assert events[0] == "plan_start"
    assert events.count("plan_step") == 4
    assert events[-1] == "plan_done"
    ok, _ = ledger.verify_chain()
    assert ok is True


def test_act_step_halts_on_ethics_violation(tmp_path):
    ledger = _ledger(tmp_path)
    interpreter = ThoughtInterpreter(EthicsGuard(), ledger=ledger)

    plan = ThoughtPlan(goal="bad goal")
    plan.add_action("We should attack and destroy the opposing network.")

    acted = []
    result = interpreter.run(plan, act_handler=lambda step: acted.append(step.text))

    assert result["completed"] is False
    assert acted == []
    assert result["halted_on"].startswith("We should attack")
    assert result["reasons"]

    halts = ledger.replay("plan_halt")
    assert len(halts) == 1
    assert halts[0]["payload"]["reason"] == "ethics"


def test_critic_gate_blocks_low_quality_action(tmp_path):
    class BlockingCritic:
        def analyze_quality(self, text, content_type="proposal"):
            class Result:
                quality_score = 0.1
                blocking_issues = ["too vague to act on"]
            return Result()

    ledger = _ledger(tmp_path)
    interpreter = ThoughtInterpreter(EthicsGuard(), critic=BlockingCritic(), ledger=ledger)

    plan = ThoughtPlan(goal="vague goal").add_action("Do something soon, generally.")
    result = interpreter.run(plan)

    assert result["completed"] is False
    assert result["reasons"] == ["too vague to act on"]
    assert ledger.replay("plan_critique")
