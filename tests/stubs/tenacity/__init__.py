"""Minimal subset of Tenacity's public API for testing."""

from __future__ import annotations

from typing import Any, Callable, Tuple, Type


def retry(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def async_wrapper(*func_args: Any, **func_kwargs: Any) -> Any:
            return await func(*func_args, **func_kwargs)

        def sync_wrapper(*func_args: Any, **func_kwargs: Any) -> Any:
            return func(*func_args, **func_kwargs)

        return async_wrapper if _is_coroutine_function(func) else sync_wrapper

    return decorator


def stop_after_attempt(attempts: int) -> int:
    return attempts


def wait_exponential(**kwargs: Any) -> dict[str, Any]:
    return kwargs


def retry_if_exception_type(exceptions: Tuple[Type[BaseException], ...] | Type[BaseException]) -> Tuple[Type[BaseException], ...]:
    if isinstance(exceptions, tuple):
        return exceptions
    return (exceptions,)


def _is_coroutine_function(func: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(func)


__all__ = [
    "retry",
    "stop_after_attempt",
    "wait_exponential",
    "retry_if_exception_type",
]
