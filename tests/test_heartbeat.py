"""Tests for the supervised heartbeat loop and its fail-safe breaker."""

from config import get_config, update_config
from services.heartbeat import Heartbeat
from services.ledger import DecisionLedger, KillSwitch


def _heartbeat(tmp_path, max_failures=3):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    return Heartbeat(KillSwitch(ledger=ledger), ledger,
                     max_consecutive_failures=max_failures), ledger


async def test_stage_failure_is_isolated_and_ledgered(tmp_path):
    heartbeat, ledger = _heartbeat(tmp_path)
    ran = []

    async def good():
        ran.append("good")

    async def bad():
        raise RuntimeError("perception exploded")

    await heartbeat.run_cycle({"perceive": bad, "plan": good})

    # The failing stage did not kill the cycle; the next stage still ran.
    assert ran == ["good"]
    errors = ledger.replay("cycle_error")
    assert len(errors) == 1
    assert errors[0]["payload"]["stage"] == "perceive"
    assert "perception exploded" in errors[0]["payload"]["error"]
    # One success later, the streak is reset.
    assert heartbeat.consecutive_failures == 0


async def test_breaker_trips_after_consecutive_failures_and_disarms(tmp_path):
    heartbeat, ledger = _heartbeat(tmp_path, max_failures=3)

    async def bad():
        raise RuntimeError("boom")

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)

        await heartbeat.run_cycle({"a": bad, "b": bad, "c": bad, "d": bad})

        # Breaker tripped at the third consecutive failure; live disarmed;
        # remaining stages skipped.
        assert heartbeat.breaker_tripped is True
        assert get_config().LIVE is False
        assert len(ledger.replay("cycle_error")) == 3
        assert len(ledger.replay("breaker_tripped")) == 1
        assert ledger.replay("kill_switch")[-1]["payload"]["armed"] is False
    finally:
        update_config(LIVE=previous)


async def test_success_resets_failure_streak(tmp_path):
    heartbeat, ledger = _heartbeat(tmp_path, max_failures=3)

    async def bad():
        raise RuntimeError("boom")

    async def good():
        return None

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)
        await heartbeat.run_cycle({"a": bad, "b": bad, "c": good, "d": bad})

        # Two failures, reset by a success, then one more: breaker holds.
        assert heartbeat.breaker_tripped is False
        assert get_config().LIVE is True
        assert heartbeat.consecutive_failures == 1
    finally:
        update_config(LIVE=previous)


async def test_supervise_wraps_jobs_for_the_scheduler(tmp_path):
    heartbeat, ledger = _heartbeat(tmp_path, max_failures=2)

    async def failing_job():
        raise ValueError("job bug")

    wrapped = heartbeat.supervise("post_proposal", failing_job)

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)
        await wrapped()  # exception must not propagate into the scheduler
        assert heartbeat.consecutive_failures == 1
        await wrapped()
        assert heartbeat.breaker_tripped is True
        assert get_config().LIVE is False
    finally:
        update_config(LIVE=previous)


async def test_reset_breaker_does_not_rearm_live(tmp_path):
    heartbeat, ledger = _heartbeat(tmp_path, max_failures=1)

    async def bad():
        raise RuntimeError("boom")

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)
        await heartbeat.run_cycle({"a": bad})
        assert heartbeat.breaker_tripped is True
        assert get_config().LIVE is False

        heartbeat.reset_breaker()
        assert heartbeat.breaker_tripped is False
        # Going live again is a human decision, not an automatic one.
        assert get_config().LIVE is False
        assert ledger.replay("breaker_reset")
    finally:
        update_config(LIVE=previous)
