"""Durable object store exposing the in-memory query API used across services.

The store keeps the exact ``InMemoryQuery``/``InMemorySession`` semantics the
services and tests are written against (lambda predicates, ``order_by`` with a
key function), but persists every committed change to an atomic JSON-lines
snapshot so the agent's memory survives restarts and redeploys.

Persistence is controlled by two environment variables:

- ``PERSIST_STORE`` (default ``true``): set to ``false`` to run purely in
  memory (the test suite does this for isolation).
- ``DB_SNAPSHOT_PATH`` (default ``data/agent_store.jsonl``): snapshot file.

Swapping in a real database later only requires replacing this module — the
query API is the single seam.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Type, TypeVar

T = TypeVar("T")

_LOCK = threading.Lock()


def default_snapshot_path() -> str:
    return os.getenv("DB_SNAPSHOT_PATH", os.path.join("data", "agent_store.jsonl"))


def persistence_enabled() -> bool:
    return os.getenv("PERSIST_STORE", "true").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------- #
# Model registry and (de)serialization
# ---------------------------------------------------------------------- #
_MODEL_REGISTRY: Dict[str, Type[Any]] = {}
_DATETIME_FIELDS: Dict[str, List[str]] = {}


def _registry() -> Dict[str, Type[Any]]:
    if not _MODEL_REGISTRY:
        from db import models as models_module

        for name in dir(models_module):
            obj = getattr(models_module, name)
            if isinstance(obj, type) and is_dataclass(obj):
                _MODEL_REGISTRY[obj.__name__] = obj
                _DATETIME_FIELDS[obj.__name__] = [
                    f.name for f in fields(obj)
                    if "datetime" in str(f.type)
                ]
    return _MODEL_REGISTRY


def _serialize(obj: Any) -> Dict[str, Any]:
    data = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[f.name] = value
    return {"model": type(obj).__name__, "data": data}


def _deserialize(record: Dict[str, Any]) -> Optional[Any]:
    registry = _registry()
    cls = registry.get(record.get("model", ""))
    if cls is None:
        return None
    data = dict(record.get("data") or {})
    for name in _DATETIME_FIELDS.get(cls.__name__, []):
        value = data.get(name)
        if isinstance(value, str):
            try:
                data[name] = datetime.fromisoformat(value)
            except ValueError:
                pass
    known = {f.name for f in fields(cls)}
    data = {k: v for k, v in data.items() if k in known}
    try:
        return cls(**data)
    except TypeError:
        return None


def _persist() -> None:
    """Write the whole store to the snapshot file atomically."""
    if not persistence_enabled():
        return
    path = default_snapshot_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for objects in _STORE.values():
            for obj in objects:
                f.write(json.dumps(_serialize(obj), default=str) + "\n")
    os.replace(tmp_path, path)


def _load() -> None:
    """Populate the store from the snapshot file, if present."""
    if not persistence_enabled():
        return
    path = default_snapshot_path()
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            obj = _deserialize(record)
            if obj is not None:
                _STORE.setdefault(type(obj), []).append(obj)


class InMemoryQuery:
    """Minimal query helper supporting the operations used in tests."""

    def __init__(self, items: Iterable[Any]):
        self._items = list(items)

    def filter(self, *predicates: Callable[[Any], bool]) -> "InMemoryQuery":
        if not predicates:
            return InMemoryQuery(self._items)
        filtered = self._items
        for predicate in predicates:
            if predicate is None:
                continue
            if not callable(predicate):
                raise TypeError("filter predicates must be callables")
            filtered = [item for item in filtered if predicate(item)]
        return InMemoryQuery(filtered)

    def order_by(self, key: Callable[[Any], Any] | None = None, *, descending: bool = False) -> "InMemoryQuery":
        if key is None:
            return InMemoryQuery(self._items)
        return InMemoryQuery(sorted(self._items, key=key, reverse=descending))

    def limit(self, count: int) -> "InMemoryQuery":
        return InMemoryQuery(self._items[:count])

    def all(self) -> List[Any]:
        return list(self._items)

    def first(self) -> Any:
        return self._items[0] if self._items else None

    def count(self) -> int:
        return len(self._items)


class InMemorySession:
    """A small session over the durable process-wide store."""

    def __init__(self, store: Dict[Type[Any], List[Any]]):
        self._store = store
        self._new: List[Any] = []

    def add(self, obj: Any) -> None:
        self._store.setdefault(type(obj), []).append(obj)
        self._new.append(obj)

    def delete(self, obj: Any) -> None:
        objects = self._store.get(type(obj), [])
        try:
            objects.remove(obj)
        except ValueError:
            pass

    def commit(self) -> None:
        self._new.clear()
        with _LOCK:
            _persist()

    def rollback(self) -> None:  # pragma: no cover - behaviour is trivial
        self._new.clear()

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        self._new.clear()

    def query(self, model: Type[T]) -> InMemoryQuery:
        return InMemoryQuery(self._store.get(model, []))


# Global backing store shared across sessions.
_STORE: Dict[Type[Any], List[Any]] = {}


def init_db() -> None:
    """Initialize the store, restoring the snapshot when persistence is on."""
    with _LOCK:
        _STORE.clear()
        _load()


@contextmanager
def get_db_session() -> Generator[InMemorySession, None, None]:
    """Yield an :class:`InMemorySession` for use in `with` statements."""
    session = InMemorySession(_STORE)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[InMemorySession, None, None]:
    """Compatibility helper mirroring FastAPI dependency signature."""
    with get_db_session() as session:
        yield session
