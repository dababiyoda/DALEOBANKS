"""Consequence Gate wiring for the organ's external action families.

Every live outbound effect crosses the kernel ConsequenceGate:

    evidence -> authority (capability grant) -> commit witness
    -> one-time execution -> receipt -> postcondition -> reconciliation
    -> outcome

Two families are mediated here:

1. Publishing (``publish_post``) — posts, replies, quotes on every
   social platform adapter.
2. Engagement/DM writes (``execute_write``) — like, unlike, repost,
   follow and send_dm on X. Every attempt crosses the gate, including
   attempts with no grant (which the gate rejects and ledgers).

The boundary is total within each family: a rejection fails toward
silence — the caller receives the family's dry-run result, exactly as
it does for a disarmed kill switch. There is no unmediated live path.

Authority posture: grants mint only from verified operator approvals.
The approval verifier is injected at ``configure`` time (app startup
wires it to the operator line); the lazy default denies everything,
so an unconfigured organ is a silent organ, never an open one.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from typing import Any, Callable, Dict, Optional, Tuple

from uniimente_kernel.capability import (
    CapabilityService,
    GrantRecord,
    InMemoryGrantStore,
)
from uniimente_kernel.commit_witness import CommitWitness
from uniimente_kernel.events import EventSpine
from uniimente_kernel.gate import ConsequenceGate

from services.ledger import get_kill_switch, get_ledger, get_rate_governor
from services.logging_utils import get_logger
from services.social_base import SocialPostResult

logger = get_logger(__name__)

ORG = "spiffe://uniimente.internal/organ/daleobanks"
AGENT = ORG + "/agent/publisher"
LEGAL_PRINCIPAL = "alfonso-lopez"
POLICY_VERSION = "1.0.0"

_grant_store: Optional[InMemoryGrantStore] = None
_capability: Optional[CapabilityService] = None
_gate: Optional[ConsequenceGate] = None
# Active grant per (platform, kind): the organ's publishing authority
# registry. Minting a grant for a pair replaces the previous entry.
_active_grants: Dict[Tuple[str, str], str] = {}


def configure(
    *,
    approval_verifier: Callable[[str], bool],
    grant_store: Optional[InMemoryGrantStore] = None,
) -> ConsequenceGate:
    """Wire the gate over the organ's shared ledger and kill switch.

    ``approval_verifier`` decides whether an approval request id
    represents a verified operator approval; grants mint only behind it.
    """
    global _grant_store, _capability, _gate
    ledger = get_ledger()
    _grant_store = grant_store or InMemoryGrantStore()
    _capability = CapabilityService(
        _grant_store, ledger, approval_verifier=approval_verifier,
    )
    spine = EventSpine(
        ledger, source=ORG, actor=AGENT,
        legal_principal=LEGAL_PRINCIPAL, policy_version=POLICY_VERSION,
    )
    witness = CommitWitness(ledger, kill_switch=get_kill_switch())
    _gate = ConsequenceGate(
        ledger, capability=_capability, witness=witness, spine=spine,
    )
    return _gate


def get_gate() -> ConsequenceGate:
    """The organ's gate. Unconfigured means deny-all, never unmediated."""
    global _gate
    if _gate is None:
        logger.warning("gate used before configure(); defaulting to deny-all")
        configure(approval_verifier=lambda request_id: False)
    return _gate


def reset_gate() -> None:
    """Drop gate state (tests). Shared ledger/switch reset separately."""
    global _grant_store, _capability, _gate
    _grant_store = None
    _capability = None
    _gate = None
    _active_grants.clear()


def mint_publish_grant(
    *,
    platform: str,
    kind: str = "post",
    approval_request_id: str,
    maximum_uses: int = 30,
    objective: Optional[str] = None,
) -> GrantRecord:
    """Mint and register the active publishing grant for (platform, kind).

    Raises CapabilityError if the approval does not verify. Authority
    starts narrow: one platform, one kind, bounded uses, shadow stage.
    """
    if _capability is None:
        get_gate()
    grant = GrantRecord(
        grantee=AGENT,
        granted_by=LEGAL_PRINCIPAL,
        legal_actor=LEGAL_PRINCIPAL,
        objective=objective or f"publish {kind} on {platform}",
        permitted_actions=[f"publish.{kind}"],
        resource=platform,
        maximum_uses=maximum_uses,
        initial_stage="shadow",
    )
    minted = _capability.mint(grant, approval_request_id=approval_request_id)
    _active_grants[(platform, kind)] = minted.grant_id
    return minted


def _await_in_thread(coro: Any) -> Any:
    """Run one coroutine on a fresh loop in a worker thread.

    The Commit Witness executes synchronously; the platform adapters are
    async. A dedicated thread with its own loop keeps one-time-execution
    semantics without nesting loops in the caller's thread.
    """
    box: Dict[str, Any] = {}

    def runner() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001 - re-raised in caller thread
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _live_receipt(result: Dict[str, Any]) -> bool:
    return bool(result.get("post_id")) and result.get("dry_run") is False


async def publish_post(
    *,
    platform: str,
    kind: str,
    content: str,
    impl: Callable[..., Any],
    impl_kwargs: Dict[str, Any],
    dry_run: Callable[..., Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> SocialPostResult:
    """Mediate one publish attempt through the ConsequenceGate.

    ``impl`` is the adapter's ``_publish_impl``; ``dry_run`` its
    ``_dry_run``. The witness never sees the platform client: the
    executor reduces the coroutine to a JSON-safe receipt dict, and the
    returned ``SocialPostResult`` is rebuilt from it.
    """
    gate = get_gate()
    grant_id = _active_grants.get((platform, kind), "none")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    parameters = {
        "content_sha256": content_hash,
        "in_reply_to": impl_kwargs.get("in_reply_to"),
        "quote_to": impl_kwargs.get("quote_to"),
    }

    def executor() -> Dict[str, Any]:
        result = _await_in_thread(impl(**impl_kwargs))
        return {
            "platform": result.platform,
            "post_id": result.post_id,
            "dry_run": result.dry_run,
        }

    outcome = gate.execute(
        grant_id=grant_id,
        action_type=f"publish.{kind}",
        resource=platform,
        parameters=parameters,
        executor=executor,
        postconditions={"live_receipt": _live_receipt},
        expected_consequence=f"{kind} live on {platform}",
        subject=f"{platform}:{kind}",
    )

    if outcome.status in ("committed", "deduplicated") and outcome.receipt is not None:
        receipt = outcome.receipt.result or {}
        post_id = receipt.get("post_id", "")
        if outcome.status == "committed" and post_id:
            # Durable commit -> post_id correlation for the outcome pull.
            # The witness receipt is runtime-only; this chained event is
            # what lets a later job find the committed action's external
            # artifact and attach what actually happened to the commit.
            gate.spine.chain(
                "consequence.receipt",
                outcome.final_event,
                data={"platform": platform, "kind": kind, "post_id": str(post_id)},
            )
        return SocialPostResult(
            platform=receipt.get("platform", platform),
            post_id=receipt.get("post_id", ""),
            dry_run=bool(receipt.get("dry_run", False)),
            meta=metadata,
        )

    # rejected | failed | postcondition_failed: fail toward silence.
    # The gate has already ledgered and chained the honest record.
    logger.warning(
        "publish %s on %s not committed (status=%s); returning dry run",
        kind, platform, outcome.status,
    )
    return await dry_run(kind=kind, metadata=metadata)


# --- Engagement/DM write family -------------------------------------------

WRITE_FAMILIES = ("like", "unlike", "repost", "send_dm", "follow")


class WriteExecutionRefused(RuntimeError):
    """The transport refused or failed inside a gated write executor.

    Raised when the adapter's write helper returns the injected sentinel
    (dry run, circuit open, rate-limit exhaustion, provider error). The
    gate receipts the attempt as ``consequence.failed`` — never as a
    success — and the family method returns its dry-run result.
    """


def mint_write_grant(
    *,
    platform: str,
    family: str,
    approval_request_id: str,
    maximum_uses: int = 30,
    objective: Optional[str] = None,
) -> GrantRecord:
    """Mint and register the active write grant for (platform, family).

    ``family`` must be one of WRITE_FAMILIES. Raises CapabilityError if
    the approval does not verify. Authority starts narrow: one platform,
    one family, bounded uses, shadow stage.
    """
    if family not in WRITE_FAMILIES:
        raise ValueError(f"unknown write family: {family!r}")
    if _capability is None:
        get_gate()
    grant = GrantRecord(
        grantee=AGENT,
        granted_by=LEGAL_PRINCIPAL,
        legal_actor=LEGAL_PRINCIPAL,
        objective=objective or f"{family} on {platform}",
        permitted_actions=[f"write.{family}"],
        resource=platform,
        maximum_uses=maximum_uses,
        initial_stage="shadow",
    )
    minted = _capability.mint(grant, approval_request_id=approval_request_id)
    _active_grants[(platform, f"write.{family}")] = minted.grant_id
    return minted


async def execute_write(
    *,
    platform: str,
    family: str,
    target: str,
    impl: Callable[..., Any],
    impl_kwargs: Dict[str, Any],
    dry_run_result: Any,
    text: Optional[str] = None,
) -> Any:
    """Mediate one engagement/DM write through the ConsequenceGate.

    Carries the same safety envelope as ``BaseSocialClient.publish`` so
    every write family inherits it by construction: the attempt is
    ledgered, a disarmed kill switch or a saturated rate governor fails
    toward silence before authority is consulted, and only then does
    the attempt cross the gate.

    ``impl`` is the client's ``_execute_write`` transport; the witness
    never sees the platform client. The executor injects a unique
    sentinel as the transport's ``default_result``: a sentinel return
    means the transport refused or failed without producing an effect,
    which is honestly receipted as a failure instead of the family's
    silent-success default.

    Returns True when the effect is committed (or already existed —
    these families set state, so deduplication means the desired state
    holds); otherwise the family's ``dry_run_result``.
    """
    if family not in WRITE_FAMILIES:
        raise ValueError(f"unknown write family: {family!r}")

    ledger = get_ledger()
    attempt: Dict[str, Any] = {"platform": platform, "family": family,
                               "target": target}
    if text is not None:
        # The ledger carries proof of content, never the content itself.
        attempt["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ledger.record("write_attempt", attempt)

    if not get_kill_switch().armed:
        ledger.record(
            "write_gated",
            {"platform": platform, "family": family, "reason": "kill_switch"},
        )
        return dry_run_result
    if not get_rate_governor().allow(platform):
        ledger.record(
            "write_gated",
            {"platform": platform, "family": family, "reason": "rate_governor"},
        )
        logger.warning("Rate governor blocked live %s on %s", family, platform)
        return dry_run_result

    gate = get_gate()
    grant_id = _active_grants.get((platform, f"write.{family}"), "none")
    parameters: Dict[str, Any] = {"family": family, "target": target}
    if text is not None:
        # The ledger carries proof of content, never the content itself.
        parameters["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    sentinel = object()

    def executor() -> Dict[str, Any]:
        result = _await_in_thread(impl(default_result=sentinel, **impl_kwargs))
        if result is sentinel:
            raise WriteExecutionRefused(
                f"{family} on {platform} refused or failed at transport"
            )
        return {"family": family, "platform": platform, "ok": True}

    outcome = gate.execute(
        grant_id=grant_id,
        action_type=f"write.{family}",
        resource=platform,
        target=target,
        parameters=parameters,
        executor=executor,
        expected_consequence=f"{family} effect on {platform}",
        subject=f"{platform}:write.{family}:{target}",
    )

    ledger.record(
        "write_result",
        {"platform": platform, "family": family, "target": target,
         "status": outcome.status},
    )

    if outcome.status in ("committed", "deduplicated"):
        return True

    # rejected | failed: fail toward silence. The gate has already
    # ledgered and chained the honest record.
    logger.warning(
        "write %s on %s not committed (status=%s); returning dry-run result",
        family, platform, outcome.status,
    )
    return dry_run_result


# --- Outcomes ----------------------------------------------------------------


def record_outcome_for(
    commit_event_id: str,
    *,
    external_observation: str,
    result_class: str,
    expected_vs_actual: str,
    validation_status: str = "externally_verified",
    evidence_refs: Optional[list] = None,
    learning: Optional[str] = None,
):
    """Attach what actually happened to a committed consequence.

    Rebuilds the commit event's identity from the ledger — the only
    part ``record_outcome`` needs is the id it chains to — and refuses
    unknown ids: an outcome chained to nothing is a fabrication.
    """
    from uniimente_kernel.events import Event

    gate = get_gate()
    payload = gate.spine.get(commit_event_id)
    if payload is None:
        raise KeyError(f"unknown commit event: {commit_event_id}")
    parent = Event(
        type=payload.get("type", ""),
        source=payload.get("source", ORG),
        actor=payload.get("actor", AGENT),
        legal_principal=payload.get("legal_principal", LEGAL_PRINCIPAL),
        sensitivity=payload.get("sensitivity", "internal"),
        causal_parent=payload.get("causal_parent"),
        id=payload["id"],
    )
    return gate.record_outcome(
        parent,
        external_observation=external_observation,
        result_class=result_class,
        expected_vs_actual=expected_vs_actual,
        validation_status=validation_status,
        evidence_refs=evidence_refs,
        learning=learning,
    )


__all__ = [
    "WRITE_FAMILIES",
    "WriteExecutionRefused",
    "configure",
    "get_gate",
    "reset_gate",
    "mint_publish_grant",
    "mint_write_grant",
    "publish_post",
    "execute_write",
    "record_outcome_for",
]
