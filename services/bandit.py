"""Lightweight Thompson sampling bandit used for action selection."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from services.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class ArmState:
    alpha: float = 2.0
    beta: float = 2.0
    pulls: int = 0


class ThompsonBandit:
    """Beta-Bernoulli Thompson sampler for discrete actions."""

    def __init__(self, arms: Iterable[str] | None = None) -> None:
        self._state: Dict[str, ArmState] = {}
        if arms:
            for arm in arms:
                self._state[arm] = ArmState()

    def select(self, available: Optional[Iterable[str]] = None) -> str:
        candidates = list(available) if available else list(self._state.keys())
        if not candidates:
            logger.info("Bandit has no candidates; adding placeholder arm")
            candidates = ["POST_PROPOSAL"]
        for arm in candidates:
            self._state.setdefault(arm, ArmState())

        samples = {
            arm: random.betavariate(self._state[arm].alpha, self._state[arm].beta)
            for arm in candidates
        }
        chosen = max(samples, key=samples.get)
        logger.debug("Bandit sampled %s -> %s", samples, chosen)
        return chosen

    def record_outcome(self, arm: str, reward: float) -> None:
        state = self._state.setdefault(arm, ArmState())
        reward = max(0.0, min(1.0, reward))
        state.alpha += reward
        state.beta += 1.0 - reward
        state.pulls += 1
        logger.debug("Updated bandit arm %s -> alpha=%.2f beta=%.2f pulls=%d", arm, state.alpha, state.beta, state.pulls)

    def state(self) -> Dict[str, ArmState]:
        return self._state


__all__ = ["ThompsonBandit", "ArmState"]
