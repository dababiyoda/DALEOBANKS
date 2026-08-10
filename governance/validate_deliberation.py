"""Check that a deliberation record is a deliberation and not a summary.

The Recursive Founder-Intent Collaboration Protocol asks for five roles, two
passes, a do-nothing alternative, and dissent that survives into the record.
Without a check, those are a convention, and a convention is what a hurried
author drops first.

This validates shape, not wisdom. It cannot tell whether the dissent was
real. It can tell whether someone wrote `"present": true` and then left the
entries empty, whether every pass 1 disadvantage was actually dispositioned
in pass 2 rather than quietly forgotten, and whether a record that claims to
change authority also names who approved it.

Run it on one file or on the directory:

    python governance/validate_deliberation.py governance/deliberations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REQUIRED_TOP = (
    "decision_id", "title", "problem", "founder_intent_refs", "baseline",
    "alternatives", "do_nothing_option", "roles", "evidence", "counterevidence",
    "pass_1", "pass_2", "dissent", "authority_impact", "migration_plan",
    "rollback_plan",
)
REQUIRED_ROLES = 5
REQUIRED_PASS_1 = ("intended_outcome", "advantages", "disadvantages",
                   "comparisons", "rejected_alternatives")
REQUIRED_PASS_2 = ("attack_summary", "new_weaknesses",
                   "pass_1_disadvantage_dispositions", "final_design",
                   "residual_risks", "recommendation")
REQUIRED_COMPARISONS = ("baseline", "do_nothing", "simplest_viable_alternative",
                        "strongest_competing_architecture",
                        "reversible_experiment")
# These vocabularies are read off the existing corpus rather than invented.
# A validator calibrated to its author's newest record will pass that record
# and fail every earlier one, which is a check on nothing.
VALID_RECOMMENDATIONS = ("RETAIN", "EXPERIMENT", "REVISE", "REJECT", "DEFER")
VALID_DISPOSITIONS = ("accepted", "mitigated", "resolved", "rejected",
                      "deferred", "experiment")
EVIDENCE_TIERS = ("primary_source", "historical_artifact", "reproduced_test",
                  "unit_test", "sandbox_execution", "deterministic_fixture",
                  "working_prototype", "authorized_pilot", "real_payment",
                  "real_user_behavior", "external_acceptance",
                  "reconciled_real_outcome", "simulation", "model_reasoning",
                  "document", "other")


def _fail(problems: List[str], condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def validate(record: Dict[str, Any]) -> List[str]:
    """Return every structural problem found. An empty list means it passes."""
    problems: List[str] = []

    for key in REQUIRED_TOP:
        _fail(problems, key in record, f"missing top-level field {key!r}")
    if problems:
        return problems

    _fail(problems, len(record["roles"]) >= REQUIRED_ROLES,
          f"{len(record['roles'])} roles, protocol requires {REQUIRED_ROLES}")
    for role in record["roles"]:
        _fail(problems, bool(role.get("role")) and bool(role.get("position")),
              "a role has no name or no position")

    _fail(problems, len(record["alternatives"]) >= 2,
          "fewer than two alternatives considered")
    for alt in record["alternatives"]:
        name = alt.get("name")
        _fail(problems, bool(name) and bool(alt.get("description")),
              "an alternative has no name or no description")
        # An alternative counts as considered when it was weighed on both
        # sides or explicitly rejected. Listing it is not considering it.
        weighed = bool(alt.get("advantages")) and bool(alt.get("disadvantages"))
        rejected = bool(alt.get("rejection_reason"))
        _fail(problems, weighed or rejected,
              f"alternative {name!r} was listed but never weighed: it needs "
              "advantages and disadvantages, or a rejection reason")

    dn = record["do_nothing_option"]
    for key in ("expected_outcome", "advantages", "disadvantages"):
        _fail(problems, bool(dn.get(key)),
              f"do_nothing_option is missing {key}: doing nothing is an option "
              "and has to be argued for")

    for key in REQUIRED_PASS_1:
        _fail(problems, key in record["pass_1"], f"pass_1 missing {key!r}")
    for key in REQUIRED_PASS_2:
        _fail(problems, key in record["pass_2"], f"pass_2 missing {key!r}")
    if any(p.startswith("pass_") for p in problems):
        return problems

    for key in REQUIRED_COMPARISONS:
        _fail(problems, bool(record["pass_1"]["comparisons"].get(key)),
              f"pass_1.comparisons missing {key!r}")

    # Every pass 1 disadvantage must be answered in pass 2. This is the check
    # that catches the common failure: a strengthening pass that only adds.
    declared = {d["id"] for d in record["pass_1"]["disadvantages"]}
    handled = {
        d["disadvantage_id"]
        for d in record["pass_2"]["pass_1_disadvantage_dispositions"]
    }
    for missing in sorted(declared - handled):
        problems.append(f"pass_1 disadvantage {missing} was never dispositioned")
    for unknown in sorted(handled - declared):
        problems.append(f"pass_2 dispositions {unknown}, which pass_1 never raised")
    for disp in record["pass_2"]["pass_1_disadvantage_dispositions"]:
        _fail(problems, disp.get("outcome") in VALID_DISPOSITIONS,
              f"disposition {disp.get('disadvantage_id')} has outcome "
              f"{disp.get('outcome')!r}, expected one of "
              f"{', '.join(VALID_DISPOSITIONS)}")
        _fail(problems, bool(disp.get("rationale")),
              f"disposition {disp.get('disadvantage_id')} has no rationale")

    _fail(problems, len(record["pass_2"]["new_weaknesses"]) >= 1,
          "pass 2 found no new weakness: a strengthening pass that finds "
          "nothing did not happen")
    for weakness in record["pass_2"]["new_weaknesses"]:
        _fail(problems, bool(weakness.get("strengthening_response")),
              f"weakness {weakness.get('id')} was named but not answered")

    _fail(problems,
          record["pass_2"]["recommendation"] in VALID_RECOMMENDATIONS,
          f"recommendation {record['pass_2']['recommendation']!r} is not one of "
          f"{', '.join(VALID_RECOMMENDATIONS)}")

    _fail(problems, len(record["counterevidence"]) >= 1,
          "no counterevidence: a decision with nothing against it was not "
          "deliberated")
    for item in record["evidence"] + record["counterevidence"]:
        _fail(problems, item.get("tier") in EVIDENCE_TIERS,
              f"evidence tier {item.get('tier')!r} is not on the hierarchy")
        _fail(problems, bool(item.get("reference")),
              "an evidence item has no reference")

    dissent = record["dissent"]
    if dissent.get("present"):
        _fail(problems, bool(dissent.get("entries")),
              "dissent claims to be present with no entries recorded")
        _fail(problems, bool(dissent.get("handling")),
              "dissent is present but nothing says how it binds")
        for entry in dissent.get("entries", []):
            _fail(problems, bool(entry.get("position")),
                  "a dissent entry has no position")

    authority = record["authority_impact"]
    if authority.get("changes_authority"):
        _fail(problems, bool(authority.get("approver")),
              "the record changes authority and names no approver")
        _fail(problems, authority.get("approval_status") == "approved",
              "the record changes authority without recorded approval")

    rollback = record["rollback_plan"]
    _fail(problems,
          bool(rollback.get("steps")) or bool(rollback.get("reason_impossible")),
          "rollback is neither planned nor explained as impossible")

    _fail(problems, len(record["founder_intent_refs"]) >= 1,
          "no founder intent referenced: this is a preference, not a decision")

    return problems


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    paths = sorted(target.glob("*.json")) if target.is_dir() else [target]
    if not paths:
        print(f"no records found at {target}")
        return 2

    failed = 0
    for path in paths:
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            print(f"FAIL {path.name}: not valid JSON: {exc}")
            failed += 1
            continue
        problems = validate(record)
        if problems:
            failed += 1
            print(f"FAIL {path.name}")
            for problem in problems:
                print(f"     {problem}")
        else:
            print(f"ok   {path.name}")

    print(f"\n{len(paths) - failed}/{len(paths)} records valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
