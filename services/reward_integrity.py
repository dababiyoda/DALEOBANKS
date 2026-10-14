"""Engagement-integrity gate for optimizer rewards.

Engagement (likes, reposts, impressions — the ``fame`` term) is the easiest
signal to inflate and the one most correlated with ragebait, false certainty
and manufactured outrage. It therefore earns reward only while the integrity
record for the same window is clean. When any integrity incident is present
(ethics violations, mutes/blocks, issued corrections, misinformation flags,
unsupported-claim flags) the reward falls back to the score computed without
engagement: reach gained while trust is deteriorating is not success.

The gate can only lower a reward, never raise it.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

INTEGRITY_INCIDENT_KINDS = frozenset(
    {
        "ethics_violation",
        "mute_detected",
        "block_detected",
        "correction_issued",
        "misinformation_flag",
        "unsupported_claim_flag",
        "manipulation_flag",
    }
)


def count_integrity_incidents(action_kinds: Iterable[str]) -> int:
    return sum(1 for kind in action_kinds if kind in INTEGRITY_INCIDENT_KINDS)


def qualify_reward(
    *,
    j_score: float,
    j_score_without_engagement: float,
    integrity_incidents: int,
) -> Dict[str, Any]:
    j_score = float(j_score or 0.0)
    floor = float(j_score_without_engagement or 0.0)
    if integrity_incidents > 0:
        reward = min(j_score, floor)
        return {
            "qualified_reward": round(max(reward, 0.0), 3),
            "engagement_credit": False,
            "reason": f"{integrity_incidents} integrity incident(s) in window; engagement earns no reward",
        }
    return {
        "qualified_reward": round(max(j_score, 0.0), 3),
        "engagement_credit": True,
        "reason": "integrity record clean for window",
    }


__all__ = ["INTEGRITY_INCIDENT_KINDS", "count_integrity_incidents", "qualify_reward"]
