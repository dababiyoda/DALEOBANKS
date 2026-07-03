"""Constitution guard: fixed values the agent cannot rewrite.

The constitution file is loaded read-only. Its hash is recorded in the
decision ledger at startup and re-verified while the agent runs; a runtime
mismatch means the file changed underneath a live process (tampering or an
unreviewed edit), and the guard fails toward silence by disarming live
posting. Legitimate amendments arrive as human commits followed by a
restart, which records the new hash as a ledgered constitution event.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from services.ledger import DecisionLedger, KillSwitch
from services.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_CONSTITUTION_PATH = "constitution.md"


class ConstitutionGuard:
    """Hashes the constitution at startup and detects runtime drift."""

    def __init__(
        self,
        path: str = DEFAULT_CONSTITUTION_PATH,
        *,
        ledger: Optional[DecisionLedger] = None,
        kill_switch: Optional[KillSwitch] = None,
    ) -> None:
        self.path = path
        self.ledger = ledger or DecisionLedger()
        self.kill_switch = kill_switch or KillSwitch(ledger=self.ledger)
        self.startup_hash: Optional[str] = None

    def current_hash(self) -> Optional[str]:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def text(self) -> str:
        if not os.path.exists(self.path):
            return ""
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()

    def load_and_record(self) -> Optional[str]:
        """Record the constitution hash at startup (the reference point)."""
        self.startup_hash = self.current_hash()
        if self.startup_hash is None:
            logger.warning("Constitution file missing at %s", self.path)
            self.ledger.record("constitution_missing", {"path": self.path})
            return None
        self.ledger.record("constitution_hash", {
            "path": self.path,
            "hash": self.startup_hash,
        })
        return self.startup_hash

    def verify(self) -> bool:
        """Re-verify at runtime; on drift, disarm and ledger the event."""
        if self.startup_hash is None:
            # Never recorded (missing file at startup): nothing to verify.
            return True
        current = self.current_hash()
        if current == self.startup_hash:
            return True
        self.ledger.record("constitution_tampered", {
            "path": self.path,
            "expected": self.startup_hash,
            "found": current,
        })
        self.kill_switch.set_armed(False, reason="constitution_tampered")
        logger.critical("Constitution changed at runtime -> live posting disarmed")
        return False


__all__ = ["ConstitutionGuard", "DEFAULT_CONSTITUTION_PATH"]
