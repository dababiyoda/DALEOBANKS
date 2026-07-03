"""Tests for the constitution guard and gated goal autonomy."""

import pytest
from fastapi import HTTPException

from config import get_config, update_config
from db.models import GoalProposal
from db.session import get_db_session, init_db
from services.constitution import ConstitutionGuard
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    set_shared_instances,
    reset_shared_instances,
)


def _guard(tmp_path, text="# Constitution\n\n1. Fail toward silence.\n"):
    path = tmp_path / "constitution.md"
    path.write_text(text)
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    guard = ConstitutionGuard(
        str(path), ledger=ledger, kill_switch=KillSwitch(ledger=ledger)
    )
    return guard, ledger, path


def test_startup_hash_is_ledgered(tmp_path):
    guard, ledger, _ = _guard(tmp_path)

    recorded = guard.load_and_record()

    assert recorded == guard.current_hash()
    events = ledger.replay("constitution_hash")
    assert len(events) == 1
    assert events[0]["payload"]["hash"] == recorded


def test_unchanged_constitution_verifies(tmp_path):
    guard, _, _ = _guard(tmp_path)
    guard.load_and_record()
    assert guard.verify() is True
    assert get_config().LIVE is get_config().LIVE  # no side effects


def test_runtime_tampering_disarms(tmp_path):
    guard, ledger, path = _guard(tmp_path)
    guard.load_and_record()

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)
        path.write_text("# Constitution\n\n1. Post as much as possible.\n")

        assert guard.verify() is False
        assert get_config().LIVE is False
        tampered = ledger.replay("constitution_tampered")
        assert len(tampered) == 1
        assert tampered[0]["payload"]["expected"] != tampered[0]["payload"]["found"]
    finally:
        update_config(LIVE=previous)


def test_repo_constitution_exists_and_names_the_invariants():
    guard = ConstitutionGuard()
    text = guard.text()
    assert "Fail toward silence" in text
    assert "human owns arming" in text.lower()
    assert guard.current_hash() is not None


def test_planner_files_proposals_instead_of_rewriting_goals(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))

    from services.planner import PlannerService

    planner = PlannerService(ledger=ledger)

    with get_db_session() as session:
        # No approved proposals: default OKR is active.
        active = planner.get_active_okr(session)
        assert active == planner.default_okr

        proposed = dict(planner.default_okr)
        proposed["key_results"] = list(proposed["key_results"])
        proposed["key_results"][0] = "Generate 8 high-quality proposal posts"
        planner._file_goal_proposal(session, proposed, "test rationale")
        planner._file_goal_proposal(session, proposed, "duplicate")  # idempotent

        pending = session.query(GoalProposal).filter(lambda p: p.status == "pending").all()
        assert len(pending) == 1

        # Still not active until approved.
        assert planner.get_active_okr(session) == planner.default_okr

        pending[0].status = "approved"
        session.commit()

        assert planner.get_active_okr(session)["key_results"][0] == (
            "Generate 8 high-quality proposal posts"
        )

    assert len(ledger.replay("okr_proposal")) == 1


async def test_goal_decision_endpoint(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        with get_db_session() as session:
            proposal = GoalProposal(
                proposal={"objective": "new"}, rationale="why not"
            )
            session.add(proposal)
            session.commit()
            proposal_id = proposal.id

        listing = await app_module.list_goal_proposals(status_filter="pending", _=None)
        assert listing["count"] == 1

        result = await app_module.decide_goal_proposal(
            proposal_id, app_module.DecisionRequest(approve=False), None
        )
        assert result["status"] == "rejected"
        assert ledger.replay("okr_decision")[0]["payload"]["decision"] == "rejected"

        with pytest.raises(HTTPException) as exc_info:
            await app_module.decide_goal_proposal(
                proposal_id, app_module.DecisionRequest(approve=True), None
            )
        assert exc_info.value.status_code == 409
    finally:
        reset_shared_instances()
