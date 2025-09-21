"""Lightweight stub of the OpenAI client for offline testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Dict


class RateLimitError(Exception):
    """Exception raised when rate limits are exceeded."""


class APITimeoutError(Exception):
    """Exception raised when the API times out."""


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Usage:
    total_tokens: int = 0


@dataclass
class _Response:
    choices: List[_Choice]
    usage: _Usage


class _Completions:
    async def create(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> _Response:
        last_message = messages[-1]["content"] if messages else ""
        reply = f"(stubbed {model}) {last_message}" if last_message else "(stubbed response)"
        return _Response(choices=[_Choice(_Message(reply))], usage=_Usage(total_tokens=len(reply.split())))


class _ChatNamespace:
    def __init__(self) -> None:
        self.completions = _Completions()


class AsyncOpenAI:
    def __init__(self, api_key: str | None = None, **_: Any) -> None:
        self.api_key = api_key
        self.chat = _ChatNamespace()


__all__ = [
    "AsyncOpenAI",
    "APITimeoutError",
    "RateLimitError",
]
