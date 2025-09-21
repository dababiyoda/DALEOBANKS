"""Simple in-memory database session used for unit tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Generator, Iterable, List, Type, TypeVar, Callable

T = TypeVar("T")


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
    """A very small session that stores objects in process memory."""

    def __init__(self, store: Dict[Type[Any], List[Any]]):
        self._store = store
        self._new: List[Any] = []

    def add(self, obj: Any) -> None:
        self._store.setdefault(type(obj), []).append(obj)
        self._new.append(obj)

    def commit(self) -> None:  # pragma: no cover - behaviour is trivial
        self._new.clear()

    def rollback(self) -> None:  # pragma: no cover - nothing to roll back
        self._new.clear()

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        self._new.clear()

    def query(self, model: Type[T]) -> InMemoryQuery:
        return InMemoryQuery(self._store.get(model, []))


# Global in-memory backing store shared across sessions.
_STORE: Dict[Type[Any], List[Any]] = {}


def init_db() -> None:
    """Initialize the in-memory store. Present for API compatibility."""
    _STORE.clear()


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
