"""Compatibility shim: decision ledger, kill switch, and rate governor.

The implementations now live in the UNIIMENTE kernel SDK
(``uniimente_kernel.ledger``), extracted from this module in kernel Phase 2
with byte-compatible semantics: same canonical hashing, same chain
verification, same fail-safe direction. Existing ledger files on disk
verify unchanged under the kernel module.

What stays here (organ wiring, not logic):

- ``KillSwitch`` keeps the DALEOBANKS state model: ``config.LIVE`` is the
  source of truth and ``update_config`` propagates transitions to every
  config subscriber (multiplexer, adapters, X client). The kernel class
  supplies the ledgered transition machinery underneath.
- The shared-instance helpers stay so existing imports keep working.
- ``time`` is imported at module level because tests monkeypatch
  ``services.ledger.time.monotonic`` (same module object the kernel uses).
"""

from __future__ import annotations

import time  # noqa: F401 -- monkeypatch target, must exist in this namespace
from typing import Optional

from config import get_config, update_config
from services.logging_utils import get_logger

from uniimente_kernel.ledger import (
    DecisionLedger,
    RateGovernor,
    default_ledger_path,
)
from uniimente_kernel.ledger import KillSwitch as _KernelKillSwitch

logger = get_logger(__name__)


class KillSwitch(_KernelKillSwitch):
    """Config-derived kill switch on kernel transition machinery.

    The kernel switch holds internal state and delegates the organ-specific
    state change to an injected ``apply`` callable; here ``apply`` is the
    config update and ``armed`` reads live config, preserving the original
    semantics exactly (including transitions triggered elsewhere in config).
    """

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        super().__init__(
            ledger=ledger,
            apply=lambda armed: update_config(LIVE=bool(armed)),
            initially_armed=bool(get_config().LIVE),
        )

    @property
    def armed(self) -> bool:
        return bool(get_config().LIVE)

    def set_armed(self, armed: bool, reason: str = "") -> None:
        # Align kernel state with the organ source of truth, then let the
        # kernel machinery perform and ledger the transition (or no-op).
        self._armed = bool(get_config().LIVE)
        super().set_armed(armed, reason=reason)


# ---------------------------------------------------------------------- #
# Shared instances (unchanged from the original module)
# ---------------------------------------------------------------------- #
_SHARED_LEDGER: Optional[DecisionLedger] = None
_SHARED_KILL_SWITCH: Optional[KillSwitch] = None
_SHARED_GOVERNOR: Optional[RateGovernor] = None


def get_ledger() -> DecisionLedger:
    global _SHARED_LEDGER
    if _SHARED_LEDGER is None:
        _SHARED_LEDGER = DecisionLedger()
    return _SHARED_LEDGER


def get_kill_switch() -> KillSwitch:
    global _SHARED_KILL_SWITCH
    if _SHARED_KILL_SWITCH is None:
        _SHARED_KILL_SWITCH = KillSwitch(ledger=get_ledger())
    return _SHARED_KILL_SWITCH


def get_rate_governor() -> RateGovernor:
    global _SHARED_GOVERNOR
    if _SHARED_GOVERNOR is None:
        _SHARED_GOVERNOR = RateGovernor()
    return _SHARED_GOVERNOR


def set_shared_instances(
    *,
    ledger: Optional[DecisionLedger] = None,
    kill_switch: Optional[KillSwitch] = None,
    governor: Optional[RateGovernor] = None,
) -> None:
    """Swap the shared safety objects (used by tests)."""

    global _SHARED_LEDGER, _SHARED_KILL_SWITCH, _SHARED_GOVERNOR
    if ledger is not None:
        _SHARED_LEDGER = ledger
    if kill_switch is not None:
        _SHARED_KILL_SWITCH = kill_switch
    if governor is not None:
        _SHARED_GOVERNOR = governor


def reset_shared_instances() -> None:
    """Drop shared instances so they rebuild from current env/config."""

    global _SHARED_LEDGER, _SHARED_KILL_SWITCH, _SHARED_GOVERNOR
    _SHARED_LEDGER = None
    _SHARED_KILL_SWITCH = None
    _SHARED_GOVERNOR = None


__all__ = [
    "DecisionLedger",
    "KillSwitch",
    "RateGovernor",
    "default_ledger_path",
    "get_ledger",
    "get_kill_switch",
    "get_rate_governor",
    "set_shared_instances",
    "reset_shared_instances",
]
