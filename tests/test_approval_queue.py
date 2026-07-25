"""Approval queue hygiene: ranked, capped, expiring, deduplicated.
Founder attention is a protected resource; queue overflow and operator
silence never become implicit approval."""

from datetime import datetime, timedelta, UTC

from db.models import ApprovalRequest
from db.session import get_db_session, init_db
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine


def _setup(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    return ledger, line


def test_requests_expire_and_cannot_be_approved(tmp_path):
    ledger, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            request = line.request_approval(
                session, kind="publish", summary="stale ask",
                payload={"draft_id": "d1"}, ttl_hours=1,
            )
            request.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.commit()

            # Any command sweeps first; the stale request closes.
            result = line.handle_command(session, f"YES {request.code}")
            assert result["ok"] is False  # nothing pending to approve

            stored = session.query(ApprovalRequest).filter(
                lambda r: r.id == request.id
            ).first()
        assert stored.status == "expired"
        assert stored.decided_via == "expiry"
        assert ledger.replay("approval_expired")
    finally:
        reset_shared_instances()


def test_duplicate_pending_requests_collapse(tmp_path):
    ledger, line = _setup(tmp_path)
    try:
        with get_db_session() as session:
            first = line.request_approval(
                session, kind="publish", summary="post the thread",
                payload={"draft_id": "d1"},
            )
            second = line.request_approval(
                session, kind="publish", summary="post the thread (again)",
                payload={"draft_id": "d1"},
            )
            assert second.id == first.id  # collapsed, not duplicated
            pending = [r for r in session.query(ApprovalRequest).all()
                       if r.status == "pending"]
        assert len(pending) == 1
    finally:
        reset_shared_instances()


async def test_queue_is_ranked_and_capped_and_overflow_batches(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_ACTIVE_APPROVALS", "3")
    ledger, line = _setup(tmp_path)
    try:
        import app as app_module

        with get_db_session() as session:
            for i in range(5):
                line.request_approval(
                    session, kind="publish", summary=f"ask {i}",
                    payload={"draft_id": f"d{i}"},
                )
            urgent = line.request_approval(
                session, kind="crisis_action", summary="urgent ask",
                payload={"draft_id": "urgent"}, priority="P1",
            )

        response = await app_module.list_operator_requests()
        assert response["count"] == 3  # capped
        assert response["batched_count"] == 3  # overflow batched, visible
        assert response["requests"][0]["id"] == urgent.id  # P1 ranks first
        assert response["requests"][0]["expires_at"] is not None

        # Batched overflow is still pending — never implicitly approved.
        with get_db_session() as session:
            pending = [r for r in session.query(ApprovalRequest).all()
                       if r.status == "pending"]
        assert len(pending) == 6
        assert all(r.status == "pending" for r in pending)
    finally:
        reset_shared_instances()


async def test_strongest_objection_travels_to_the_operator(tmp_path):
    ledger, line = _setup(tmp_path)
    try:
        import app as app_module

        with get_db_session() as session:
            line.request_approval(
                session, kind="publish", summary="post with risk",
                payload={"draft_id": "d9"},
                strongest_objection="Could read as financial advice without disclosure",
            )
        response = await app_module.list_operator_requests()
        assert response["requests"][0]["strongest_objection"].startswith("Could read")
    finally:
        reset_shared_instances()
