"""Pytest configuration providing basic asyncio support."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


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
