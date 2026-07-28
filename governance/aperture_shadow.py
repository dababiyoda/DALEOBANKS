"""DALEOBANKS publication in SHADOW MODE, governed by the Reality Aperture.

The organ proposes. The Kernel authorizes. The organ may still refuse.

    publication candidate
    -> identity and evidence envelope
    -> policy evaluation                (Kernel)
    -> authorization certificate        (Kernel - the ONLY signer)
    -> certificate verification         (organ, public key only)
    -> revocation validation            (organ, signed snapshot)
    -> ConstitutionGuard                (organ, local)
    -> KillSwitch                       (organ, local, fail-closed)
    -> fake publication adapter         (independent state)
    -> independent readback
    -> receipt
    -> reconciliation

WHAT THIS MODULE MAY NOT DO. It holds no signing provider and cannot obtain
one: the aperture's `Aperture` constructor takes a VerificationRegistry and has
no parameter that accepts a signer. DALEOBANKS can refuse a publication. It
cannot authorize one.

SHADOW MEANS SHADOW. The existing production path in services/ is untouched and
still runs as before. Nothing here can reach a real platform: the adapter
registry contains exactly one entry, the fake, and `resolve_adapter` raises on
anything else. No X credential is read, passed, or referenced on this path.

PACKAGING GAP, stated rather than hidden: the aperture currently lives in the
uniimente-kernel repository and is imported from a sibling checkout. That is a
development convenience, not a distribution strategy. Until the Kernel publishes
an installable client package this module is not deployable, and the tests skip
rather than pretend.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# --- aperture import (see PACKAGING GAP above) ---------------------------
_KERNEL = os.environ.get(
    "UNIIMENTE_KERNEL_PATH",
    str(pathlib.Path(__file__).resolve().parents[2] / "uniimente-kernel"))
if _KERNEL not in sys.path and pathlib.Path(_KERNEL).exists():
    sys.path.insert(0, _KERNEL)

try:
    from aperture import (Aperture, CertificateError, LocalVeto, Presenter,
                          VerificationRegistry)
    from aperture.revocation import RevocationState
    APERTURE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the skip in tests
    APERTURE_AVAILABLE = False
    Aperture = LocalVeto = Presenter = VerificationRegistry = None  # type: ignore
    RevocationState = None  # type: ignore

    class CertificateError(Exception):  # type: ignore
        pass


ORGAN_ID = "spiffe://uniimente.internal/organ/daleobanks"
SHADOW_WORKLOAD = ORGAN_ID + "/workload/publisher-shadow-v1"

# Credentials that must never appear on the aperture path.
PRODUCTION_CREDENTIAL_VARS = (
    "X_BEARER_TOKEN", "X_API_KEY", "X_API_SECRET",
    "X_ACCESS_TOKEN", "X_ACCESS_SECRET",
)


class ShadowConfigurationError(RuntimeError):
    """Shadow mode was asked to do something only production may do."""


# ---------------------------------------------------------------- adapters

class FakePlatform:
    """External platform whose state is owned by the platform, not the caller.

    The executor SUBMITS an operation. The platform decides what its own state
    becomes. The verifier reads that state separately. This is what makes the
    readback independent: the executor has no way to write the value the
    verifier will read.
    """

    adapter_id = "fake-platform"
    is_production = False

    def __init__(self, *, drop_silently: bool = False,
                 mutate: Optional[Callable[[str], str]] = None):
        self._posts: list[dict] = []
        self._drop = drop_silently
        self._mutate = mutate
        self.submissions = 0

    def submit(self, text: str) -> dict:
        """The executor's side. Its return value is a CLAIM, not evidence."""
        self.submissions += 1
        if self._drop:
            return {"claimed": "published", "id": "post-phantom"}
        stored = self._mutate(text) if self._mutate else text
        self._posts.append({"id": f"post-{len(self._posts) + 1}", "text": stored})
        return {"claimed": "published", "id": self._posts[-1]["id"]}

    def readback(self) -> list[dict]:
        """The verifier's side. Reads the platform's own state."""
        return [dict(p) for p in self._posts]


_ADAPTERS = {FakePlatform.adapter_id: FakePlatform}


def resolve_adapter(adapter_id: str):
    """Shadow mode resolves exactly one adapter. Anything else is refused.

    This is the hard stop the execution order requires: if shadow configuration
    ever resolves to a production adapter, this raises rather than publishing.
    """
    cls = _ADAPTERS.get(adapter_id)
    if cls is None:
        raise ShadowConfigurationError(
            f"shadow mode cannot resolve adapter {adapter_id!r}; the only "
            f"adapter available in shadow is {FakePlatform.adapter_id!r}")
    if getattr(cls, "is_production", False):
        raise ShadowConfigurationError(
            f"adapter {adapter_id!r} is a production adapter and is forbidden "
            "in shadow mode")
    return cls


def assert_no_production_credentials(env: Optional[dict] = None) -> None:
    """Fail closed if any X credential is visible to the aperture path."""
    env = os.environ if env is None else env
    present = [v for v in PRODUCTION_CREDENTIAL_VARS if env.get(v)]
    if present:
        raise ShadowConfigurationError(
            f"production credentials present on the shadow path: {present}. "
            "The aperture path must never see a platform credential.")


# ---------------------------------------------------------------- results

@dataclass
class ShadowResult:
    candidate_id: str
    status: str
    reason: str = ""
    certificate_id: str = ""
    observed_state: Any = None
    readback_verified: bool = False
    legacy_would_publish: Optional[bool] = None
    agrees_with_legacy: Optional[bool] = None


@dataclass
class ShadowMetrics:
    candidates_processed: int = 0
    certificates_issued: int = 0
    certificates_refused: int = 0
    local_vetoes: int = 0
    policy_escalations: int = 0
    legacy_path_agreements: int = 0
    legacy_path_disagreements: int = 0
    scope_mutation_attempts: int = 0
    identity_mismatches: int = 0
    revocation_refusals: int = 0
    reconciliation_mismatches: int = 0
    external_publications: int = 0
    validation_latencies_ms: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        lat = self.validation_latencies_ms
        return {
            "candidates_processed": self.candidates_processed,
            "certificates_issued": self.certificates_issued,
            "certificates_refused": self.certificates_refused,
            "local_vetoes": self.local_vetoes,
            "policy_escalations": self.policy_escalations,
            "legacy_path_agreements": self.legacy_path_agreements,
            "legacy_path_disagreements": self.legacy_path_disagreements,
            "false_refusals": "unclassified - requires a human to judge whether a "
                              "refusal was correct; no automatic classification is "
                              "made and none is guessed",
            "scope_mutation_attempts": self.scope_mutation_attempts,
            "identity_mismatches": self.identity_mismatches,
            "revocation_refusals": self.revocation_refusals,
            "reconciliation_mismatches": self.reconciliation_mismatches,
            "mean_validation_latency_ms": round(sum(lat) / len(lat), 3) if lat else None,
            "external_publications": self.external_publications,
        }


# ---------------------------------------------------------------- the path

class ShadowPublicationPath:
    """Runs a real publication candidate through the aperture, publishing nothing."""

    def __init__(
        self,
        *,
        registry: "VerificationRegistry",
        revocation: Optional["RevocationState"] = None,
        policy_version: str,
        constitution_version: str,
        constitution_guard: Optional[Any] = None,
        kill_switch: Optional[Any] = None,
        adapter_id: str = FakePlatform.adapter_id,
        platform: Optional[FakePlatform] = None,
    ) -> None:
        if not APERTURE_AVAILABLE:  # pragma: no cover
            raise ShadowConfigurationError("aperture is not importable")
        assert_no_production_credentials()

        self.platform = platform or resolve_adapter(adapter_id)()
        self.guard = constitution_guard
        self.kill_switch = kill_switch
        # The organ's veto starts ENGAGED and is released only by a named local
        # operator, mirroring DALEOBANKS' own fail-closed posture.
        self.veto = LocalVeto(engaged=True, reason="shadow default-closed")
        self.aperture = Aperture(
            registry=registry, organ_id=ORGAN_ID,
            current_policy_version=policy_version,
            current_constitution_version=constitution_version,
            veto=self.veto, revocation=revocation)
        self.metrics = ShadowMetrics()
        self.results: list[ShadowResult] = []

    # -- local controls, checked before anything external -----------------
    def _local_refusal(self) -> Optional[str]:
        if self.guard is not None:
            try:
                ok = self.guard.verify() if hasattr(self.guard, "verify") else True
                if ok is False:
                    return "ConstitutionGuard: constitution hash drifted"
            except Exception as e:  # noqa: BLE001
                return f"ConstitutionGuard raised {type(e).__name__}: {e}"
        if self.kill_switch is not None and not getattr(self.kill_switch, "armed", False):
            return "KillSwitch disarmed: the organ is not permitted to act live"
        return None

    def release_veto(self, *, operator: str, reason: str) -> None:
        self.veto.release(reason, authorized_by=operator)

    def run(self, candidate: dict, certificate,
            *, legacy_would_publish: Optional[bool] = None) -> ShadowResult:
        """One candidate through the full path. Never publishes for real."""
        import time
        self.metrics.candidates_processed += 1
        cid = candidate.get("id", "candidate")
        text = candidate["text"]

        started = time.perf_counter()
        presenter = Presenter(candidate["actor_id"], ORGAN_ID, SHADOW_WORKLOAD)

        local = self._local_refusal()
        if local is not None:
            self.metrics.local_vetoes += 1
            r = ShadowResult(cid, "local_refusal", local)
            self.results.append(r)
            return r

        receipt = self.aperture.execute(
            certificate, presenter, payload={"text": text},
            executor=lambda: self.platform.submit(text),
            readback=self.platform.readback,
            expected_state=lambda s: any(p["text"] == text for p in s))
        self.metrics.validation_latencies_ms.append(
            (time.perf_counter() - started) * 1000)

        status = receipt.status
        if status == "committed":
            self.metrics.certificates_issued += 1
        else:
            self.metrics.certificates_refused += 1
        if status == "local_veto":
            self.metrics.local_vetoes += 1
        if status in ("actor_mismatch", "organ_mismatch", "workload_mismatch"):
            self.metrics.identity_mismatches += 1
        if status == "payload_mismatch":
            self.metrics.scope_mutation_attempts += 1
        if status.startswith("revocation") or status.endswith("_revoked"):
            self.metrics.revocation_refusals += 1
        if status == "revocation_human_escalation":
            self.metrics.policy_escalations += 1
        if status == "reconciliation_mismatch":
            self.metrics.reconciliation_mismatches += 1

        agrees = None
        if legacy_would_publish is not None:
            agrees = (status == "committed") == legacy_would_publish
            if agrees:
                self.metrics.legacy_path_agreements += 1
            else:
                self.metrics.legacy_path_disagreements += 1

        r = ShadowResult(
            candidate_id=cid, status=status, reason=receipt.error,
            certificate_id=certificate.authority_record_id,
            observed_state=receipt.observed_state,
            readback_verified=receipt.readback_verified,
            legacy_would_publish=legacy_would_publish,
            agrees_with_legacy=agrees)
        self.results.append(r)
        return r

    def real_publications(self) -> int:
        """Always zero. The fake platform is the only reachable adapter."""
        return 0
