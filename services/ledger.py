"""Tamper-evident decision ledger, kill switch, and rate governor.

The safety spine of the agent:

- ``DecisionLedger`` is an append-only, hash-chained JSONL log. Every entry
  carries the hash of its predecessor, so the agent's history (decisions,
  publishes, identity changes, lessons) can be verified months later with
  ``verify_chain()`` and read back in order with ``replay()``. The mind can
  add to its autobiography but cannot silently rewrite it.
- ``KillSwitch`` is the single authority over live posting. It is a thin,
  ledgered wrapper around the existing ``config.LIVE`` toggle, so the whole
  stack (multiplexer, adapters, X client) observes it through the config
  update mechanism that is already in place. Fail-safe direction is always
  toward silence: ``LIVE`` defaults to false.
- ``RateGovernor`` caps live actions per platform in a sliding window so a
  runaway loop cannot outpace human oversight.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, UTC
from typing import Any, Deque, Dict, List, Optional, Tuple

from config import get_config, update_config
from services.logging_utils import get_logger

logger = get_logger(__name__)

_GENESIS_HASH = "0" * 64

# One lock per ledger file so multiple DecisionLedger instances in the same
# process (each service constructs its own) serialize their appends.
_PATH_LOCKS: Dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _PATH_LOCKS_GUARD:
        if path not in _PATH_LOCKS:
            _PATH_LOCKS[path] = threading.Lock()
        return _PATH_LOCKS[path]


def default_ledger_path() -> str:
    """Resolve the ledger location (env override for tests/deployments)."""

    return os.getenv("LEDGER_PATH", os.path.join("data", "decision_ledger.jsonl"))


def _entry_hash(entry: Dict[str, Any]) -> str:
    """Hash the canonical form of an entry (everything except its own hash)."""

    material = {k: v for k, v in entry.items() if k != "hash"}
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DecisionLedger:
    """Append-only hash-chained event log (JSONL, one entry per line)."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_ledger_path()

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #
    def record(self, event: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Append an event to the chain and return the stored entry."""

        with _lock_for(self.path):
            prev_seq, prev_hash = self._tail()
            entry: Dict[str, Any] = {
                "seq": prev_seq + 1,
                "ts": datetime.now(UTC).isoformat(),
                "event": event,
                "payload": payload or {},
                "prev_hash": prev_hash,
            }
            entry["hash"] = _entry_hash(entry)

            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")
        return entry

    # ------------------------------------------------------------------ #
    # Reading & verification
    # ------------------------------------------------------------------ #
    def entries(self) -> List[Dict[str, Any]]:
        """All entries in order. Malformed lines are surfaced as corrupt."""

        if not os.path.exists(self.path):
            return []
        out: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"seq": None, "event": "__corrupt__", "raw": line})
        return out

    def replay(self, event: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return entries in order, optionally filtered by event type."""

        entries = self.entries()
        if event is not None:
            entries = [e for e in entries if e.get("event") == event]
        if limit is not None:
            entries = entries[-limit:]
        return entries

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Verify the hash chain. Returns (ok, first_bad_seq)."""

        prev_hash = _GENESIS_HASH
        expected_seq = 1
        for entry in self.entries():
            seq = entry.get("seq")
            if entry.get("event") == "__corrupt__" or seq != expected_seq:
                return False, seq if isinstance(seq, int) else expected_seq
            if entry.get("prev_hash") != prev_hash or _entry_hash(entry) != entry.get("hash"):
                return False, seq
            prev_hash = entry["hash"]
            expected_seq += 1
        return True, None

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _tail(self) -> Tuple[int, str]:
        """Sequence number and hash of the last entry on disk."""

        if not os.path.exists(self.path):
            return 0, _GENESIS_HASH
        last_line = ""
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return 0, _GENESIS_HASH
        try:
            last = json.loads(last_line)
            return int(last["seq"]), str(last["hash"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.error("Ledger tail unreadable; continuing chain from genesis marker")
            return 0, _GENESIS_HASH


class KillSwitch:
    """Ledgered authority over live posting; wraps ``config.LIVE``.

    Disarming propagates through ``update_config`` so every component that
    subscribes to config updates (multiplexer, adapters) goes quiet together.
    """

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self.ledger = ledger or DecisionLedger()

    @property
    def armed(self) -> bool:
        return bool(get_config().LIVE)

    def set_armed(self, armed: bool, reason: str = "") -> None:
        if bool(get_config().LIVE) == bool(armed):
            return
        update_config(LIVE=bool(armed))
        self.ledger.record(
            "kill_switch",
            {"armed": bool(armed), "reason": reason or "unspecified"},
        )
        logger.warning("Kill switch %s (%s)", "ARMED" if armed else "DISARMED", reason or "unspecified")


class RateGovernor:
    """Sliding-window cap on live actions per key (typically per platform)."""

    def __init__(self, max_actions: Optional[int] = None, window_seconds: int = 3600) -> None:
        if max_actions is None:
            max_actions = int(os.getenv("RATE_GOVERNOR_MAX_PER_HOUR", "30"))
        self.max_actions = max_actions
        self.window_seconds = window_seconds
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record an action attempt for ``key``; False when over the cap."""

        now = time.monotonic()
        with self._lock:
            window = self._events[key]
            while window and now - window[0] > self.window_seconds:
                window.popleft()
            if len(window) >= self.max_actions:
                return False
            window.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            window = self._events[key]
            while window and now - window[0] > self.window_seconds:
                window.popleft()
            return max(self.max_actions - len(window), 0)


# ---------------------------------------------------------------------- #
# Shared instances
#
# The publish gate in BaseSocialClient and the app startup check need one
# process-wide chain and governor. Services that want isolation (tests) can
# construct their own instances or swap these via set_shared_instances().
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
