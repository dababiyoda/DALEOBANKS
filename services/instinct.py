"""Instinct Engine and Identity Gate: the agent's hard reflex layer.

The Instinct Engine runs *before generation* on an opportunity (a mention, a
proposal slot, a DM, a sensed article) and answers "should I even engage, and
how?". The Identity Gate runs *after generation* on the draft and answers
"is this me, and is it safe to say?". Both are deterministic heuristics
(persona- and constitution-derived) so they work offline and are cheap enough
to run on every action; every verdict is ledgered.

Neither layer publishes anything — they only narrow what the existing
publish gates are allowed to see. The model may recommend; application code
authorizes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from services.ledger import DecisionLedger, get_ledger
from services.logging_utils import get_logger

logger = get_logger(__name__)

# Instinct verdicts, roughly ordered from "act" to "don't".
ENGAGE = "engage"
CREATE_ASSET = "create_asset"
RESEARCH_FIRST = "research_first"
DM_INSTEAD = "dm_instead"
SAVE_FOR_LATER = "save_for_later"
HUMAN_REVIEW = "human_review"
IGNORE = "ignore"
BLOCK = "block"

# Identity gate outcomes.
ALLOW = "allow"
REWRITE = "rewrite"
NEEDS_HUMAN = "needs_human"
# BLOCK is shared.

# Verdicts that let a proposal/reply flow continue toward generation.
PROCEED_VERDICTS = {ENGAGE, CREATE_ASSET, RESEARCH_FIRST}

_DEFAULT_MISSION_KEYWORDS: Set[str] = {
    "system", "systems", "systemic", "incentive", "incentives", "pilot",
    "pilots", "evidence", "coordination", "science", "technology", "policy",
    "progress", "reform", "mechanism", "institution", "institutions",
    "infrastructure", "climate", "energy", "governance", "critical",
    "thinking",
}

_RAGEBAIT_MARKERS = [
    "rt if", "like if", "retweet if", "you won't believe", "destroyed",
    "obliterated", "wake up sheeple", "ratio", "triggered", "owned",
]

_INSULT_MARKERS = [
    "idiot", "stupid", "moron", "loser", "clown", "pathetic", "dumb",
    "imbecile", "fool",
]

_DECEPTION_MARKERS = [
    "i am a human", "i'm a human", "pretend to be", "as a real person",
    "hide that i", "don't reveal",
]

_STRONG_CLAIM_MARKERS = [
    "always", "never", "guaranteed", "100%", "everyone knows", "obviously",
    "proven fact", "no doubt", "undeniable",
]

_SOURCE_MARKERS = ["http://", "https://", "source:", "per the", "according to"]

_ASSET_MARKERS = [
    "how do i", "how to", "guide", "template", "checklist", "tutorial",
    "walk me through", "step by step",
]

_LEVERAGE_MARKERS = [
    "pilot", "partner", "collaborate", "hire", "budget", "fund", "invest",
    "procurement", "rfp", "deal", "contract",
]


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 15:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _marker_score(text: str, markers: List[str], per_hit: float = 0.3) -> float:
    return min(1.0, sum(per_hit for marker in markers if marker in text))


def _overlap(text: str, keywords: Set[str]) -> float:
    words = {w.strip(".,!?;:()\"'") for w in text.split() if w.strip()}
    if not words:
        return 0.0
    hits = len(words & keywords)
    # Short inputs (a bare topic) are judged against their own length so a
    # single on-mission word scores as a full match.
    return min(1.0, hits / min(3, len(words)))


class _PersonaMixin:
    def __init__(self, persona_store: Any = None, ledger: Optional[DecisionLedger] = None):
        self.persona_store = persona_store
        self._ledger = ledger

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    def _mission_keywords(self) -> Set[str]:
        keywords = set(_DEFAULT_MISSION_KEYWORDS)
        if self.persona_store is None:
            return keywords
        try:
            persona = self.persona_store.get_current_persona()
            for source in (
                persona.get("mission", ""),
                " ".join(persona.get("engagement_focus", [])),
                " ".join(persona.get("doctrine", [])),
            ):
                for word in str(source).lower().split():
                    word = word.strip(".,!?;:()\"'")
                    if len(word) > 3:
                        keywords.add(word)
        except Exception:
            pass
        return keywords


class InstinctEngine(_PersonaMixin):
    """Pre-generation reflex: is this opportunity worth this identity's time?"""

    def assess(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        kind = opportunity.get("kind", "unknown")
        topic = str(opportunity.get("topic") or "")
        text = str(opportunity.get("text") or "")
        combined = f"{topic} {text}".lower()
        relationship = opportunity.get("relationship") or {}

        ragebait_risk = _marker_score(combined, _RAGEBAIT_MARKERS)
        if _caps_ratio(text) > 0.5:
            ragebait_risk = min(1.0, ragebait_risk + 0.4)
        insulting = any(marker in combined for marker in _INSULT_MARKERS)

        credibility_risk = _marker_score(combined, _STRONG_CLAIM_MARKERS, per_hit=0.25)
        has_source = any(marker in combined for marker in _SOURCE_MARKERS)
        has_figures = any(c.isdigit() for c in combined)
        if has_figures and not has_source:
            credibility_risk = min(1.0, credibility_risk + 0.3)

        evidence_need = 0.0
        if has_figures:
            evidence_need += 0.3
        if any(w in combined for w in ("study", "studies", "data", "research", "report")):
            evidence_need += 0.3
        if has_source:
            evidence_need -= 0.4
        evidence_need = max(0.0, min(1.0, evidence_need))

        keywords = self._mission_keywords()
        mission_fit = _overlap(combined, keywords)
        # The selector's default slot ("general") means "persona's choice" —
        # neutral fit, not off-mission.
        if kind == "proposal" and not text and topic.strip().lower() in ("", "general"):
            mission_fit = max(mission_fit, 0.5)
        identity_fit = mission_fit  # one persona, one lens; kept as separate
        # signals so future scoring can diverge them.

        interactions = relationship.get("interactions", 0) or 0
        sentiment = relationship.get("sentiment", 0.0) or 0.0
        relationship_value = min(1.0, interactions * 0.15 + max(0.0, sentiment) * 0.3)

        business_leverage = _marker_score(combined, _LEVERAGE_MARKERS)

        scores = {
            "identity_fit": round(identity_fit, 3),
            "mission_fit": round(mission_fit, 3),
            "business_leverage": round(business_leverage, 3),
            "relationship_value": round(relationship_value, 3),
            "credibility_risk": round(credibility_risk, 3),
            "ragebait_risk": round(ragebait_risk, 3),
            "evidence_need": round(evidence_need, 3),
        }

        verdict, reason = self._verdict(
            kind, scores, insulting=insulting, sentiment=sentiment,
            combined=combined, stakes=opportunity.get("stakes"),
        )

        result = {"verdict": verdict, "reason": reason, "scores": scores, "kind": kind}
        try:
            self.ledger.record("instinct_verdict", {
                "kind": kind, "topic": topic[:60], "verdict": verdict,
                "reason": reason, **scores,
            })
        except Exception as exc:
            logger.error(f"Failed to ledger instinct verdict: {exc}")
        return result

    def _verdict(self, kind, scores, *, insulting, sentiment, combined, stakes):
        if scores["ragebait_risk"] >= 0.6:
            return BLOCK, "reads as ragebait; engaging feeds it"
        if insulting:
            return BLOCK, "engaging with insults degrades the identity"
        if kind == "mention" and sentiment <= -0.4:
            return DM_INSTEAD, "hostile history; de-escalate privately, not publicly"
        if stakes == "high":
            return HUMAN_REVIEW, "high stakes flagged; a human should look first"
        if scores["evidence_need"] >= 0.6 and scores["credibility_risk"] >= 0.5:
            return RESEARCH_FIRST, "factual claims need verification before engaging"
        if any(marker in combined for marker in _ASSET_MARKERS):
            return CREATE_ASSET, "a reusable asset serves this better than a one-off reply"
        fit = max(scores["identity_fit"], scores["mission_fit"])
        if fit < 0.2 and scores["relationship_value"] < 0.3:
            return IGNORE, "off-mission and no relationship at stake"
        # Mentions go stale and self-chosen proposal slots were already
        # persona-picked, so "bank it" only applies to sensed material.
        if (
            kind not in ("mention", "proposal")
            and fit < 0.45
            and scores["business_leverage"] < 0.6
        ):
            return SAVE_FOR_LATER, "marginal fit; bank it rather than force it"
        return ENGAGE, "on-mission and worth the identity's time"


class IdentityGate(_PersonaMixin):
    """Post-generation gate: is this draft consistent with who the agent is?"""

    def review(self, draft: str, kind: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        lower = draft.lower()

        drift_risk = 0.0
        if any(marker in lower for marker in _INSULT_MARKERS):
            drift_risk += 0.8
        if any(marker in lower for marker in _DECEPTION_MARKERS):
            drift_risk += 0.8
        drift_risk = min(1.0, drift_risk + _marker_score(lower, _RAGEBAIT_MARKERS, per_hit=0.2))

        voice_fit = 1.0
        if _caps_ratio(draft) > 0.3:
            voice_fit -= 0.4
        if draft.count("!") > 2:
            voice_fit -= 0.2
        if draft.count("#") > 3:
            voice_fit -= 0.2
        voice_fit = max(0.0, voice_fit)

        keywords = self._mission_keywords()
        overlap = _overlap(lower, keywords)
        # Replies legitimately carry less mission vocabulary than proposals.
        mission_fit = 0.5 + overlap * 0.5 if kind == "reply" else overlap
        belief_fit = mission_fit

        credibility_risk = _marker_score(lower, _STRONG_CLAIM_MARKERS, per_hit=0.25)
        has_source = any(marker in lower for marker in _SOURCE_MARKERS)
        if any(c.isdigit() for c in lower) and not has_source:
            credibility_risk = min(1.0, credibility_risk + 0.3)

        business_leverage = _marker_score(lower, _LEVERAGE_MARKERS)

        scores = {
            "belief_fit": round(belief_fit, 3),
            "voice_fit": round(voice_fit, 3),
            "mission_fit": round(mission_fit, 3),
            "business_leverage": round(business_leverage, 3),
            "credibility_risk": round(credibility_risk, 3),
            "drift_risk": round(drift_risk, 3),
        }

        if drift_risk >= 0.6:
            outcome, reason = BLOCK, "draft drifts from the constitution (insults/deception/ragebait)"
        elif credibility_risk >= 0.7:
            outcome, reason = NEEDS_HUMAN, "strong unsourced claims; a human should approve"
        elif voice_fit < 0.5 or (kind != "reply" and mission_fit < 0.2):
            outcome, reason = REWRITE, "doesn't sound like us or serve the mission"
        else:
            outcome, reason = ALLOW, "consistent with identity and mission"

        result = {"outcome": outcome, "reason": reason, "scores": scores, "kind": kind}
        try:
            self.ledger.record("identity_gate", {
                "kind": kind, "outcome": outcome, "reason": reason, **scores,
            })
        except Exception as exc:
            logger.error(f"Failed to ledger identity gate: {exc}")
        return result


_SHARED_ENGINE: Optional[InstinctEngine] = None
_SHARED_GATE: Optional[IdentityGate] = None


def get_instinct_engine() -> InstinctEngine:
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        _SHARED_ENGINE = InstinctEngine()
    return _SHARED_ENGINE


def get_identity_gate() -> IdentityGate:
    global _SHARED_GATE
    if _SHARED_GATE is None:
        _SHARED_GATE = IdentityGate()
    return _SHARED_GATE


def set_instinct_instances(
    engine: Optional[InstinctEngine] = None, gate: Optional[IdentityGate] = None
) -> None:
    global _SHARED_ENGINE, _SHARED_GATE
    _SHARED_ENGINE = engine
    _SHARED_GATE = gate
