"""python -m daleobanks — validate, preflight, run, report.

Four verbs, in the order you would actually use them. Every one is read-only
with respect to the outside world: the strongest thing this can do is write a
shadow receipt to a local store.
"""

from __future__ import annotations

import argparse
import json
import sys

from services.institution import (
    DEFAULT_DECLARATION_PATH,
    DaleoBanks,
    Declaration,
    DeclarationError,
)


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _move_component(institution, session, args) -> int:
    """Operate the ledger from outside it.

    A gate whose only handle is a Python import is a wall. These four verbs
    are the handle: everything this branch built is now gated on recording a
    consequence, so recording one has to be something a person can do.
    """
    from services.compounding_ledger import CompoundingError

    ledger = institution.opus
    component = ledger.by_name(session, args.component or "")
    if component is None:
        _emit({
            "ok": False,
            "error": f"no component named {args.component!r}",
            "hint": "run `python -m daleobanks opus` for the names",
        })
        return 2

    try:
        if args.command == "advance":
            record = ledger.advance(
                session, component.id, to=args.to_level or "", note=args.note
            )
            result = {"component": record.name, "maturity": record.maturity}
        elif args.command == "prove":
            ledger.record_proof(
                session,
                component.id,
                evidence_tier=args.tier or "",
                external_reference=args.ref or "",
                description=args.note,
            )
            result = {
                "component": component.name,
                "maturity": component.maturity,
                "state": component.state,
                "admitted_proofs": component.admitted_proof_count,
                "next": ledger.next_step(session, component),
            }
        elif args.command == "harvest":
            record = ledger.harvest(
                session, component.id, lesson=args.lesson or ""
            )
            result = {"component": component.name, "lesson": record.lesson}
        else:
            record = ledger.kill(session, component.id, reason=args.reason or "")
            result = {"component": record.name, "state": record.state}
    except CompoundingError as exc:
        # The refusal is the useful output. It says what was not paid for.
        _emit({"ok": False, "refused": str(exc)})
        return 2

    session.commit()
    _emit({"ok": True, **result})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="daleobanks",
        description="Run the DALEOBANKS institution from a founder declaration.",
    )
    parser.add_argument(
        "command",
        choices=["validate", "preflight", "seed", "run", "report", "canon",
                 "opus", "advance", "prove", "harvest", "kill"],
        help="validate the declaration, show what is authorized, seed the "
             "canonical structure and blueprint, run one shadow cycle, print "
             "the report, dump the canon, ask what the work has done outside "
             "itself, or move one component along: advance it a level, prove "
             "it with outside evidence, harvest its lesson, kill it",
    )
    parser.add_argument("--declaration", default=DEFAULT_DECLARATION_PATH)
    parser.add_argument("--component", help="component name, as `opus` prints it")
    parser.add_argument("--to", dest="to_level", help="target maturity level")
    parser.add_argument("--tier", help="evidence tier for `prove`")
    parser.add_argument(
        "--ref",
        help="what happened outside this system: an invoice, a person, a "
             "settlement. Repository paths and simulations are refused.",
    )
    parser.add_argument("--note", default="", help="what was done")
    parser.add_argument("--lesson", help="what this taught, required to harvest")
    parser.add_argument("--reason", help="why, required to kill")
    args = parser.parse_args(argv)

    try:
        declaration = Declaration.load(args.declaration)
    except DeclarationError as exc:
        # The useful output is which decision has not been made.
        _emit({"ok": False, "error": str(exc)})
        return 2

    if args.command == "canon":
        from services.canon import (
            COMMUNITY, DAILY_NEWS, FLAGSHIP_CHANNEL, LANGUAGE_LANES,
            PILLARS, PORTFOLIO_MIX, RABBIT_HOLE,
        )

        _emit({
            "flagship_channel": FLAGSHIP_CHANNEL,
            "community": COMMUNITY,
            "pillars": [{"id": p["id"], "name": p["name"]} for p in PILLARS],
            "rabbit_hole": [{"depth": n["depth"], "surface": n["surface"],
                             "title": n["title"]} for n in RABBIT_HOLE],
            "daily_news": DAILY_NEWS,
            "language_lanes": LANGUAGE_LANES,
            "portfolio_mix": PORTFOLIO_MIX,
        })
        return 0

    if args.command == "validate":
        _emit({
            "ok": True,
            "founder": declaration.founder,
            "timezone": declaration.timezone,
            "accounts": len(declaration.accounts),
            "languages": declaration.languages,
            "gaps": declaration.gaps(),
        })
        return 0

    institution = DaleoBanks(declaration)

    if args.command == "preflight":
        _emit(institution.preflight())
        return 0

    from db.session import get_db_session, init_db

    init_db()
    with get_db_session() as session:
        if args.command == "seed":
            _emit({
                "canon": institution.seed_canon(session),
                "opus": institution.seed_opus(session),
            })
        elif args.command == "opus":
            # Seeding is idempotent, so this verb works on a cold store.
            institution.seed_opus(session)
            _emit(institution.opus_report(session))
        elif args.command in ("advance", "prove", "harvest", "kill"):
            institution.seed_opus(session)
            return _move_component(institution, session, args)
        elif args.command == "run":
            _emit(institution.run_cycle(session))
        else:
            _emit(institution.report(session))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
