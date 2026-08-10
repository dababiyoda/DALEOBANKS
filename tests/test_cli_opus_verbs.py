"""A gate whose only handle is a Python import is a wall.

These verbs are the handle. The asymmetry is the point: `advance` is
refused while construction is over the ceiling, and `prove` never is,
because proof is the only door out.
"""

import json

import pytest

from daleobanks.__main__ import main
from db.session import init_db


@pytest.fixture(autouse=True)
def _cold_store(tmp_path, monkeypatch):
    # conftest disables persistence for isolation; these verbs are about a
    # person running one command and then another, so the round trip through
    # the snapshot is the thing under test. Scoped to this file's tmp_path.
    monkeypatch.setenv("DB_SNAPSHOT_PATH", str(tmp_path / "store.jsonl"))
    monkeypatch.setenv("PERSIST_STORE", "true")
    init_db()


def _run(capsys, *argv):
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_unknown_component_names_where_to_look(capsys):
    code, out = _run(capsys, "prove", "--component", "nonexistent",
                     "--tier", "real_payment", "--ref", "invoice 4471")
    assert code == 2
    assert "opus" in out["hint"]


def test_advance_is_refused_while_construction_is_over_the_ceiling(capsys):
    code, out = _run(capsys, "advance", "--component", "one daily edition",
                     "--to", "SKETCHED")
    assert code == 2
    assert "blueprint stays open" in out["refused"]


def test_proof_is_never_gated_by_the_ceiling(capsys):
    """Negative control: the one door out is always open."""
    code, out = _run(capsys, "prove", "--component", "one daily edition",
                     "--tier", "real_user_behavior",
                     "--ref", "a reader in Lisbon opened three editions unprompted")
    assert code == 0
    assert out["maturity"] == "PROVEN"


def test_an_internal_reference_is_refused_at_the_command_line(capsys):
    code, out = _run(capsys, "prove", "--component", "one daily edition",
                     "--tier", "real_payment", "--ref", "services/canon.py")
    assert code == 2
    assert "its own evidence" in out["refused"]


def test_killing_without_harvesting_is_refused_at_the_command_line(capsys):
    code, out = _run(capsys, "kill", "--component", "one daily edition",
                     "--reason", "nobody read it")
    assert code == 2
    assert "tuition" in out["refused"]


def test_harvest_then_kill_works_at_the_command_line(capsys):
    code, _ = _run(capsys, "harvest", "--component", "one daily edition",
                   "--lesson", "daily outran the supply of things worth saying")
    assert code == 0
    code, out = _run(capsys, "kill", "--component", "one daily edition",
                     "--reason", "cadence was wrong, not the format")
    assert code == 0 and out["state"] == "KILLED"
