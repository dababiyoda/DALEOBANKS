"""Lightweight Thompson sampling bandit used for action selection."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional

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

    def select(
        self,
        available: Optional[Iterable[str]] = None,
        priors: Optional[Mapping[str, float]] = None,
    ) -> str:
        """Choose an arm by prior-weighted Thompson sampling.

        ``available`` is the complete permitted candidate set. An explicitly
        empty set means nothing is permitted, so the safe no-op ``REST`` is
        returned; it never falls back to every arm the bandit has seen (that
        would resurrect arms on cooldown or otherwise excluded).

        ``priors`` carries the policy's action probabilities (persona mix,
        drives, optimizer weights). Each arm's posterior sample is scaled by
        its prior relative to the strongest prior, so policy changes alter
        selection while measured rewards still move the posterior. An arm
        with a zero or missing prior is never chosen while any candidate has
        a positive prior.
        """
        if available is None:
            candidates = list(self._state.keys())
        else:
            candidates = list(available)
        if not candidates:
            logger.info("Bandit has no permitted candidates; resting")
            return "REST"
        for arm in candidates:
            self._state.setdefault(arm, ArmState())

        weights = {arm: 1.0 for arm in candidates}
        if priors is not None:
            raw = {arm: max(0.0, float(priors.get(arm, 0.0) or 0.0)) for arm in candidates}
            top = max(raw.values())
            if top > 0:
                weights = {arm: value / top for arm, value in raw.items()}
                candidates = [arm for arm in candidates if weights[arm] > 0]

        samples = {
            arm: random.betavariate(self._state[arm].alpha, self._state[arm].beta) * weights[arm]
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
