"""Tests for the decision ledger, kill switch, and rate governor."""

import json
import os

from config import get_config, update_config
from services.ledger import DecisionLedger, KillSwitch, RateGovernor


def _make_ledger(tmp_path):
    return DecisionLedger(path=str(tmp_path / "ledger.jsonl"))


def test_ledger_records_and_verifies_chain(tmp_path):
    ledger = _make_ledger(tmp_path)

    first = ledger.record("test_event", {"n": 1})
    second = ledger.record("test_event", {"n": 2})

    assert first["seq"] == 1
    assert second["seq"] == 2
    assert second["prev_hash"] == first["hash"]

    ok, bad_seq = ledger.verify_chain()
    assert ok is True
    assert bad_seq is None


def test_ledger_detects_tampering(tmp_path):
    ledger = _make_ledger(tmp_path)
    ledger.record("test_event", {"n": 1})
    ledger.record("test_event", {"n": 2})
    ledger.record("test_event", {"n": 3})

    # Rewrite the payload of the middle entry without recomputing hashes.
    with open(ledger.path) as f:
        lines = f.readlines()
    entry = json.loads(lines[1])
    entry["payload"]["n"] = 999
    lines[1] = json.dumps(entry, separators=(",", ":")) + "\n"
    with open(ledger.path, "w") as f:
        f.writelines(lines)

    ok, bad_seq = ledger.verify_chain()
    assert ok is False
    assert bad_seq == 2


def test_ledger_replay_filters_by_event(tmp_path):
    ledger = _make_ledger(tmp_path)
    ledger.record("alpha", {"i": 1})
    ledger.record("beta", {"i": 2})
    ledger.record("alpha", {"i": 3})

    alphas = ledger.replay("alpha")
    assert [e["payload"]["i"] for e in alphas] == [1, 3]

    limited = ledger.replay("alpha", limit=1)
    assert [e["payload"]["i"] for e in limited] == [3]

    everything = ledger.replay()
    assert len(everything) == 3


def test_ledger_survives_multiple_instances_on_same_file(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    a = DecisionLedger(path=path)
    b = DecisionLedger(path=path)

    a.record("event", {"src": "a"})
    b.record("event", {"src": "b"})
    a.record("event", {"src": "a2"})

    ok, _ = a.verify_chain()
    assert ok is True
    assert len(a.replay()) == 3


def test_kill_switch_disarm_propagates_to_config_and_ledger(tmp_path):
    ledger = _make_ledger(tmp_path)
    switch = KillSwitch(ledger=ledger)

    previous = get_config().LIVE
    try:
        update_config(LIVE=True)
        assert switch.armed is True

        switch.set_armed(False, reason="test_breaker")
        assert get_config().LIVE is False
        assert switch.armed is False

        events = ledger.replay("kill_switch")
        assert len(events) == 1
        assert events[0]["payload"] == {"armed": False, "reason": "test_breaker"}

        # No-op when already in the requested state: nothing new recorded.
        switch.set_armed(False, reason="again")
        assert len(ledger.replay("kill_switch")) == 1
    finally:
        update_config(LIVE=previous)


def test_rate_governor_caps_actions_within_window():
    governor = RateGovernor(max_actions=3, window_seconds=3600)

    assert governor.allow("x") is True
    assert governor.allow("x") is True
    assert governor.allow("x") is True
    assert governor.allow("x") is False
    assert governor.remaining("x") == 0

    # Other keys have independent budgets.
    assert governor.allow("mastodon") is True


def test_rate_governor_window_expiry(monkeypatch):
    governor = RateGovernor(max_actions=1, window_seconds=10)

    now = [1000.0]
    monkeypatch.setattr("services.ledger.time.monotonic", lambda: now[0])

    assert governor.allow("x") is True
    assert governor.allow("x") is False

    now[0] += 11
    assert governor.allow("x") is True
