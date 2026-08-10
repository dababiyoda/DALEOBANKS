"""The mandate's own content, as data the system can run on.

A blank template is a quiz. Everything below is specified in the founder
mandate — the flagship channel, the three community pillars, the topic
mixes, the rabbit-hole journey, the daily edition's seven sections, the
language lanes, the shared primitives — so the defaults carry it rather than
asking the founder to retype it.

Two boundaries this file holds.

The public UNIIMENTE channel is a media surface beneath DALEOBANKS. It is not
the Golden Kernel and it is not constitutional UNIIMENTE. Every record here
that touches the name says which one it means, because the confusion would be
the most expensive one available.

Nothing here is authorization. Canon supplies purpose, topics, and structure.
Handles, credentials, budgets, and permission come from a founder
declaration, and a surface seeded from canon starts PLANNED — not even
SHADOW, because canon knows what the channel is for and nothing about who
owns the account.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# --------------------------------------------------------------------- #
# The flagship public rabbit hole
# --------------------------------------------------------------------- #

FLAGSHIP_CHANNEL: Dict[str, Any] = {
    "name": "UNIIMENTE",
    "public_brand_name": "UNIIMENTE",
    "parent_identity": "DALEOBANKS",
    "identity_type": "brand_account",
    "purpose": (
        "First major public rabbit hole beneath the DALEOBANKS media operating "
        "company. A public media channel — explicitly NOT the Golden Kernel and "
        "NOT constitutional UNIIMENTE."
    ),
    "audience": "Immigrant builders, cross-border earners, and people rebuilding capability",
    "kernel_distinction": (
        "PUBLIC_MEDIA_CHANNEL. Carries no constitutional authority, no identity "
        "root, and no consequence gate. Sharing a name with the Kernel is a "
        "brand lineage decision, not an authority claim."
    ),
    "topic_mix": (
        "financial_independence", "fire", "wealth_building", "psychology",
        "self_help", "spirituality_through_psychology_and_philosophy",
        "important_discoveries", "science", "technology", "ai",
        "entrepreneurship", "major_news",
    ),
    "risk_level": "medium",
    "monetization_policy": "none",
}

# --------------------------------------------------------------------- #
# The first community: three pillars
# --------------------------------------------------------------------- #

COMMUNITY = {
    "name": "First immigrant capability community",
    "aesthetic": "secret_society",
    # The aesthetic is belonging and progression. Naming what it is not,
    # here, in data, is cheaper than discovering the drift later.
    "aesthetic_means": (
        "belonging", "ritual", "progression", "identity", "seriousness",
        "selectivity", "shared_language", "ambition", "cultural_solidarity",
    ),
    "aesthetic_does_not_mean": (
        "false_mystical_authority", "fake_exclusivity", "cultic_control",
        "financial_promises", "deception", "coercion", "hidden_access_claims",
        "ideological_obedience",
    ),
}

PILLARS: Tuple[Dict[str, Any], ...] = (
    {
        "id": "pillar_1_fire",
        "name": "FIRE, money, ownership, and financial independence",
        "topics": (
            "saving", "budgeting", "emergency_reserves", "investing_education",
            "retirement", "tax_literacy", "income_growth", "business_ownership",
            "compound_growth", "financial_traps", "insurance_literacy",
            "credit_education", "asset_ownership", "long_term_wealth",
            "family_obligations", "cross_border_financial_realities",
        ),
        "boundary": (
            "Education, never individualized regulated financial advice. No "
            "income promises."
        ),
        "risk_class": "tier3",
    },
    {
        "id": "pillar_2_discoveries",
        "name": "Discoveries, technology, science, and important news",
        "topics": (
            "ai", "robotics", "software", "science", "engineering", "economics",
            "jobs", "emerging_industries", "major_policy_changes",
            "immigration_relevant_developments", "market_changes",
            "new_technologies", "business_opportunities",
        ),
        "must_answer": (
            "What happened?", "Why does it matter?", "Who benefits?",
            "Who is exposed?", "What changes because of this?",
            "What should a builder know?",
        ),
        "risk_class": "tier2",
    },
    {
        "id": "pillar_3_healing",
        "name": "Psychological and spiritual self-healing",
        "topics": (
            "trauma_informed_education", "identity_reconstruction", "discipline",
            "meaning", "emotional_regulation", "self_respect",
            "cultural_displacement", "fear", "shame", "helplessness",
            "survival_mode", "philosophy", "spiritual_exploration", "self_command",
        ),
        "boundary": (
            "No diagnosis. No replacing therapists. No supernatural certainty. "
            "No exploiting emotional vulnerability. No healing promises. No "
            "dependency."
        ),
        "risk_class": "tier3",
    },
)

# --------------------------------------------------------------------- #
# The rabbit hole journey
# --------------------------------------------------------------------- #

# Each stop carries the opposing case and a way out, because the territory
# graph refuses a node without them. The worked example from the mandate,
# encoded so the first graph is real rather than a placeholder.
RABBIT_HOLE: Tuple[Dict[str, Any], ...] = (
    {
        "title": "Why immigrant families may work extremely hard but still struggle to compound wealth",
        "surface": "tiktok", "depth": 0,
        "thesis": "Effort compounds differently when income leaves the household every month.",
        "counterargument": "Remittances buy option value and family resilience that a savings-rate spreadsheet does not price.",
        "off_ramp": "If this does not describe your situation, the general compounding explainer is the better start.",
        "capability_payload": "Work out your true savings rate including transfers before choosing any target.",
    },
    {
        "title": "The financial systems many families were never taught",
        "surface": "instagram", "depth": 1,
        "thesis": "Most financial traps are structural defaults, not personal failures.",
        "counterargument": "Structure explains a lot and not everything; individual choices still move the outcome.",
        "off_ramp": "Prefer to skip the systems framing? The practical checklist stands alone.",
        "capability_payload": "List every recurring fee you pay and find which are opt-out by default.",
    },
    {
        "title": "How FIRE changes when you support family across borders",
        "surface": "youtube", "depth": 2,
        "thesis": "Standard FIRE math assumes a household boundary that many families do not have.",
        "counterargument": "Adjusted FIRE targets can become an excuse to defer saving indefinitely.",
        "off_ramp": "Not supporting anyone abroad? Use the standard target and ignore this adjustment.",
        "capability_payload": "Recompute your number with transfers as a fixed obligation, not discretionary spend.",
    },
    {
        "title": "Where you actually are: a capability diagnostic",
        "surface": "web", "depth": 3,
        "thesis": "A specific starting point beats a general plan.",
        "counterargument": "Diagnostics can become procrastination dressed as preparation.",
        "off_ramp": "Skip it and start the emergency fund today; the diagnostic will still be here.",
        "capability_payload": "Answer eight questions and get one next action, not a report.",
        "terminal_action": "emergency_fund_started",
    },
)

# --------------------------------------------------------------------- #
# The daily edition
# --------------------------------------------------------------------- #

DAILY_NEWS = {
    "hour_local": 20,          # 8:00 PM in the declared timezone
    "content_type": "daily_high_signal_news",
    "purpose": (
        "Not headline repetition. Prioritize the largest discovery, the largest "
        "practical implication, the most underappreciated development, the "
        "largest relevant risk, the largest new opportunity, and one thing the "
        "audience should understand better tomorrow."
    ),
    "sections": (
        "what_happened", "why_it_matters", "what_most_people_are_missing",
        "who_benefits", "who_is_exposed", "what_changes", "what_to_watch_next",
    ),
    "separation_rule": "Reporting and opinion must be visibly distinguished.",
    "preferred_discovery": "feedly",
    "discovery_caveat": (
        "Feedly is a preferred discovery route, never evidence. An aggregator "
        "surfacing an article does not make the article a source."
    ),
}

# --------------------------------------------------------------------- #
# Language lanes and shared primitives
# --------------------------------------------------------------------- #

# Success is not language count. A lane is added when it improves revenue,
# qualified audience, owned distribution, talent access, or aspiration
# progress — so only the first ships enabled.
LANGUAGE_LANES: Tuple[Dict[str, Any], ...] = (
    {"language": "en", "region": "us", "status": "PRIMARY"},
    {"language": "es", "region": "latam", "status": "CANDIDATE"},
    {"language": "pt", "region": "br", "status": "CANDIDATE"},
)

# Candidate bottlenecks from the mandate. Possibilities, not priorities: the
# registry ranks them by how many live aspirations each actually unlocks.
CANDIDATE_PRIMITIVES: Tuple[Dict[str, str], str] = (
    {"name": "portable reputation", "category": "coordination",
     "description": "Reputation a person can carry between platforms and institutions."},
    {"name": "proof-to-settlement", "category": "economic",
     "description": "A path from verified work to money actually moving."},
    {"name": "safe agent permissions", "category": "technical",
     "description": "Bounded, revocable authority for automated systems."},
    {"name": "capital access", "category": "economic",
     "description": "Productive capital reaching people without existing collateral."},
    {"name": "education", "category": "capability",
     "description": "Learning that transfers into what someone can actually do."},
)

# --------------------------------------------------------------------- #
# Ownership dispositions
# --------------------------------------------------------------------- #

# BUILD is one of seven. Mission progress can exceed ownership value, so the
# default is UNDECIDED and choosing costs a rationale.
DISPOSITION_GUIDANCE = {
    "BUILD": "ownership creates strategic control or a moat",
    "PARTNER": "aligned specialists can solve it faster",
    "FUND": "capital is the binding constraint",
    "OPEN_SOURCE": "wide availability beats exclusivity",
    "POPULARIZE": "awareness, prestige, talent, or demand is the bottleneck",
    "STANDARDIZE": "fragmentation blocks progress",
    "PURCHASE": "the primitive is already commoditized",
}

# --------------------------------------------------------------------- #
# Editorial portfolio
# --------------------------------------------------------------------- #

# Mission alignment operates at portfolio level. Optimizing every unit toward
# a venture cell turns the brand into propaganda for internal companies.
PORTFOLIO_MIX = (
    "entertainment", "education", "community", "culture", "commercial_content",
    "aspiration_campaigns", "news", "lifestyle", "relationship_building",
    "high_leverage_technical_debate",
)



# --------------------------------------------------------------------- #
# The complete blueprint
# --------------------------------------------------------------------- #

# Action -> Asset -> System -> Business -> Network -> Infrastructure. Opus
# Maximus is not on this list because it is not a component: it is what the
# components add up to, and only if they compound.
#
# This map is deliberately complete rather than deliberately small. A thing
# with no map has nowhere to grow, and future work needs a target to build
# against instead of rediscovering the shape each time. Mapping costs
# nothing and claims nothing: BLUEPRINT is a coordinate, not an achievement.
#
# `maturity` records what is true today, not what is intended. The entries
# marked BUILT have implementation and tests and have still never touched
# the world, which is exactly the distinction this exists to keep visible.
#
# Every entry names the external consequence that would prove it earned its
# place. Deadlines are short on purpose: a component that cannot touch the
# world inside two quarters is not being built, it is being admired.

def _c(name, tier, dimensions, consequence, days, maturity="BLUEPRINT",
       parent=None):
    return {
        "name": name,
        "tier": tier,
        "dimensions": list(dimensions),
        "expected_external_consequence": consequence,
        "proof_deadline_days": days,
        "maturity": maturity,
        "parent": parent,
    }


OPUS_COMPONENTS = (
    # ---------------- infrastructure: what everything routes through ----
    _c("eligibility super-node", "infrastructure", ["autonomy", "infrastructure"],
       "an outside party accepts a DALEOBANKS eligibility determination for a "
       "decision it would otherwise have made itself", 180),
    _c("default routing super-node", "infrastructure",
       ["distribution", "infrastructure"],
       "a person outside the org reaches an opportunity through this routing "
       "rather than through search", 180),
    _c("proof and truth super-node", "infrastructure",
       ["proof", "knowledge", "infrastructure"],
       "someone outside cites a DALEOBANKS claim record as their reason for "
       "changing a position", 180),
    _c("cashflow and settlement super-node", "infrastructure",
       ["capital", "infrastructure"],
       "money moves in and is reconciled against a bank record", 180),
    _c("owned distribution rails", "infrastructure",
       ["distribution", "autonomy", "infrastructure"],
       "an audience is reached during a platform outage or ban", 180),
    _c("institutional evidence spine", "infrastructure",
       ["proof", "knowledge", "infrastructure"],
       "an external auditor reconstructs a decision from the ledger alone",
       180, maturity="BUILT"),
    _c("civilization-seeding program", "infrastructure",
       ["knowledge", "capability", "infrastructure"],
       "a primitive DALEOBANKS made legible is built by someone with no "
       "relationship to DALEOBANKS", 180),

    # ---------------- network: capable people who find each other -------
    _c("immigrant capability community", "network",
       ["capability", "distribution"],
       "two members who met here complete something neither would have "
       "completed alone", 120, parent="default routing super-node"),
    _c("collaboration and expert network", "network",
       ["capability", "knowledge"],
       "an expert with no prior relationship contributes to a research lead "
       "and lets their name stand behind it", 120,
       parent="proof and truth super-node"),
    _c("creator and contributor network", "network",
       ["capability", "distribution"],
       "someone outside publishes under the standard and is read", 120,
       parent="default routing super-node"),
    _c("partner and venture network", "network", ["capital", "capability"],
       "a partner commits resources to a jointly-run program", 150,
       parent="eligibility super-node"),
    _c("customer network", "network", ["capital", "distribution"],
       "a customer buys a second time without being asked", 150,
       parent="cashflow and settlement super-node"),
    _c("research and scientific network", "network", ["knowledge", "proof"],
       "an independent group reproduces a result DALEOBANKS surfaced", 180,
       parent="proof and truth super-node"),

    # ---------------- business: the part that pays for the rest ---------
    _c("early cash engine", "business", ["capital", "autonomy"],
       "one real buyer pays for one real delivery and accepts it", 90,
       parent="cashflow and settlement super-node"),
    _c("membership and community subscription", "business",
       ["capital", "distribution"],
       "a member renews after the first period without a discount", 120,
       parent="early cash engine"),
    _c("education and learning products", "business",
       ["capital", "capability"],
       "a learner pays, completes, and reports a capability they did not have",
       120, parent="early cash engine"),
    _c("sponsorship and brand partnerships", "business",
       ["capital", "distribution"],
       "a sponsor pays under disclosed terms and renews", 150,
       parent="early cash engine"),
    _c("digital products and commerce", "business", ["capital"],
       "a product is delivered, accepted, and not refunded", 120,
       parent="early cash engine"),
    _c("events and experiences", "business", ["capital", "capability"],
       "attendees pay, show up, and one collaboration forms that outlives the "
       "event", 180, parent="early cash engine"),
    _c("licensing and media services", "business", ["capital", "distribution"],
       "an outside organization licenses DALEOBANKS work and ships it", 180,
       parent="early cash engine"),
    _c("free cash flow to UNIIMENTE", "business", ["capital", "autonomy"],
       "founder-authorized cash moves from DALEOBANKS to UNIIMENTE "
       "development and is reconciled", 180,
       parent="cashflow and settlement super-node"),

    # ---------------- system: machinery that runs unwatched -------------
    _c("media operating system", "system", ["distribution", "knowledge"],
       "a published piece produces a reply from someone who was not already "
       "in the audience", 90, maturity="BUILT",
       parent="immigrant capability community"),
    _c("content factory", "system", ["distribution", "capability"],
       "one researched thesis becomes artifacts on three surfaces and one "
       "outperforms the others for a reason that was predicted", 90,
       maturity="BUILT", parent="media operating system"),
    _c("localization engine", "system", ["distribution", "knowledge"],
       "a non-English reader acts on a localized artifact", 120,
       maturity="BUILT", parent="media operating system"),
    _c("daily news operation", "system", ["distribution", "knowledge"],
       "a reader changes a decision because of an edition and says so", 90,
       maturity="SKETCHED", parent="media operating system"),
    _c("source and evidence pipeline", "system", ["knowledge", "proof"],
       "a consequential claim survives an outside challenge on its sources",
       90, maturity="BUILT", parent="proof and truth super-node"),
    _c("correction ledger", "system", ["proof", "knowledge"],
       "a published correction is acknowledged by someone who saw the "
       "original", 120, maturity="BUILT", parent="proof and truth super-node"),
    _c("analytics and experiment engine", "system", ["knowledge", "proof"],
       "an experiment falsifies a belief DALEOBANKS held and the strategy "
       "changes", 90, maturity="BUILT", parent="media operating system"),
    _c("audience intelligence ledger", "system", ["knowledge", "distribution"],
       "a segment prediction is confirmed by behavior nobody prompted", 120,
       maturity="BUILT", parent="media operating system"),
    _c("opportunity router", "system", ["capital", "proof"],
       "WMI returns an assessment on a packet this system produced, through "
       "the real intake and not the mock", 90, maturity="BUILT",
       parent="early cash engine"),
    _c("infinite goal chase", "system", ["capability", "proof"],
       "one aspiration gate clears on evidence from outside this process", 90,
       maturity="BUILT", parent="proof and truth super-node"),
    _c("participant ladder", "system", ["capability", "distribution"],
       "one person advances a rung by a verified voluntary action", 90,
       maturity="BUILT", parent="immigrant capability community"),
    _c("debate engine", "system", ["knowledge", "capability"],
       "a public debate produces a research lead an outside expert takes up",
       120, maturity="BUILT", parent="collaboration and expert network"),
    _c("relationship memory", "system", ["capability", "knowledge"],
       "a returning collaborator is recognized and served better because of "
       "it, with consent on record", 120, maturity="SKETCHED",
       parent="collaboration and expert network"),
    _c("community operating system", "system", ["capability", "distribution"],
       "a cohort completes a learning path without staff intervention", 150,
       parent="immigrant capability community"),
    _c("automation loom", "system", ["autonomy", "capability"],
       "a routine workflow runs unattended for a month and its failures were "
       "all caught by its own guards", 150, maturity="SKETCHED",
       parent="owned distribution rails"),
    _c("incident and failure posture", "system", ["autonomy", "proof"],
       "a real incident degrades the system toward pause rather than toward "
       "publishing", 120, maturity="BUILT",
       parent="institutional evidence spine"),
    _c("dependency and portability registry", "system",
       ["autonomy", "infrastructure"],
       "a vendor is replaced without an outage", 150, maturity="BUILT",
       parent="institutional evidence spine"),
    _c("compounding ledger", "system", ["proof", "knowledge"],
       "a component is killed or reshaped because this ledger refused it, and "
       "the resources go somewhere that works", 90, maturity="BUILT",
       parent="institutional evidence spine"),
    _c("pumpstation handoff", "system", ["capital", "capability"],
       "one person is handed off with disclosure and consent and reports the "
       "outcome", 150, parent="eligibility super-node"),

    # ---------------- asset: value that survives the machinery ----------
    _c("owned audience list", "asset", ["distribution"],
       "one person consents to be reached off-platform and is reached", 60,
       parent="owned distribution rails"),
    _c("claim and evidence library", "asset", ["knowledge", "proof"],
       "an outside reader corrects a claim and the correction is published",
       60, maturity="BUILT", parent="proof and truth super-node"),
    _c("content archive", "asset", ["knowledge", "distribution"],
       "someone finds and uses an old piece without being pointed at it", 90,
       parent="owned distribution rails"),
    _c("account registry", "asset", ["infrastructure", "autonomy"],
       "an official surface is verified against the registry by someone "
       "outside", 90, maturity="BUILT", parent="owned distribution rails"),
    _c("persona and brand genome", "asset", ["knowledge", "distribution"],
       "a stranger identifies DALEOBANKS work without the name on it", 120,
       maturity="BUILT", parent="content archive"),
    _c("territory and rabbit hole graph", "asset",
       ["capability", "distribution"],
       "one person walks from a public surface to a capability payload and "
       "takes the terminal action", 90, maturity="BUILT",
       parent="immigrant capability community"),
    _c("aspiration registry", "asset", ["proof", "capability"],
       "a blocked aspiration is unblocked by something built outside", 120,
       maturity="BUILT", parent="infinite goal chase"),
    _c("shared primitive registry", "asset", ["knowledge", "capability"],
       "an outside builder picks up a primitive from this registry", 150,
       maturity="BUILT", parent="civilization-seeding program"),

    # ---------------- action: the smallest thing doable today -----------
    _c("one daily edition", "action", ["distribution"],
       "one edition reaches one reader who did not ask for it and who comes "
       "back for the next one", 30, parent="owned audience list"),
    _c("one researched thesis", "action", ["knowledge", "proof"],
       "one thesis is challenged from outside and holds", 30,
       maturity="SKETCHED", parent="claim and evidence library"),
    _c("one verified advancement action", "action", ["capability"],
       "one participant voluntarily completes a defined action and it is "
       "verified", 45, parent="participant ladder"),
    _c("one reconciled sale", "action", ["capital"],
       "one payment clears, one delivery is accepted, and the margin is "
       "positive", 45, parent="early cash engine"),
    _c("one qualified opportunity packet", "action", ["capital", "proof"],
       "one packet is assessed by WMI through the real intake", 45,
       maturity="SKETCHED", parent="opportunity router"),
    _c("one published correction", "action", ["proof"],
       "one material correction is published and reaches the original "
       "audience", 45, parent="correction ledger"),
    _c("one warm handoff", "action", ["capability"],
       "one person is routed onward with disclosure and consent", 60,
       parent="pumpstation handoff"),
    _c("one localized artifact", "action", ["distribution"],
       "one artifact is acted on in a language that is not English", 60,
       maturity="SKETCHED", parent="localization engine"),
)



def default_declaration(founder: str = "Alfonso Lopez",
                        timezone: str = "America/New_York") -> Dict[str, Any]:
    """A declaration carrying the mandate's canon, missing only what is owned.

    Everything structural is filled. What stays blank is what canon cannot
    know: the handle, the destination, the budget, and the source packet.
    Those are the six declarations, and their absence is the point — the
    system runs, reports what it did, and names them.
    """
    return {
        "founder": founder,
        "timezone": timezone,
        "campaign": {
            "aspiration": "Prove one real DALEOBANKS source-to-owned-relationship transaction",
            "success_state": "One retained external observation from a declared surface",
            "gate": "Founder-declared surface, source packet, destination, and exact authority",
            "sbm": "AUTHORIZED_EXTERNAL_EVIDENCE_LOOP_CLOSURE_RATE",
            "evidence_threshold": "One retained observation: positive, negative, mixed, or inconclusive",
            "resource_ceiling": "USD 0 — no spend authorized",
            "stop_condition": "No response within 14 days, or any integrity guard fires",
        },
        "owned_audience": {"destination": "", "channel": "email"},
        "budget": {"ceiling": 0.0, "currency": "USD"},
        "accounts": [{
            "name": FLAGSHIP_CHANNEL["name"],
            "platform": "x",
            "handle": "",
            "language": "en",
            "region": "us",
            "identity_type": FLAGSHIP_CHANNEL["identity_type"],
            "purpose": FLAGSHIP_CHANNEL["purpose"],
            "audience": FLAGSHIP_CHANNEL["audience"],
            "allowed_topics": list(FLAGSHIP_CHANNEL["topic_mix"]),
            "forbidden_topics": [
                "individual_financial_advice", "financial_product_recommendation",
                "mental_health_diagnosis", "medical_claims",
            ],
            "monetization_policy": FLAGSHIP_CHANNEL["monetization_policy"],
            "risk_level": FLAGSHIP_CHANNEL["risk_level"],
            "public_brand_name": FLAGSHIP_CHANNEL["public_brand_name"],
            "parent_identity": FLAGSHIP_CHANNEL["parent_identity"],
            "topic_lane": "flagship_rabbit_hole",
        }],
        "source_packet": {
            "topic": "cross-border financial friction",
            "discovery_source": DAILY_NEWS["preferred_discovery"],
            "region": "us",
            "sources": [],
        },
        "languages": [lane["language"] for lane in LANGUAGE_LANES
                      if lane["status"] == "PRIMARY"],
    }


__all__ = [
    "FLAGSHIP_CHANNEL", "COMMUNITY", "PILLARS", "RABBIT_HOLE", "DAILY_NEWS",
    "LANGUAGE_LANES", "CANDIDATE_PRIMITIVES", "DISPOSITION_GUIDANCE",
    "PORTFOLIO_MIX", "OPUS_COMPONENTS", "default_declaration",
]
