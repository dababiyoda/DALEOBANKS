"""Pytest configuration providing basic asyncio support and offline stubs."""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Fallback stubs for third-party packages (dotenv, numpy, openai, tenacity)
# live in tests/stubs. Appending the directory to the END of sys.path means a
# real installed package always takes precedence; the stubs only kick in when
# the dependency is missing, keeping the suite runnable offline.
_STUBS_DIR = str(Path(__file__).resolve().parent / "tests" / "stubs")
if _STUBS_DIR not in sys.path:
    sys.path.append(_STUBS_DIR)

# Keep the decision ledger out of the working tree during test runs; tests
# that assert on ledger contents construct their own DecisionLedger(path=...).
if "LEDGER_PATH" not in os.environ:
    os.environ["LEDGER_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="daleobanks-ledger-"), "decision_ledger.jsonl"
    )

# Same for the semantic index (see services/semantic_index.py).
if "SEMANTIC_INDEX_PATH" not in os.environ:
    os.environ["SEMANTIC_INDEX_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="daleobanks-semindex-"), "semantic_index.jsonl"
    )


def pytest_pyfunc_call(pyfuncitem):  # pragma: no cover - pytest hook
    """Allow pytest to run ``async def`` tests without extra plugins."""
    test_func = pyfuncitem.obj

    if inspect.iscoroutinefunction(test_func):
        funcargs = pyfuncitem.funcargs
        sig = inspect.signature(test_func)
        call_args = {
            name: value
            for name, value in funcargs.items()
            if name in sig.parameters
        }
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(test_func(**call_args))
        finally:
            asyncio.set_event_loop(None)
            loop.close()
        return True
    return None
