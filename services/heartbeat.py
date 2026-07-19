"""Compatibility shim: supervised heartbeat loop.

The implementation now lives in the UNIIMENTE kernel SDK
(``uniimente_kernel.heartbeat``), extracted from this module in kernel
Phase 2 with identical behavior: per-stage isolation, consecutive-failure
breaker that fails toward silence, breaker reset that never re-arms,
ledgered errors and trips. Re-exported so existing imports keep working.
"""

from uniimente_kernel.heartbeat import Heartbeat

__all__ = ["Heartbeat"]
