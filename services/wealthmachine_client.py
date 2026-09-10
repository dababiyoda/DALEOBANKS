"""Bridge to WealthMachineIntelligence: opportunity out, assessment back.

Modes (env ``WEALTHMACHINE_MODE``, default resolves automatically):

- ``http``  POST the OpportunityPacket wire payload to
            ``{WEALTHMACHINE_URL}/api/opportunities/intake`` and validate the
            returned VentureAssessment. Used once the WealthMachine repo
            exposes its intake endpoint.
- ``mock``  a local, deterministic scorer with the same contract, so the
            whole loop runs offline with no credentials. Default when no
            ``WEALTHMACHINE_URL`` is configured.

Assessments never execute anything. ``assessment_to_actions`` converts an
assessment into drafts (validation plan, landing-page copy, buyer-interview
script, outreach draft) plus an ApprovalRequest — the human decides.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional

from db.models import ApprovalRequest, MediaAssetDraft, OpportunityPacket, VentureAssessment
from services.bridge_security import (
    BridgeSecurityError,
    NonceCache,
    build_headers,
    signing_key,
    verify_headers,
    body_digest,
)
from adapters.contract_validation import strict_json
from events.bridge_state import BridgeState
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger
from services.venture_protocol import SCHEMA_VERSION, packet_to_wire, validate_assessment_wire

logger = get_logger(__name__)

_LEGAL_RISK_FLAGS = {"legal_risk", "regulated_product", "licensing_required"}


class CircuitOpenError(ConnectionError):
    """Too many consecutive bridge failures — failing closed for a cooldown."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BridgeSecurityError('adapter redirects refused; credentials are recipient-bound')


class WealthMachineClient:
    # Circuit breaker: after this many consecutive transport failures the
    # bridge opens and fails closed for a cooldown instead of hammering a
    # degraded remote.
    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 300

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._response_nonces = None

    def close(self):
        if self._response_nonces is not None:
            self._response_nonces.close()
            self._response_nonces = None

    def _durable_state(self):
        if self._response_nonces is None:
            self._response_nonces = BridgeState(
                os.getenv('UNIIMENTE_BRIDGE_STATE_PATH', ''),
                os.getenv('UNIIMENTE_CONSTITUTION_HASH', ''), owner='daleobanks',
                legal_principal=os.getenv('UNIIMENTE_LEGAL_PRINCIPAL', ''))
        return self._response_nonces

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    @property
    def url(self) -> str:
        return os.getenv("WEALTHMACHINE_URL", "").rstrip("/")

    @property
    def mode(self) -> str:
        configured = os.getenv("WEALTHMACHINE_MODE", "").lower()
        if configured in ("mock", "http"):
            return configured
        return "http" if self.url else "mock"

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    def evaluate(self, packet: OpportunityPacket) -> VentureAssessment:
        if self.mode == "http":
            assessment = self._evaluate_http(packet)
        else:
            assessment = self._evaluate_mock(packet)
        self.ledger.record("venture_assessment", {
            "packet_id": packet.id,
            "go_no_go": assessment.go_no_go,
            "score": assessment.opportunity_score,
            "mode": self.mode,
        })
        return assessment

    def _evaluate_http(self, packet: OpportunityPacket) -> VentureAssessment:
        import time as _time
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        if (os.getenv('UNIIMENTE_BRIDGE_MODE') != 'synthetic-localhost'
                or parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.username or parsed.password):
            raise BridgeSecurityError('live Kernel-mediated adapter not configured; direct organ bypass refused')

        if _time.time() < self._circuit_open_until:
            raise CircuitOpenError(
                "bridge circuit is open after repeated failures — failing closed"
            )

        body = json.dumps(packet_to_wire(packet)).encode()
        headers = {"Content-Type": "application/json"}
        token = os.getenv("WEALTHMACHINE_INTAKE_TOKEN", "")
        if not token.strip():
            raise BridgeSecurityError('verified JWT admission token required')
        # This is a JWT supplied by the isolated test fixture, not issued here.
        # WMI verifies signature/issuer/audience/expiry and sender-to-sub binding.
        headers["Authorization"] = f"Bearer {token}"
        # Signed transport: identity, timestamp, nonce, idempotency key.
        # The packet id doubles as the idempotency key — resending the same
        # packet must not run the engine twice.
        headers.update(build_headers(
            body, identity="daleobanks", schema_version=SCHEMA_VERSION,
            idempotency_key=packet.id, trace_id=packet.id,
            recipient='wealthmachine', operation='opportunity.evaluate',
        ))
        request = urllib.request.Request(
            f"{self.url}/api/opportunities/intake",
            data=body, headers=headers, method="POST",
        )
        timeout = float(os.getenv("WEALTHMACHINE_TIMEOUT", "20"))
        state = self._durable_state()  # configuration/history admission before any dispatch
        try:
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
                raw = response.read()
                response_headers = dict(response.headers.items())
        except Exception:
            self._record_failure()
            raise
        try:
            transport = verify_headers(response_headers, raw,
                nonce_cache=state, expected_sender='wealthmachine',
                expected_recipient='daleobanks', expected_operation='opportunity.evaluate',
                request_digest=body_digest(body), direction='response', status='200')
            if transport['idempotency_key'] != packet.id or transport['schema_version'] != SCHEMA_VERSION:
                raise BridgeSecurityError('response logical key or version mismatch')
            payload = strict_json(raw)
            validate_assessment_wire(payload)
            if (payload['opportunity_packet_id'] != packet.id
                    or payload['schema_version'] != SCHEMA_VERSION):
                raise BridgeSecurityError('response refers to another packet/version')
        except (BridgeSecurityError, ValueError):
            self._record_failure()
            raise
        self._consecutive_failures = 0
        return VentureAssessment(
            id=payload['id'],
            created_at=datetime.fromisoformat(payload['created_at'].replace('Z', '+00:00')),
            opportunity_packet_id=payload["opportunity_packet_id"],
            go_no_go=payload["go_no_go"],
            opportunity_score=float(payload.get("opportunity_score") or 0.0),
            market_alignment=float(payload.get("market_alignment") or 0.0),
            expected_roi=str(payload.get("expected_roi") or ""),
            risk_level=str(payload.get("risk_level") or "medium"),
            legal_readiness=str(payload.get("legal_readiness") or "unreviewed"),
            product_hypothesis=str(payload.get("product_hypothesis") or ""),
            pricing_hypothesis=str(payload.get("pricing_hypothesis") or ""),
            validation_plan=list(payload.get("validation_plan") or []),
            monetization_paths=list(payload.get("monetization_paths") or []),
            recommended_next_action=str(payload.get("recommended_next_action") or ""),
            requires_human_approval=True,  # non-negotiable on this side
            reasons=list(payload.get("reasons") or []),
            cases=list(payload.get("cases") or []),
        )

    def _record_failure(self) -> None:
        import time as _time

        self._consecutive_failures += 1
        if self._consecutive_failures >= self.FAILURE_THRESHOLD:
            self._circuit_open_until = _time.time() + self.COOLDOWN_SECONDS
            logger.warning(
                f"WealthMachine bridge circuit opened for {self.COOLDOWN_SECONDS}s "
                f"after {self._consecutive_failures} consecutive failures"
            )
            self.ledger.record("bridge_circuit_opened", {
                "failures": self._consecutive_failures,
                "cooldown_seconds": self.COOLDOWN_SECONDS,
            })

    def _evaluate_mock(self, packet: OpportunityPacket) -> VentureAssessment:
        """Deterministic local scoring with the same shape as the real engine."""
        from services.adversarial_cases import build_cases, severe_unresolved

        score = 0.2
        score += 0.1 * min(len(packet.evidence), 3)
        score += {"high": 0.2, "medium": 0.1}.get(packet.urgency, 0.0)
        if packet.monetization_paths:
            score += 0.1
        if packet.possible_offer:
            score += 0.1
        score = round(min(score, 0.95), 3)

        legal_flags = _LEGAL_RISK_FLAGS & set(packet.risk_flags)
        finance = "finance_education_only" in packet.risk_flags

        # Same adversarial committee as the real engine (mirrored module).
        cases = build_cases(packet_to_wire(packet), score, round(min(0.9, score + 0.1), 3))
        severe = severe_unresolved(cases)

        reasons = []
        if legal_flags:
            go_no_go, risk_level = "kill", "high"
            reasons.append(f"legal risk flags present: {sorted(legal_flags)}")
        elif not packet.evidence:
            go_no_go, risk_level = "needs_more_evidence", "medium"
            reasons.append("no evidence attached to the packet")
        elif score < 0.55:
            go_no_go, risk_level = "defer", "medium"
            reasons.append(f"opportunity score {score} below threshold")
        else:
            go_no_go = "go"
            risk_level = "medium" if finance else "low"
            reasons.append(f"score {score} with offer and monetization paths")
        if severe and go_no_go == "go":
            # A high score may not erase a severe unresolved risk.
            go_no_go = "needs_more_evidence"
            reasons.append(f"severe unresolved adversarial case(s) cap the verdict: {severe}")
        for case in cases:
            if case["stance"] == "against" and case["severity"] != "low":
                reasons.append(f"[{case['case']}] {case['argument']}")
        if finance:
            reasons.append("finance content must remain educational; no personalized advice")

        validation_plan = [step for step in [
            packet.smallest_validation_action,
            "Draft landing-page copy and collect waitlist interest (no payment yet)",
            "Run 3-5 buyer interviews from engaged repliers",
        ] if step]

        return VentureAssessment(
            opportunity_packet_id=packet.id,
            go_no_go=go_no_go,
            opportunity_score=score,
            market_alignment=round(min(0.9, score + 0.1), 3),
            expected_roi="unknown until validation; no revenue promises",
            risk_level=risk_level,
            legal_readiness="review_required" if (legal_flags or finance) else "standard",
            product_hypothesis=packet.possible_offer or "unspecified",
            pricing_hypothesis="$15-29 one-time or $9/mo; test willingness before building",
            validation_plan=validation_plan,
            monetization_paths=packet.monetization_paths,
            recommended_next_action=validation_plan[0] if validation_plan else "gather evidence",
            requires_human_approval=True,
            reasons=reasons,
            cases=cases,
        )

    # ------------------------------------------------------------------ #
    # Assessment -> reviewable actions (drafts + approval, never execution)
    # ------------------------------------------------------------------ #
    def assessment_to_actions(
        self,
        session: Any,
        assessment: VentureAssessment,
        packet: OpportunityPacket,
        operator_line: Any,
    ) -> Dict[str, Any]:
        finance = "finance_education_only" in packet.risk_flags
        disclosure = "\n\nEducational only — not financial advice." if finance else ""

        landing = MediaAssetDraft(
            source_opportunity_packet_id=packet.id,
            source_thought=packet.core_thesis,
            account_lane="main",
            platform="web",
            format="landing_page",
            title=f"{packet.possible_offer or 'Offer'} — waitlist",
            draft_text=(
                f"# {packet.core_thesis}\n\n"
                f"We're building {packet.possible_offer or 'a resource'} for "
                f"{packet.audience}.\n\nWhat you'll learn: the mechanisms, the "
                "numbers to track, and the questions to ask — in plain language."
                f"\n\nJoin the waitlist to shape what we build.{disclosure}"
            ),
            cta="Join the waitlist",
            disclosure_needed=finance,
            risk_level=assessment.risk_level,
        )
        interview = MediaAssetDraft(
            source_opportunity_packet_id=packet.id,
            source_thought=packet.core_thesis,
            format="interview_script",
            title=f"Buyer interviews: {packet.possible_offer or packet.core_thesis[:40]}",
            script="\n".join([
                "1. Walk me through the last time you felt this pain. What did you do?",
                "2. What have you already tried? What did it cost you?",
                "3. If this problem vanished tomorrow, what changes for you?",
                "4. What would make a resource on this obviously worth paying for?",
                "5. Who else do you know wrestling with this? (referral, not pitch)",
            ]),
            risk_level="low",
        )
        outreach = MediaAssetDraft(
            source_opportunity_packet_id=packet.id,
            source_thought=packet.core_thesis,
            format="outreach_dm",
            title="Interview invitation (engaged repliers only)",
            draft_text=(
                "Thanks for the thoughtful reply on this topic. I'm researching "
                "the problem seriously — would you be open to a 15-minute chat "
                "about your experience? No pitch, just learning."
            ),
            risk_level="medium",  # outreach always needs a human yes
        )
        for draft in (landing, interview, outreach):
            session.add(draft)

        approval = operator_line.request_approval(
            session,
            kind="validation_plan",
            summary=(
                f"Run validation for '{(packet.possible_offer or packet.core_thesis)[:60]}' "
                f"({assessment.go_no_go}, score {assessment.opportunity_score})"
            ),
            payload={
                "opportunity_packet_id": packet.id,
                "venture_assessment_id": assessment.id,
                "validation_plan": assessment.validation_plan,
                "draft_ids": [landing.id, interview.id, outreach.id],
            },
            rationale="; ".join(assessment.reasons)[:300],
        )
        session.commit()
        return {
            "landing_page": landing,
            "interview_script": interview,
            "outreach_draft": outreach,
            "approval_request": approval,
        }


_SHARED_CLIENT: Optional[WealthMachineClient] = None


def get_wealthmachine_client() -> WealthMachineClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = WealthMachineClient()
    return _SHARED_CLIENT


def set_wealthmachine_client(client: Optional[WealthMachineClient]) -> None:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None and _SHARED_CLIENT is not client:
        _SHARED_CLIENT.close()
    _SHARED_CLIENT = client


__all__ = ["WealthMachineClient", "get_wealthmachine_client", "set_wealthmachine_client"]
