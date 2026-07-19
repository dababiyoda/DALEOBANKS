"""Consequence Gate wiring for the organ's publishing action family.

Every live outbound post crosses the kernel ConsequenceGate:

    evidence -> authority (capability grant) -> commit witness
    -> one-time execution -> receipt -> postcondition -> reconciliation
    -> outcome

The boundary is total: ``publish_post`` sends *every* attempt through
``gate.execute``, including attempts with no grant (which the gate
rejects and ledgers). A rejection fails toward silence: the caller
receives a dry-run result, exactly as it does for a disarmed kill
switch. There is no unmediated live path in this family.

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

from services.ledger import get_kill_switch, get_ledger
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


__all__ = [
    "configure",
    "get_gate",
    "reset_gate",
    "mint_publish_grant",
    "publish_post",
]
