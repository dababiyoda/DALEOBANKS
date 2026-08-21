"""Scheduled outcome pull: attach observed reality to committed publishes.

Doctrine: an executed action without its outcome is incomplete and
blocks autonomy promotion. Zero response is a negative result, never an
absence. This module finds committed publishes (via their chained
``consequence.receipt`` events) that have no outcome yet, pulls their
engagement metrics from the platform, and records what actually
happened through ``gate.record_outcome_for`` — chained to the commit.

Two honesty rules:

1. Receipts younger than ``min_age_hours`` are not eligible. A post
   pulled one minute after commit would record ``zero_response`` for a
   post that has not lived yet — a permanent negative record written
   too early is a lie about lifetime performance.
2. A post the platform returns no metrics for is skipped, not
   recorded. The pull is recurring; absence of observation is not
   evidence of absence. Reconciliation of tombstoned posts is future
   work, deliberately not guessed at here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.gate import record_outcome_for
from services.ledger import get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

METRIC_KEYS = (
    "like_count",
    "retweet_count",
    "reply_count",
    "quote_count",
    "impression_count",
)

DEFAULT_MIN_AGE_HOURS = 6.0


def classify(metrics: Dict[str, Any]) -> str:
    """Mechanical result class: any observed interaction is positive."""
    total = sum(int(metrics.get(k, 0) or 0) for k in METRIC_KEYS)
    return "positive" if total > 0 else "zero_response"


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pending_receipts(
    ledger: Any, *, min_age_hours: float, now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Committed publishes with a post_id, old enough, and no outcome yet."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=min_age_hours)
    covered = {
        e["payload"].get("causal_parent")
        for e in ledger.replay("consequence.outcome")
    }
    pending: List[Dict[str, Any]] = []
    for entry in ledger.replay("consequence.receipt"):
        payload = entry["payload"]
        data = payload.get("data", {})
        if not data.get("post_id"):
            continue
        if payload.get("causal_parent") in covered:
            continue
        stamp = _parse_time(payload.get("time"))
        if stamp is not None and stamp > cutoff:
            continue  # too young to judge honestly
        pending.append(payload)
    return pending


async def pull_publish_outcomes(
    x_client: Any,
    *,
    limit: int = 100,
    min_age_hours: float = DEFAULT_MIN_AGE_HOURS,
) -> Dict[str, Any]:
    """Record outcomes for committed publishes lacking them.

    One batched read for all pending posts; one chained outcome per
    observed post. Returns a summary for the scheduler's own logs.
    """
    ledger = get_ledger()
    pending = _pending_receipts(ledger, min_age_hours=min_age_hours)[:limit]
    if not pending or x_client is None:
        return {"pending": len(pending), "recorded": 0, "skipped": 0}

    by_post_id = {str(r["data"]["post_id"]): r for r in pending}
    metrics = await x_client.metrics_for(list(by_post_id.keys()))
    # Platform ids come back as ints or strings depending on the client;
    # normalize once so either shape resolves.
    normalized = {str(k): v for k, v in (metrics or {}).items()}

    recorded = 0
    skipped = 0
    for post_id, receipt in by_post_id.items():
        observed = normalized.get(post_id)
        if not observed:
            skipped += 1
            continue
        total = sum(int(observed.get(k, 0) or 0) for k in METRIC_KEYS)
        observation = json.dumps(
            {"post_id": post_id, "metrics": observed}, sort_keys=True
        )
        # The evidence ref commits to the exact observation bytes.
        digest = hashlib.sha256(observation.encode("utf-8")).hexdigest()
        record_outcome_for(
            receipt["causal_parent"],
            external_observation=observation,
            result_class=classify(observed),
            expected_vs_actual=(
                f"expected consequence: post live on "
                f"{receipt['data'].get('platform', 'x')}; "
                f"observed engagement: {total} interactions"
            ),
            validation_status="externally_verified",
            evidence_refs=[f"sha256:{digest}"],
        )
        recorded += 1

    summary = {"pending": len(pending), "recorded": recorded, "skipped": skipped}
    logger.info("outcome pull: %s", summary)
    return summary


__all__ = [
    "DEFAULT_MIN_AGE_HOURS",
    "METRIC_KEYS",
    "classify",
    "pull_publish_outcomes",
]
