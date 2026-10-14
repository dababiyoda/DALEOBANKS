"""Gate evidence #7 and #8.

#7 — the complete shadow DecisionEpisode survives a process restart: the
store and the ledger are reopened from disk, the episode reconstructs with
the same stages, the chain verifies, and a grant spent before the restart
is still spent after it.

#8 — concurrent use cannot exceed a grant: many threads racing on one
grant consume exactly maximum_uses, never more.
"""

import threading

import pytest

from db.models import CapabilityGrant
from db.session import get_db_session, init_db
from services.capability import CapabilityError, CapabilityService
from services.decision_episode import build_episode
from services.ledger import DecisionLedger, KillSwitch, set_shared_instances, reset_shared_instances
from services.operator_line import OperatorLine
from tests.test_shadow_loop import _shadow_loop


def test_shadow_episode_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSIST_STORE", "true")
    monkeypatch.setenv("DB_SNAPSHOT_PATH", str(tmp_path / "store.jsonl"))
    ledger_path = str(tmp_path / "ledger.jsonl")

    ledger = DecisionLedger(path=ledger_path)
    set_shared_instances(ledger=ledger)
    try:
        packet, grant, _approval, draft_id = _shadow_loop(ledger, CapabilityService(ledger=ledger))
        with get_db_session() as session:
            before = build_episode(session, packet.id, ledger=ledger)
    finally:
        reset_shared_instances()

    # Restart: memory cleared, store and ledger reopened from disk only.
    init_db()
    reopened = DecisionLedger(path=ledger_path)
    set_shared_instances(ledger=reopened)
    try:
        chain_ok, _ = reopened.verify_chain()
        assert chain_ok is True

        with get_db_session() as session:
            after = build_episode(session, packet.id, ledger=reopened)
            assert after is not None
            assert after["missing_stages"] == before["missing_stages"]
            assert after["loop_closed"] is True
            assert after["shadow_only"] is True and after["externally_closed"] is False
            assert after["capability_grant"][0]["id"] == grant.id
            assert len(after["ledger_events"]) == len(before["ledger_events"])

            # Spent before the restart, still spent after it.
            restored = session.query(CapabilityGrant).filter(lambda g: g.id == grant.id).first()
            assert restored.uses_consumed == 1
            with pytest.raises(CapabilityError):
                CapabilityService(ledger=reopened).validate_and_consume(
                    session, grant.id, "publish_post", draft_id, target="lane-main",
                )
    finally:
        reset_shared_instances()


class _SlowTargets(list):
    """Widens the window between the use-count check and the increment, so
    a missing lock shows up deterministically instead of by luck."""

    def __contains__(self, item):
        threading.Event().wait(0.02)
        return super().__contains__(item)


def test_concurrent_consumption_cannot_exceed_the_grant(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    service = CapabilityService(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    try:
        with get_db_session() as session:
            request = line.request_approval(
                session, kind="publish", summary="Publish one draft, three times at most",
                payload={"draft_id": "draft-c"},
            )
            line.handle_command(session, f"YES {request.code}")
            grant = service.mint_from_approval(
                session, request.id, "publish_post", "publish draft-c", "draft-c",
                named_targets=["lane-main"], maximum_uses=3,
            )
            grant.named_targets = _SlowTargets(grant.named_targets)

        threads, start = 12, threading.Barrier(12)
        outcomes = []

        def attempt():
            start.wait()
            with get_db_session() as session:
                try:
                    service.validate_and_consume(
                        session, grant.id, "publish_post", "draft-c", target="lane-main",
                    )
                    outcomes.append("ok")
                except CapabilityError:
                    outcomes.append("refused")

        workers = [threading.Thread(target=attempt) for _ in range(threads)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        assert outcomes.count("ok") == 3
        assert outcomes.count("refused") == threads - 3
        assert grant.uses_consumed == 3
        assert len(ledger.replay("capability_consumed")) == 3
    finally:
        reset_shared_instances()


def test_revocation_racing_consumption_leaves_no_use_after_revoke(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "l.jsonl"))
    set_shared_instances(ledger=ledger)
    service = CapabilityService(ledger=ledger)
    line = OperatorLine(ledger=ledger, kill_switch=KillSwitch(ledger=ledger))
    try:
        with get_db_session() as session:
            request = line.request_approval(
                session, kind="publish", summary="Publish one draft, revocable",
                payload={"draft_id": "draft-r"},
            )
            line.handle_command(session, f"YES {request.code}")
            grant = service.mint_from_approval(
                session, request.id, "publish_post", "publish draft-r", "draft-r",
                named_targets=["lane-main"], maximum_uses=10,
            )
            grant.named_targets = _SlowTargets(grant.named_targets)

        start = threading.Barrier(9)

        def consume():
            start.wait()
            with get_db_session() as session:
                try:
                    service.validate_and_consume(
                        session, grant.id, "publish_post", "draft-r", target="lane-main",
                    )
                except CapabilityError:
                    pass

        def revoke():
            start.wait()
            with get_db_session() as session:
                service.revoke(session, grant.id, reason="operator pulled it mid-flight")

        workers = [threading.Thread(target=consume) for _ in range(8)]
        workers.append(threading.Thread(target=revoke))
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        events = [e["event"] for e in ledger.entries()]
        revoked_at = events.index("capability_revoked")
        consumed_after = [i for i, e in enumerate(events)
                          if e == "capability_consumed" and i > revoked_at]
        assert consumed_after == []
        assert grant.uses_consumed == events.count("capability_consumed")
    finally:
        reset_shared_instances()
