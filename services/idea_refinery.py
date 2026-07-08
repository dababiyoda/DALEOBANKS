"""The idea refinery: raw operator thoughts become structured, reviewable
assets — theses, audience options, localized media drafts, and opportunity
packets. Nothing here publishes, sells, DMs, or launches anything; every
output is a draft waiting for human decision, and anything with real-world
consequences routes through the approval queue.

Offline-first: the refinery produces deterministic template drafts with no
LLM available; when the LLM adapter is configured it may polish wording,
but the guardrails run on the final text either way.

Finance guardrail (hardcoded): money-related content stays educational.
Personalized advice phrasing is stripped/blocked and an educational
disclosure is attached. No income promises, ever.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from db.models import Idea, MediaAssetDraft, OpportunityPacket
from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger
from services.prompt_firewall import get_firewall

logger = get_logger(__name__)

EDUCATIONAL_DISCLOSURE = "Educational only — not financial advice."

_FINANCE_KEYWORDS = (
    "financial", "finance", "money", "invest", "investing", "retire",
    "retirement", "fire", "budget", "budgeting", "savings", "income",
    "wealth", "debt",
)

# Personalized-advice and income-promise phrasing that must never survive
# into a draft. This list is a floor, not a ceiling.
_ADVICE_VIOLATIONS = (
    "you should invest", "you should buy", "you should sell",
    "guaranteed return", "guaranteed returns", "guaranteed income",
    "guaranteed profit", "can't lose", "cannot lose", "risk-free return",
    "double your money", "get rich quick",
)

_OFFER_HINTS = ("checklist", "workshop", "newsletter", "community", "course",
                "template", "guide")


def check_educational(text: str) -> List[str]:
    """Return the personalized-advice / income-promise violations in a text."""
    lower = (text or "").lower()
    return [phrase for phrase in _ADVICE_VIOLATIONS if phrase in lower]


def _is_finance_related(text: str) -> bool:
    lower = (text or "").lower()
    return any(word in lower for word in _FINANCE_KEYWORDS)


def _first_sentence(text: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        if sentence.strip():
            return sentence.strip()
    return (text or "").strip()


class IdeaRefinery:
    """Turns one raw thought into reviewable assets. Drafts only."""

    def __init__(self, llm_adapter: Any = None, ledger: Optional[DecisionLedger] = None):
        self.llm_adapter = llm_adapter
        self._ledger = ledger
        self.firewall = get_firewall()

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    # ------------------------------------------------------------------ #
    # Intake
    # ------------------------------------------------------------------ #
    def intake(self, session: Any, raw_text: str) -> Idea:
        scan = self.firewall.scan(raw_text or "")
        sanitized = self.firewall.sanitize(raw_text or "").strip()
        risk_flags = []
        if scan["risk"] >= 0.4:
            # Even operator-channel text gets hygiene: instruction-shaped
            # content is flagged so it never silently steers downstream.
            risk_flags.append("injection_suspect")
        idea = Idea(raw_text=sanitized, risk_flags=risk_flags)
        session.add(idea)
        session.commit()
        self.ledger.record("idea_intake", {
            "id": idea.id, "chars": len(sanitized), "risk_flags": risk_flags,
        })
        return idea

    # ------------------------------------------------------------------ #
    # Refinement
    # ------------------------------------------------------------------ #
    async def refine(self, session: Any, idea: Idea) -> Dict[str, Any]:
        thesis = _first_sentence(idea.raw_text)
        audiences = self._recommend_audiences(idea.raw_text)
        drafts = [self._draft_for(audience, thesis, idea) for audience in audiences]
        drafts.append(self._video_script(thesis, idea))

        for draft in drafts:
            session.add(draft)

        packet = self._opportunity_from(idea, thesis)
        if packet is not None:
            session.add(packet)

        idea.thesis = thesis
        idea.audiences = audiences
        idea.status = "refined"
        session.commit()

        self.ledger.record("idea_refined", {
            "id": idea.id,
            "drafts": len(drafts),
            "opportunity": packet.id if packet else None,
        })
        return {
            "idea": idea,
            "thesis": thesis,
            "audiences": audiences,
            "drafts": drafts,
            "opportunity": packet,
        }

    def _recommend_audiences(self, text: str) -> List[Dict[str, Any]]:
        audiences: List[Dict[str, Any]] = [{
            "name": "Systems-critique general audience",
            "lane": "main",
            "platform": "x",
            "language": "en",
            "cultural_context": "US general",
        }]
        if _is_finance_related(text):
            audiences.append({
                "name": "Ghanaian immigrant FIRE education (USA)",
                "lane": "diaspora_fire",
                "platform": "x",
                "language": "en",
                "cultural_context": "Ghanaian immigrants in the USA",
            })
            audiences.append({
                "name": "Spanish-language financial independence",
                "lane": "fi_es",
                "platform": "x",
                "language": "es",
                "cultural_context": "Spanish-speaking US/LatAm audience",
            })
        else:
            audiences.append({
                "name": "Practitioners close to the problem",
                "lane": "main",
                "platform": "x",
                "language": "en",
                "cultural_context": "domain practitioners",
            })
        return audiences

    def _draft_for(self, audience: Dict[str, Any], thesis: str, idea: Idea) -> MediaAssetDraft:
        finance = _is_finance_related(idea.raw_text)
        context = audience.get("cultural_context", "")
        language = audience.get("language", "en")

        if language == "es":
            body = (
                f"{thesis}\n\nLa independencia financiera no es egoísmo: es protección "
                "frente a sistemas que ganan cuando tú dependes. Empieza por entender "
                "a dónde va tu dinero cada mes — el conocimiento es el primer activo."
            )
            hook = "La libertad financiera es defensa, no lujo."
            cta = "Comparte: ¿qué te enseñaron sobre el dinero?"
        elif "Ghanaian" in context:
            body = (
                f"{thesis}\n\nFor Ghanaian families building in the USA: financial "
                "independence is how you protect the people counting on you — here and "
                "back home. The educational basics compound: track the money you send "
                "and spend, know your savings rate, learn how employer accounts work "
                "before choosing among them."
            )
            hook = "Building here without losing what you're building for."
            cta = "What money lesson do you wish you'd learned earlier?"
        else:
            body = (
                f"{thesis}\n\nThe systems question: who profits when you stay dependent? "
                "Mechanism: dependency is a revenue model — subscriptions, interest, and "
                "lock-in are designed. The counter-mechanism is boring competence: know "
                "your numbers, cut the leaks, own your exits."
            )
            hook = "Dependency is a business model. Independence is the counter-move."
            cta = "Which system in your life profits from your dependency?"

        disclosure = finance
        if disclosure:
            body = f"{body}\n\n{EDUCATIONAL_DISCLOSURE}"

        violations = check_educational(body)
        if violations:
            # Templates are ours, so this should be unreachable — but the
            # guard is load-bearing, not decorative.
            raise ValueError(f"draft violates finance education guardrail: {violations}")

        return MediaAssetDraft(
            source_thought=idea.raw_text[:280],
            account_lane=audience.get("lane", "main"),
            platform=audience.get("platform", "x"),
            language=language,
            cultural_context=context,
            format="post",
            title=thesis[:80],
            draft_text=body,
            hook=hook,
            cta=cta,
            disclosure_needed=disclosure,
            risk_level="medium" if finance else "low",
        )

    def _video_script(self, thesis: str, idea: Idea) -> MediaAssetDraft:
        finance = _is_finance_related(idea.raw_text)
        script = "\n".join([
            f"HOOK (0-3s): {thesis}",
            "BEAT 1 (3-15s): Name the system — who profits from the status quo?",
            "BEAT 2 (15-35s): One concrete, educational mechanism the viewer can verify.",
            "BEAT 3 (35-50s): What changes when you understand it (no promises, just agency).",
            "CTA (50-60s): Ask the audience what they were taught — invite replies.",
        ] + ([EDUCATIONAL_DISCLOSURE] if finance else []))
        return MediaAssetDraft(
            source_thought=idea.raw_text[:280],
            account_lane="main",
            platform="short_video",
            language="en",
            format="video_script",
            title=f"Short: {thesis[:60]}",
            script=script,
            disclosure_needed=finance,
            risk_level="medium" if finance else "low",
        )

    def _opportunity_from(self, idea: Idea, thesis: str) -> Optional[OpportunityPacket]:
        lower = idea.raw_text.lower()
        finance = _is_finance_related(idea.raw_text)
        offers = [hint for hint in _OFFER_HINTS if hint in lower]
        if not offers and finance:
            offers = ["checklist", "workshop", "newsletter"]
        if not offers:
            return None

        risk_flags = list(idea.risk_flags)
        if finance:
            risk_flags.append("finance_education_only")

        return OpportunityPacket(
            source="daleobanks",
            source_ref=idea.id,
            signal_type="operator_thought",
            observed_pain="People feel trapped by systems that profit from their dependency",
            core_thesis=thesis,
            audience="US-based savers early in their financial independence journey",
            cultural_context="US general + diaspora niches",
            language="en",
            customer_segment="individual learners",
            buyer_type="consumer",
            urgency="medium",
            evidence=[f"operator thought {idea.id}"],
            possible_offer=f"educational {offers[0]}",
            monetization_paths=[f"paid {offer}" for offer in offers[:3]],
            risk_flags=risk_flags,
            smallest_validation_action=(
                "Post one educational thread on the thesis and offer a free "
                f"{offers[0]} waitlist; measure saves, replies, and signups"
            ),
            confidence=0.55,
        )


__all__ = ["IdeaRefinery", "check_educational", "EDUCATIONAL_DISCLOSURE"]
