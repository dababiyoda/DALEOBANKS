"""Supervised cognitive loop: keeps the mind alive 24/7 without drifting.

Distributed-systems supervision pattern. Each stage (perceive, plan, act,
reflect — or any scheduled job) runs isolated, so a failure in one organ
never kills the loop. Repeated consecutive failures trip a breaker that
disarms live posting via the kill switch — the system fails toward silence,
never toward runaway posting — and every error and breaker trip is recorded
in the decision ledger.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Any, Awaitable, Callable, Dict, Optional

from services.ledger import DecisionLedger, KillSwitch
from services.logging_utils import get_logger

logger = get_logger(__name__)


class Heartbeat:
    """Supervises async stages with a consecutive-failure breaker."""

    def __init__(
        self,
        kill_switch: KillSwitch,
        ledger: DecisionLedger,
        max_consecutive_failures: int = 3,
    ) -> None:
        self.kill_switch = kill_switch
        self.ledger = ledger
        self.max_consecutive_failures = max_consecutive_failures
        self._failures = 0
        self._running = False
        self._breaker_tripped = False

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    @property
    def breaker_tripped(self) -> bool:
        return self._breaker_tripped

    def record_success(self, stage: str) -> None:
        """A stage completed; the failure streak resets."""
        self._failures = 0

    def record_failure(self, stage: str, exc: BaseException) -> None:
        """A stage failed; ledger it and trip the breaker if streak exceeds cap."""
        self._failures += 1
        self.ledger.record(
            "cycle_error",
            {"stage": stage, "error": str(exc), "consecutive": self._failures},
        )
        logger.error("heartbeat stage %s failed (%d): %s", stage, self._failures, exc)
        if self._failures >= self.max_consecutive_failures:
            self._trip_breaker()

    def _trip_breaker(self) -> None:
        # Fail-safe to silence: disarm live posting rather than keep acting.
        self.kill_switch.set_armed(False, reason="heartbeat_breaker")
        self.ledger.record(
            "breaker_tripped",
            {"disarmed_at": datetime.now(UTC).isoformat(),
             "consecutive_failures": self._failures},
        )
        self._breaker_tripped = True
        logger.critical("heartbeat breaker tripped -> live posting disarmed")

    def reset_breaker(self) -> None:
        """Manual re-arm path: clears the streak and breaker state.

        Deliberately does NOT re-arm the kill switch — going live again is a
        human decision made through the existing LIVE toggle.
        """
        self._failures = 0
        self._breaker_tripped = False
        self.ledger.record("breaker_reset", {})

    async def run_cycle(self, stages: Dict[str, Callable[[], Awaitable[Any]]]) -> None:
        """Run one perceive/plan/act/reflect cycle with per-stage isolation."""
        for name, stage in stages.items():
            try:
                await stage()
                self.record_success(name)
            except Exception as exc:
                self.record_failure(name, exc)
                if self._breaker_tripped:
                    return

    async def loop(
        self,
        stages: Dict[str, Callable[[], Awaitable[Any]]],
        interval_seconds: int = 300,
    ) -> None:
        self._running = True
        while self._running:
            await self.run_cycle(stages)
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False

    def supervise(
        self, stage: str, fn: Callable[[], Awaitable[Any]]
    ) -> Callable[[], Awaitable[Any]]:
        """Wrap a job callable so the scheduler runs it under supervision.

        Any exception that escapes the job is ledgered and counted toward
        the breaker instead of propagating into the scheduler.
        """

        async def _supervised() -> None:
            try:
                await fn()
                self.record_success(stage)
            except Exception as exc:
                self.record_failure(stage, exc)

        _supervised.__name__ = f"supervised_{stage}"
        return _supervised


__all__ = ["Heartbeat"]
