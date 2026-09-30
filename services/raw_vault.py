"""Compatibility shim: raw evidence vault.

The implementation now lives in the UNIIMENTE kernel SDK
(``uniimente_kernel.raw_vault``), extracted from this module in kernel
Phase 2. Semantics are preserved: verbatim append-only JSONL storage,
keyed fetch, fail-soft logging. One additive change from the kernel:
every newly deposited record also carries ``content_hash`` (sha256 of the
verbatim text, aligning with the kernel evidence contract) and an
``instruction_shaped`` quarantine flag. Records written before this swap
remain readable; they simply predate those fields.

The shared-vault helpers stay here so existing imports keep working.
"""

from __future__ import annotations

from typing import Optional

from uniimente_kernel.raw_vault import RawVault, default_vault_path

_SHARED_VAULT: Optional[RawVault] = None


def get_raw_vault() -> RawVault:
    global _SHARED_VAULT
    if _SHARED_VAULT is None:
        _SHARED_VAULT = RawVault()
    return _SHARED_VAULT


def set_raw_vault(vault: Optional[RawVault]) -> None:
    global _SHARED_VAULT
    _SHARED_VAULT = vault


__all__ = ["RawVault", "get_raw_vault", "set_raw_vault", "default_vault_path"]
