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
from typing import Any, Dict, Optional

from db.models import ApprovalRequest, MediaAssetDraft, OpportunityPacket, VentureAssessment
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger
from services.venture_protocol import packet_to_wire, validate_assessment_wire

logger = get_logger(__name__)

_LEGAL_RISK_FLAGS = {"legal_risk", "regulated_product", "licensing_required"}


class WealthMachineClient:
    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

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
        request = urllib.request.Request(
            f"{self.url}/api/opportunities/intake",
            data=json.dumps(packet_to_wire(packet)).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = float(os.getenv("WEALTHMACHINE_TIMEOUT", "20"))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        validate_assessment_wire(payload)
        return VentureAssessment(
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
        )

    def _evaluate_mock(self, packet: OpportunityPacket) -> VentureAssessment:
        """Deterministic local scoring with the same shape as the real engine."""
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
    _SHARED_CLIENT = client


__all__ = ["WealthMachineClient", "get_wealthmachine_client", "set_wealthmachine_client"]
