"""Pytest configuration providing basic asyncio support and offline stubs."""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


class ExternalNetworkForbidden(BaseException):
    """A test attempted external I/O; do not let retry loops catch and retry it."""


def pytest_sessionstart(session):
    # Install before collection: optional real dependencies must never turn an
    # offline suite into outreach. This is test isolation, not a runtime policy.
    import socket
    original_lookup = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_sendto = socket.socket.sendto
    def local(host):
        return host in (None, 'localhost', '127.0.0.1', '::1', b'localhost', b'127.0.0.1', b'::1')
    def lookup(host, *args, **kwargs):
        if not local(host):
            raise ExternalNetworkForbidden('offline suite refused external DNS: ' + str(host))
        return original_lookup(host, *args, **kwargs)
    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            raise ExternalNetworkForbidden('offline suite refused external connection')
        return original_connect(sock, address)
    def sendto(sock, data, *args):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise ExternalNetworkForbidden('offline suite refused network datagram')
        return original_sendto(sock, data, *args)
    socket.getaddrinfo = lookup
    socket.socket.connect = connect
    socket.socket.sendto = sendto


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
