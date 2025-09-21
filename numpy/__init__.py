"""Lightweight subset of NumPy's random module used for testing.

This shim provides just enough functionality for the project test
suite without requiring the heavy NumPy dependency at runtime.  Only
`np.random.beta`, `np.random.normal`, `np.random.random`, and
`np.random.seed` are implemented because they are the only APIs used by
our code and tests.  The implementations delegate to Python's built-in
`random` module which offers equivalent stochastic behaviour for the
use cases in the tests.
"""

from __future__ import annotations

import random as _random
from typing import Any


class _RandomModule:
    """Minimal stand-in for :mod:`numpy.random` used in tests.

    The methods intentionally mirror the NumPy API shape that the code
    relies on.  They simply forward to the corresponding functions in
    :mod:`random` while enforcing valid parameter ranges so behaviour is
    predictable and errors are informative.
    """

    def beta(self, alpha: float, beta: float) -> float:
        """Draw a beta-distributed sample."""
        if alpha <= 0 or beta <= 0:
            raise ValueError("alpha and beta must be > 0")
        return _random.betavariate(alpha, beta)

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Draw from a normal (Gaussian) distribution."""
        if sigma < 0:
            raise ValueError("sigma must be non-negative")
        return _random.gauss(mu, sigma)

    def random(self) -> float:
        """Return a float in the half-open interval [0.0, 1.0)."""
        return _random.random()

    def seed(self, seed: Any) -> None:
        """Seed the underlying random number generator."""
        _random.seed(seed)


random = _RandomModule()

__all__ = ["random"]
