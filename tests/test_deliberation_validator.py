"""The validator must be able to fail, or it is a rubber stamp.

Each check gets a record that trips it. The corpus itself is the negative
control: five real records, written before the validator existed, all pass.
"""

import copy
import json
from pathlib import Path

import pytest

from governance.validate_deliberation import validate

CORPUS = Path("governance/deliberations")


def _valid():
    return json.loads((CORPUS / "DB-DEC-006.json").read_text())


def test_the_existing_corpus_passes():
    """Negative control: a checker that fails everything checks nothing."""
    records = sorted(CORPUS.glob("*.json"))
    assert len(records) >= 5
    for path in records:
        assert validate(json.loads(path.read_text())) == [], path.name


def test_four_roles_is_not_five():
    record = _valid()
    record["roles"] = record["roles"][:4]
    assert any("protocol requires 5" in p for p in validate(record))


def test_dissent_claimed_but_empty_is_caught():
    record = _valid()
    record["dissent"]["entries"] = []
    assert any("no entries recorded" in p for p in validate(record))


def test_a_forgotten_disadvantage_is_caught():
    """The common failure: a second pass that only adds."""
    record = _valid()
    record["pass_2"]["pass_1_disadvantage_dispositions"] = (
        record["pass_2"]["pass_1_disadvantage_dispositions"][:2]
    )
    assert any("never dispositioned" in p for p in validate(record))


def test_a_disposition_for_an_unraised_disadvantage_is_caught():
    record = _valid()
    record["pass_2"]["pass_1_disadvantage_dispositions"].append(
        {"disadvantage_id": "D99", "outcome": "resolved", "rationale": "x"}
    )
    assert any("which pass_1 never raised" in p for p in validate(record))


def test_a_second_pass_that_found_nothing_is_caught():
    record = _valid()
    record["pass_2"]["new_weaknesses"] = []
    assert any("did not happen" in p for p in validate(record))


def test_an_unweighed_alternative_is_caught():
    record = _valid()
    record["alternatives"].append({"name": "a thing", "description": "listed only"})
    assert any("never weighed" in p for p in validate(record))


def test_no_counterevidence_is_caught():
    record = _valid()
    record["counterevidence"] = []
    assert any("was not deliberated" in p for p in validate(record))


def test_changing_authority_without_an_approver_is_caught():
    record = _valid()
    record["authority_impact"]["changes_authority"] = True
    problems = validate(record)
    assert any("names no approver" in p for p in problems)
    assert any("without recorded approval" in p for p in problems)


def test_an_invented_evidence_tier_is_caught():
    record = _valid()
    record["evidence"][0]["tier"] = "it felt right"
    assert any("not on the hierarchy" in p for p in validate(record))


def test_a_missing_do_nothing_option_is_caught():
    record = _valid()
    record["do_nothing_option"]["expected_outcome"] = ""
    assert any("doing nothing is an option" in p for p in validate(record))
