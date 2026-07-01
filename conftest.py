"""Pytest configuration providing basic asyncio support and offline stubs."""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import Any

# Fallback stubs for third-party packages (dotenv, numpy, openai, tenacity)
# live in tests/stubs. Appending the directory to the END of sys.path means a
# real installed package always takes precedence; the stubs only kick in when
# the dependency is missing, keeping the suite runnable offline.
_STUBS_DIR = str(Path(__file__).resolve().parent / "tests" / "stubs")
if _STUBS_DIR not in sys.path:
    sys.path.append(_STUBS_DIR)


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
