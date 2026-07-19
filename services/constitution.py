"""Compatibility shim: constitution guard.

The implementation now lives in the UNIIMENTE kernel SDK
(``uniimente_kernel.constitution_check``), extracted from this module in
kernel Phase 2. The kernel guard watches several files and hashes them
together; for a single watched file it records the file's plain sha256 —
exactly what this organ's guard has always recorded for its one
``constitution.md``. Load, verify, tamper-disarm, and ledger event shapes
are unchanged. This class keeps the organ's single-file API
(``path``, ``current_hash()``, ``text()``, ``startup_hash``) over the
kernel machinery; when DALEOBANKS migrates to the kernel's UCL
constitution directory, the overrides disappear.
"""

from __future__ import annotations

from typing import Optional

from services.ledger import DecisionLedger, KillSwitch
from services.logging_utils import get_logger
from uniimente_kernel.constitution_check import (
    ConstitutionGuard as _KernelGuard,
    _hash_file,
)

logger = get_logger(__name__)

DEFAULT_CONSTITUTION_PATH = "constitution.md"


class ConstitutionGuard(_KernelGuard):
    """Single-file constitution guard on kernel multi-file machinery."""

    def __init__(
        self,
        path: str = DEFAULT_CONSTITUTION_PATH,
        *,
        ledger: Optional[DecisionLedger] = None,
        kill_switch: Optional[KillSwitch] = None,
    ) -> None:
        super().__init__([path], ledger=ledger, kill_switch=kill_switch)
        self.path = path

    @property
    def startup_hash(self) -> Optional[str]:
        return self.startup_hashes.get(self.path)

    @startup_hash.setter
    def startup_hash(self, value: Optional[str]) -> None:
        self.startup_hashes = {} if value is None else {self.path: value}

    def current_hash(self) -> Optional[str]:
        return _hash_file(self.path)

    def text(self) -> str:
        return super().text(self.path)


__all__ = ["ConstitutionGuard", "DEFAULT_CONSTITUTION_PATH"]
