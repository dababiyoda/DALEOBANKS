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

# Same for the world model (see services/world_model.py).
if "WORLD_MODEL_PATH" not in os.environ:
    os.environ["WORLD_MODEL_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="daleobanks-worldmodel-"), "world_model.jsonl"
    )

# Same for the evidence library (see services/evidence_library.py).
if "EVIDENCE_LIBRARY_PATH" not in os.environ:
    os.environ["EVIDENCE_LIBRARY_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="daleobanks-evidence-"), "evidence_library.jsonl"
    )

# Same for the raw evidence vault (see services/raw_vault.py).
if "RAW_VAULT_PATH" not in os.environ:
    os.environ["RAW_VAULT_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="daleobanks-rawvault-"), "raw_vault.jsonl"
    )

# Run the object store purely in memory so tests stay isolated (init_db()
# gives every test a clean slate). Persistence has dedicated tests that
# opt back in with a temp snapshot path.
os.environ.setdefault("PERSIST_STORE", "false")


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
