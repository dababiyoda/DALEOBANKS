"""Debate judged by what it produced, and the research it is supposed to feed.

A debate that generated only outrage is a weak outcome. That sentence is
easy to agree with and hard to enforce, because outrage is the thing that
looks like success in every dashboard a media company has. So productivity
here is defined by artifacts a debate leaves behind — a sharper question, a
falsified assumption, an expert who surfaced, a research lead, a prototype, a
standard proposal, a collaboration — and a debate that produced none of them
closes as unproductive with that recorded.

The second half is the civilization-seeding loop: make a missing primitive
legible, make solving it prestigious, attract people who can, support the
experiment, and absorb what works. Its failure mode is treating a lively
public thread as though a question had been settled. Public discussion is not
scientific closure, so a research lead carries its verification state
explicitly and starts unverified.

Nothing here publishes or contacts anyone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from db.models import DebateRecord, ResearchLead, SharedPrimitive
from services.aspiration_registry import DISPOSITIONS
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

# What a debate must leave behind to have been worth having.
PRODUCTIVE_OUTCOMES = (
    "better_question",
    "falsified_assumption",
    "expert_identified",
    "research_lead",
    "experiment",
    "prototype",
    "standard_proposal",
    "collaboration",
    "funding_target",
    "venture_hypothesis",
)

# Attention is not an outcome. Recorded so it can be counted and discounted.
UNPRODUCTIVE_OUTCOMES = ("engagement_only", "outrage_only", "no_response")

EVIDENCE_CLASSES = (
    "FACT", "SUPPORTED_INFERENCE", "PROPOSAL",
    "EXPERIMENT", "ASPIRATION", "SPECULATION",
)

# Frontier topics that read as proven because the future is desirable.
SPECULATIVE_DOMAINS = (
    "longevity", "advanced ai", "agi", "robotics", "new computing",
    "quantum", "bioengineering", "space technology", "morphogenetic",
    "nanotech", "fusion", "brain-computer",
)

LEAD_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "FALSIFIED", "ABANDONED")


class DebateEngineError(ValueError):
    """A debate or research lead violated an evidence or framing invariant."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def touches_speculative_domain(text: str) -> List[str]:
    lower = (text or "").lower()
    return [domain for domain in SPECULATIVE_DOMAINS if domain in lower]


class DebateEngine:
    """Open debates that can fail honestly, and route what they produce."""

    def __init__(self, ledger: Optional[DecisionLedger] = None) -> None:
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def open_debate(
        self,
        session: Any,
        *,
        question: str,
        daleobanks_position: str,
        strongest_counterargument: str,
        evidence_class: str,
        content_ids: Optional[Sequence[str]] = None,
    ) -> DebateRecord:
        """Open a debate carrying the case against its own position.

        A frontier topic may not open above PROPOSAL. Wanting a future badly
        is not evidence that it arrived, and the classes exist so ambition and
        fact stay separable in the record.
        """
        if not (question or "").strip():
            raise DebateEngineError("a debate requires a question")
        if evidence_class not in EVIDENCE_CLASSES:
            raise DebateEngineError(f"evidence_class must be one of {list(EVIDENCE_CLASSES)}")
        if not (strongest_counterargument or "").strip():
            raise DebateEngineError(
                "a debate requires the strongest case against its own position; "
                "opening without one is agenda-setting, not debate"
            )
        speculative = touches_speculative_domain(f"{question} {daleobanks_position}")
        if speculative and evidence_class in ("FACT", "SUPPORTED_INFERENCE"):
            raise DebateEngineError(
                f"topic touches {speculative} and is claimed as {evidence_class}; "
                f"frontier work is labeled PROPOSAL or weaker until evidence "
                f"says otherwise, however desirable the future is"
            )

        record = DebateRecord(
            question=question.strip(),
            daleobanks_position=daleobanks_position.strip(),
            strongest_counterargument=strongest_counterargument.strip(),
            evidence_class=evidence_class,
            content_ids=list(content_ids or []),
        )
        session.add(record)
        session.commit()
        self.ledger.record("debate_opened", {
            "debate_id": record.id, "evidence_class": evidence_class,
            "speculative_domains": speculative, "counterargument_present": True,
        })
        return record

    def close_debate(
        self,
        session: Any,
        *,
        debate_id: str,
        outcomes: Sequence[str],
        outcome_refs: Optional[Dict[str, Any]] = None,
    ) -> DebateRecord:
        """Close a debate on what it produced. Attention alone is a failure."""
        record = self._debate(session, debate_id)
        if record.closed_at:
            raise DebateEngineError("debate is already closed")
        listed = [str(o).strip() for o in outcomes if str(o).strip()]
        unknown = [o for o in listed
                   if o not in PRODUCTIVE_OUTCOMES and o not in UNPRODUCTIVE_OUTCOMES]
        if unknown:
            raise DebateEngineError(
                f"unrecognized outcomes {unknown}; allowed: "
                f"{list(PRODUCTIVE_OUTCOMES + UNPRODUCTIVE_OUTCOMES)}"
            )
        if not listed:
            raise DebateEngineError(
                "closing a debate requires stating what it produced, even when "
                "the honest answer is nothing"
            )
        record.outcomes = listed
        record.outcome_refs = dict(outcome_refs or {})
        record.productive = any(o in PRODUCTIVE_OUTCOMES for o in listed)
        record.closed_at = _now().isoformat()
        session.commit()
        self.ledger.record("debate_closed", {
            "debate_id": record.id, "outcomes": listed,
            "productive": record.productive,
        })
        return record

    def open_research_lead(
        self,
        session: Any,
        *,
        question: str,
        debate_id: str = "",
        primitive_id: str = "",
        experts_identified: Optional[Sequence[str]] = None,
        hypothesis: str = "",
        disposition: str = "UNDECIDED",
    ) -> ResearchLead:
        """Turn an unresolved question into something someone could answer."""
        if not (question or "").strip():
            raise DebateEngineError("a research lead requires a question")
        if disposition not in DISPOSITIONS:
            raise DebateEngineError(f"disposition must be one of {sorted(DISPOSITIONS)}")
        if debate_id:
            self._debate(session, debate_id)
        if primitive_id:
            primitive = session.query(SharedPrimitive).filter(
                lambda row: row.id == primitive_id
            ).first()
            if primitive is None:
                raise DebateEngineError("shared primitive is not registered")

        lead = ResearchLead(
            debate_id=debate_id, question=question.strip(), primitive_id=primitive_id,
            experts_identified=list(experts_identified or []),
            hypothesis=hypothesis.strip(), disposition=disposition,
        )
        session.add(lead)
        session.commit()
        self.ledger.record("research_lead_opened", {
            "lead_id": lead.id, "debate_id": debate_id,
            "primitive_id": primitive_id, "disposition": disposition,
            "independently_verified": False,
        })
        return lead

    def resolve_research_lead(
        self,
        session: Any,
        *,
        lead_id: str,
        status: str,
        result: str,
        verification_ref: str = "",
    ) -> ResearchLead:
        """Record a result. RESOLVED requires independent verification.

        FALSIFIED does not: learning that a hypothesis is wrong is a real
        result and demanding verification for it would suppress the cheapest
        useful outcome a research programme produces.
        """
        if status not in LEAD_STATUSES:
            raise DebateEngineError(f"status must be one of {list(LEAD_STATUSES)}")
        lead = session.query(ResearchLead).filter(
            lambda row: row.id == lead_id
        ).first()
        if lead is None:
            raise DebateEngineError("research lead is not registered")
        if not (result or "").strip():
            raise DebateEngineError("a result statement is required")
        if status == "RESOLVED" and not (verification_ref or "").strip():
            raise DebateEngineError(
                "a lead is RESOLVED only on independent verification; a lively "
                "public thread is not scientific closure"
            )
        lead.status = status
        lead.result = result.strip()
        lead.verification_ref = verification_ref.strip()
        lead.independently_verified = bool(
            status == "RESOLVED" and verification_ref.strip()
        )
        session.commit()
        self.ledger.record("research_lead_resolved", {
            "lead_id": lead.id, "status": status,
            "independently_verified": lead.independently_verified,
        })
        return lead

    def absorb_external_capability(
        self, session: Any, *, lead_id: str, capability_ref: str
    ) -> ResearchLead:
        """Record a capability that arrived from outside and now exists.

        The point of seeding is that someone else solves it. Absorbing an
        external solution is the loop working, not the loop losing.
        """
        lead = session.query(ResearchLead).filter(
            lambda row: row.id == lead_id
        ).first()
        if lead is None:
            raise DebateEngineError("research lead is not registered")
        if not lead.independently_verified:
            raise DebateEngineError(
                "only an independently verified result may be absorbed as a "
                "capability"
            )
        if not (capability_ref or "").strip():
            raise DebateEngineError("a capability reference is required")
        lead.absorbed_capability_ref = capability_ref.strip()
        session.commit()
        self.ledger.record("external_capability_absorbed", {
            "lead_id": lead.id, "capability_ref": lead.absorbed_capability_ref,
            "primitive_id": lead.primitive_id,
        })
        return lead

    def seeding_scorecard(self, session: Any) -> Dict[str, Any]:
        """Did the debate portfolio produce anything, or only attention?"""
        debates = session.query(DebateRecord).all()
        closed = [d for d in debates if d.closed_at]
        leads = session.query(ResearchLead).all()
        return {
            "debates_open": len(debates) - len(closed),
            "debates_closed": len(closed),
            "productive_debates": sum(1 for d in closed if d.productive),
            "unproductive_debates": sum(1 for d in closed if not d.productive),
            "research_leads": len(leads),
            "leads_verified": sum(1 for l in leads if l.independently_verified),
            "leads_falsified": sum(1 for l in leads if l.status == "FALSIFIED"),
            "external_capabilities_absorbed": sum(
                1 for l in leads if l.absorbed_capability_ref
            ),
        }

    @staticmethod
    def _debate(session: Any, debate_id: str) -> DebateRecord:
        record = session.query(DebateRecord).filter(
            lambda row: row.id == debate_id
        ).first()
        if record is None:
            raise DebateEngineError("debate is not registered")
        return record


__all__ = [
    "PRODUCTIVE_OUTCOMES", "UNPRODUCTIVE_OUTCOMES", "EVIDENCE_CLASSES",
    "SPECULATIVE_DOMAINS", "LEAD_STATUSES",
    "DebateEngineError", "DebateEngine", "touches_speculative_domain",
]
