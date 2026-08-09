"""Guards on the two ways this system could learn to be worse.

The optimizer runs Thompson sampling over a J-score built from impact,
revenue, authority, and fame, minus a penalty. Fame is an engagement proxy
plus follower growth. The penalty counts rate limits, mutes, blocks, and
ethics violations — all reactive platform signals.

Nothing in that loop measures whether anyone understood something or became
more capable. So content that raises engagement by making people angry, and
never trips a platform block, raises the J-score. The bandit then samples
that arm more often. The shortcut is not a hypothetical: it is what this
reward function currently rewards.

Two guards, because there are two distinct failures.

The content guard asks what a piece of writing is aimed at. DALEOBANKS is
supposed to be ruthless toward exploitation, fraud, corruption, and systems
that trap people — that register is the brand, and a guard that flattens it
would be worse than no guard. What it may not do is aim contempt at ordinary
people for being poor, confused, foreign, or inexperienced. Ruthless toward
the problem, humane toward the person: the guard reads the target, not the
temperature.

The learning guard asks what the optimizer is being taught. An arm whose
engagement climbs while its capability and trust signals fall is the
shortcut mid-formation. Refusing to reinforce it is the only place that
pattern can be caught, because by the time it shows up in the J-score it has
already been learned.

Neither guard publishes, blocks a platform call, or grants authority. They
refuse to let content through and refuse to let a reward be counted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from services.logging_utils import get_logger

logger = get_logger(__name__)


class IntegrityGuardError(ValueError):
    """Content or a reward signal violated an integrity invariant."""


class RageBaitError(IntegrityGuardError):
    """Content is shaped to produce anger without producing capability."""


class ContemptError(IntegrityGuardError):
    """Content aims contempt at people rather than at a system."""


class FakeEngagementError(IntegrityGuardError):
    """An engagement signal is implausible and must not enter learning."""


# --------------------------------------------------------------------- #
# What is being attacked
# --------------------------------------------------------------------- #

# Legitimate targets. Attacking these hard is the brand, not a violation.
_SYSTEM_TARGETS = (
    "scam", "scams", "fraud", "predatory", "exploitation", "exploit",
    "corruption", "corrupt", "kickback", "loophole", "cartel", "monopoly",
    "the industry", "the system", "these lenders", "the fee", "hidden fee",
    "junk fee", "the policy", "the loophole", "this practice", "the incentive",
    "bad incentives", "the bureaucracy", "institutional", "price gouging",
    "wage theft", "bait and switch", "dark pattern", "lock-in",
)

# Contempt aimed at people. The mandate names these groups specifically as
# ones the brand must never humiliate.
_PROTECTED_DESCRIPTORS = (
    "poor", "broke", "confused", "uneducated", "illiterate", "immigrant",
    "immigrants", "migrants", "foreigners", "traumatized", "desperate",
    "boomers", "zoomers", "peasants", "normies", "sheep", "sheeple",
    "losers", "lazy", "stupid", "idiots", "morons", "dumb", "clueless",
    "gullible", "suckers", "marks", "rubes", "npcs",
)

# Contempt verbs and framings applied to a person or group.
_CONTEMPT_MARKERS = (
    "deserve what they get", "deserve it", "brought it on themselves",
    "too stupid", "too dumb", "too lazy", "if you're this", "if you are this",
    "no sympathy for", "zero sympathy", "cry harder", "cope harder",
    "stay poor", "enjoy being poor", "you people", "these people are",
    "they're all", "typical of them", "natural selection",
)

# Outrage-shaped hooks. Not forbidden — but they must carry a payload.
_OUTRAGE_MARKERS = (
    "furious", "outrage", "outrageous", "disgusting", "disgrace",
    "should be illegal", "makes me sick", "infuriating", "rage",
    "wake up", "they don't want you to know", "nobody is talking about",
    "this is criminal", "scandal", "betrayal", "sickening",
)

# Evidence that the reader can do something afterwards. This is the payload
# that separates a regenerative rabbit hole from an outrage machine.
_CAPABILITY_MARKERS = (
    "here's how", "here is how", "what you can do", "step ", "steps",
    "check whether", "check if", "ask for", "request", "you can",
    "the fix", "how to", "compare", "calculate", "read the", "look for",
    "before you sign", "before signing", "your options", "alternatives",
    "what to do", "protect yourself", "verify", "the rule is", "start by",
)


def _hits(text: str, needles: Sequence[str]) -> List[str]:
    lower = (text or "").lower()
    return [needle for needle in needles if needle in lower]


def classify_target(text: str) -> str:
    """What is this aimed at: a system, a person, or neither?

    Contempt wins over system-attack when both appear. A sentence can name a
    predatory lender and still sneer at the borrower, and that is exactly the
    case worth catching — the legitimate target does not launder the contempt.
    """
    contempt = _hits(text, _CONTEMPT_MARKERS)
    descriptors = _hits(text, _PROTECTED_DESCRIPTORS)
    systems = _hits(text, _SYSTEM_TARGETS)

    # An explicit contempt marker settles it, even when a legitimate system
    # target is also named. Naming a predatory lender does not launder a sneer
    # at the borrower in the same sentence.
    if contempt:
        return "person"
    # A protected descriptor alone is not contempt: "immigrant families are
    # overcharged" is reporting. It takes a generalizing framing to become one.
    if descriptors and _hits(text, ("are just", "are all", "always", "never learn")):
        return "person"
    if systems:
        return "system"
    return "neither"


def rage_bait_assessment(text: str) -> Dict[str, Any]:
    """Describe the shape of a piece of content without judging it yet."""
    outrage = _hits(text, _OUTRAGE_MARKERS)
    capability = _hits(text, _CAPABILITY_MARKERS)
    target = classify_target(text)
    return {
        "target": target,
        "outrage_markers": outrage,
        "capability_markers": capability,
        "outrage_present": bool(outrage),
        "capability_payload": bool(capability),
        # The forbidden shape: heat with nothing the reader can do.
        "rage_bait": bool(outrage) and not capability,
        "contempt": target == "person",
    }


def assert_publishable(text: str, *, context: str = "content") -> Dict[str, Any]:
    """Refuse contempt at people, and refuse outrage with no payload.

    Raises rather than returning a verdict, so a caller cannot forget to read
    the result. A forceful attack on a broken system with a concrete payload
    passes untouched — that register is the point of the brand.
    """
    assessment = rage_bait_assessment(text)
    if assessment["contempt"]:
        raise ContemptError(
            f"{context} aims contempt at people rather than at a system. "
            f"Ruthless toward the problem, humane toward the person."
        )
    if assessment["rage_bait"]:
        raise RageBaitError(
            f"{context} carries outrage markers {assessment['outrage_markers']} "
            f"with nothing the reader can do afterwards. Add the capability "
            f"payload or drop the heat."
        )
    return assessment


# --------------------------------------------------------------------- #
# What the optimizer is being taught
# --------------------------------------------------------------------- #

# An arm may not be reinforced when engagement rises while the signals that
# say a human was served fall. Tuned loose on purpose: this catches a trend,
# not a single noisy sample.
ENGAGEMENT_RISE_THRESHOLD = 0.15
QUALITY_FALL_THRESHOLD = -0.05


def reward_admissible(
    *,
    engagement_delta: float,
    capability_delta: float,
    trust_delta: float,
) -> Dict[str, Any]:
    """Decide whether a reward may reinforce an arm.

    The shortcut has a signature: engagement climbing while capability or
    trust decline. Read the signature, not the reward.
    """
    degrading = (capability_delta <= QUALITY_FALL_THRESHOLD
                 or trust_delta <= QUALITY_FALL_THRESHOLD)
    climbing = engagement_delta >= ENGAGEMENT_RISE_THRESHOLD
    shortcut = climbing and degrading
    return {
        "admissible": not shortcut,
        "shortcut_detected": shortcut,
        "engagement_delta": engagement_delta,
        "capability_delta": capability_delta,
        "trust_delta": trust_delta,
        "reason": (
            "engagement rising while capability or trust fall — this is the "
            "anger-to-engagement shortcut mid-formation"
            if shortcut else "no degradation signature"
        ),
    }


def assert_reward_admissible(
    *,
    arm: str,
    engagement_delta: float,
    capability_delta: float,
    trust_delta: float,
) -> Dict[str, Any]:
    """Gate a reward before it reaches the bandit. Raises on the shortcut."""
    verdict = reward_admissible(
        engagement_delta=engagement_delta,
        capability_delta=capability_delta,
        trust_delta=trust_delta,
    )
    if not verdict["admissible"]:
        raise RageBaitError(
            f"arm '{arm}' may not be reinforced: {verdict['reason']} "
            f"(engagement {engagement_delta:+.2f}, capability "
            f"{capability_delta:+.2f}, trust {trust_delta:+.2f})"
        )
    return verdict


# --------------------------------------------------------------------- #
# Fake engagement must not enter learning
# --------------------------------------------------------------------- #

# Engagement above this multiple of an account's own baseline is treated as
# unexplained until something explains it. Bought engagement and scraper
# artifacts both look like this, and both corrupt the reward if ingested.
IMPLAUSIBLE_MULTIPLE = 20.0


def engagement_plausible(
    *, observed: float, baseline: float, followers: int
) -> Dict[str, Any]:
    """Is this engagement signal explainable by the account's own history?"""
    reasons: List[str] = []
    if observed < 0:
        reasons.append("negative engagement is not a measurement")
    if followers > 0 and observed > followers * 2:
        reasons.append(
            f"engagement {observed} exceeds twice the follower count {followers}"
        )
    if baseline > 0 and observed > baseline * IMPLAUSIBLE_MULTIPLE:
        reasons.append(
            f"engagement {observed} is more than {IMPLAUSIBLE_MULTIPLE}x the "
            f"baseline {baseline}"
        )
    return {"plausible": not reasons, "reasons": reasons}


def assert_engagement_ingestible(
    *, observed: float, baseline: float, followers: int
) -> Dict[str, Any]:
    """Refuse an implausible engagement signal before it reaches analytics."""
    verdict = engagement_plausible(
        observed=observed, baseline=baseline, followers=followers
    )
    if not verdict["plausible"]:
        raise FakeEngagementError(
            "engagement signal is not plausible and must not enter learning: "
            + "; ".join(verdict["reasons"])
        )
    return verdict


# --------------------------------------------------------------------- #
# Material-relationship disclosure
# --------------------------------------------------------------------- #

# Promoting any of these without disclosure makes owned-company promotion
# look like independent editorial analysis. Trust compounds; so does its loss.
DISCLOSURE_REQUIRED_ENTITIES = (
    "pumpstation", "uniimente", "wealthmachine", "wealthmachineintelligence",
)

_DISCLOSURE_MARKERS = (
    "disclosure", "disclosed", "we own", "i own", "owned by", "our company",
    "sponsored", "paid partnership", "affiliate", "material relationship",
    "conflict of interest", "we operate", "part of uniimente",
)


def disclosure_required(text: str, *, extra_entities: Sequence[str] = ()) -> List[str]:
    """Which material relationships does this text mention?"""
    entities = tuple(DISCLOSURE_REQUIRED_ENTITIES) + tuple(
        e.lower() for e in extra_entities
    )
    return _hits(text, entities)


def assert_disclosed(text: str, *, extra_entities: Sequence[str] = ()) -> Dict[str, Any]:
    """Refuse promotion of an owned or related entity with no disclosure."""
    mentioned = disclosure_required(text, extra_entities=extra_entities)
    markers = _hits(text, _DISCLOSURE_MARKERS)
    if mentioned and not markers:
        raise IntegrityGuardError(
            f"content references material relationship(s) {sorted(set(mentioned))} "
            f"without a disclosure. Owned-company promotion may not look like "
            f"independent editorial analysis."
        )
    return {"entities": sorted(set(mentioned)), "disclosure_markers": markers,
            "disclosed": bool(markers) or not mentioned}


__all__ = [
    "IntegrityGuardError", "RageBaitError", "ContemptError", "FakeEngagementError",
    "ENGAGEMENT_RISE_THRESHOLD", "QUALITY_FALL_THRESHOLD", "IMPLAUSIBLE_MULTIPLE",
    "DISCLOSURE_REQUIRED_ENTITIES",
    "classify_target", "rage_bait_assessment", "assert_publishable",
    "reward_admissible", "assert_reward_admissible",
    "engagement_plausible", "assert_engagement_ingestible",
    "disclosure_required", "assert_disclosed",
]
