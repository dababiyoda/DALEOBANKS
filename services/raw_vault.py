"""Raw evidence vault: the untouched original of everything sensed.

The sanitizer must never destroy the source record. Raw external content
(mention text, DMs, articles, transcripts) is preserved here verbatim with
provenance for audit and replay — while only sanitized, delimited,
evidence-only context may ever enter a prompt. The vault is append-only
JSONL, separate from the tamper-evident ledger (which stores metadata, not
private text).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from services.logging_utils import get_logger

logger = get_logger(__name__)


def default_vault_path() -> str:
    return os.getenv("RAW_VAULT_PATH", os.path.join("data", "raw_vault.jsonl"))


class RawVault:
    """Append-only store of raw sensed content, keyed for replay."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_vault_path()
        self._lock = threading.Lock()

    def deposit(
        self,
        *,
        source: str,
        text: str,
        raw_ref: str = "",
        actor: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Store one raw record verbatim. Returns the vault id (None on failure)."""
        record = {
            "vault_id": str(uuid.uuid4()),
            "source": source,
            "raw_ref": str(raw_ref or ""),
            "actor": actor,
            "text": text,
            "received_at": datetime.now(UTC).isoformat(),
            "meta": meta or {},
        }
        try:
            with self._lock:
                directory = os.path.dirname(self.path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record["vault_id"]
        except Exception as exc:
            logger.error(f"Raw vault deposit failed: {exc}")
            return None

    def fetch(self, vault_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve one raw record for audit/replay."""
        try:
            with self._lock, open(self.path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("vault_id") == vault_id:
                        return record
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.error(f"Raw vault fetch failed: {exc}")
        return None

    def all_records(self) -> List[Dict[str, Any]]:
        try:
            with self._lock, open(self.path, "r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except FileNotFoundError:
            return []
        except Exception as exc:
            logger.error(f"Raw vault read failed: {exc}")
            return []

    def __len__(self) -> int:
        return len(self.all_records())


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
