"""Phase 5: bounded curiosity bonus in the Thompson-sampling optimizer."""

import math

import numpy as np

from services.optimizer import Optimizer


def test_novelty_bonus_decays_with_pulls():
    optimizer = Optimizer()
    bonuses = optimizer.novelty_bonus({"untried": 0, "tried": 8, "worn": 99})

    assert bonuses["untried"] == optimizer.novelty_weight  # weight / sqrt(1)
    assert bonuses["untried"] > bonuses["tried"] > bonuses["worn"]
    assert math.isclose(bonuses["tried"], optimizer.novelty_weight / 3)


def test_novelty_bonus_is_capped_by_weight():
    optimizer = Optimizer()
    bonuses = optimizer.novelty_bonus({"a": 0, "b": 1}, weight=0.2)

    assert max(bonuses.values()) <= 0.2
    assert bonuses["a"] == 0.2


def test_thompson_sampling_prefers_unexplored_arm_when_posteriors_tie(monkeypatch):
    optimizer = Optimizer()

    # Make the posterior draw deterministic and identical for every arm so
    # only the novelty bonus can break the tie.
    monkeypatch.setattr(np.random, "beta", lambda a, b: 0.5)

    performance = {
        "topic": {
            "energy": {"mean_reward": 0.5, "count": 50},
            "frontier": {"mean_reward": 0.5, "count": 0},
        }
    }

    selected = optimizer._thompson_sample(performance)
    assert selected["topic"] == "frontier"


def test_novelty_cannot_override_clearly_better_arm(monkeypatch):
    optimizer = Optimizer()

    # Deterministic posterior means: strong arm well above weak arm by more
    # than the maximum possible bonus.
    def fake_beta(alpha, beta):
        return alpha / (alpha + beta)

    monkeypatch.setattr(np.random, "beta", fake_beta)

    performance = {
        "topic": {
            "strong": {"mean_reward": 0.9, "count": 40},
            "weak_new": {"mean_reward": 0.1, "count": 0},
        }
    }

    selected = optimizer._thompson_sample(performance)
    assert selected["topic"] == "strong"
