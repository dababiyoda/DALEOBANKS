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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="daleobanks",
        description="Run the DALEOBANKS institution from a founder declaration.",
    )
    parser.add_argument(
        "command", choices=["validate", "preflight", "run", "report"],
        help="validate the declaration, show what is authorized, run one "
             "shadow cycle, or print the report",
    )
    parser.add_argument("--declaration", default=DEFAULT_DECLARATION_PATH)
    args = parser.parse_args(argv)

    try:
        declaration = Declaration.load(args.declaration)
    except DeclarationError as exc:
        # The useful output is which decision has not been made.
        _emit({"ok": False, "error": str(exc)})
        return 2

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
        if args.command == "run":
            _emit(institution.run_cycle(session))
        else:
            _emit(institution.report(session))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
