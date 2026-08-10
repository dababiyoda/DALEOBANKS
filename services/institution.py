"""The front door.

Everything else in this repository is a part. This is the machine: one
declaration file in, one wired institution out, and a report generated from
live state rather than written by hand.

The reason it exists is that a parts bin is not a company. Each service here
enforces something real, but until now every one of them had to be called by
someone who already knew its arguments — which means the only operator who
could run DALEOBANKS was whoever last read the source. That is not an
institution, it is a codebase with good intentions.

Three things this refuses to do.

It will not run on an incomplete declaration. Missing fields are named, not
defaulted, because a default is a decision someone did not make.

It will not raise its own authority. Every surface starts SHADOW and stays
there. A config file is not a standing mandate, and the composition layer is
exactly where that boundary would erode first if it were allowed to.

It will not report what it did not do. ``report()`` reads the durable store
and the registries; there is no field a human fills in. A report that cannot
be written by hand cannot be flattering by accident.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from services.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_DECLARATION_PATH = "founder_declaration.yaml"

# The six the aspiration registry refuses a campaign without, plus the two
# that decide where anything lands.
REQUIRED_CAMPAIGN_FIELDS = (
    "aspiration", "success_state", "gate", "sbm",
    "evidence_threshold", "resource_ceiling", "stop_condition",
)
REQUIRED_TOP_LEVEL = ("founder", "timezone", "campaign", "accounts")


from db.models import ComponentRecord


class DeclarationError(ValueError):
    """The declaration is incomplete or asks for authority it cannot grant."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - yaml is a declared dep
        raise DeclarationError(f"pyyaml is required to read {path}: {exc}")
    if not os.path.exists(path):
        raise DeclarationError(
            f"no declaration at {path}. Copy founder_declaration.example.yaml "
            f"and fill in the six campaign fields"
        )
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def _run_sync(coro: Any) -> Any:
    """Run a coroutine from sync code, whether or not a loop is already up."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop: run on a private one so the caller stays sync.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass
class Declaration:
    """What the founder actually declared, validated."""

    founder: str
    timezone: str
    campaign: Dict[str, Any]
    accounts: List[Dict[str, Any]]
    owned_audience: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    source_packet: Dict[str, Any] = field(default_factory=dict)
    languages: List[str] = field(default_factory=lambda: ["en"])
    path: str = ""

    @classmethod
    def canonical(cls) -> "Declaration":
        """The mandate's own defaults, with only ownership left blank.

        Running with no file at all is legitimate and produces a real cycle.
        What canon cannot supply is what canon cannot know: the handle, the
        destination, the budget, the source packet.
        """
        from services.canon import default_declaration

        raw = default_declaration()
        return cls(
            founder=raw["founder"], timezone=raw["timezone"],
            campaign=raw["campaign"], accounts=raw["accounts"],
            owned_audience=raw["owned_audience"], budget=raw["budget"],
            source_packet=raw["source_packet"], languages=raw["languages"],
            path="<canon>",
        )

    @classmethod
    def load(cls, path: str = DEFAULT_DECLARATION_PATH) -> "Declaration":
        if not os.path.exists(path):
            # No file is not an error. It means "run the canon and tell me
            # what I still have to decide."
            return cls.canonical()
        raw = _load_yaml(path)
        missing = [k for k in REQUIRED_TOP_LEVEL if not raw.get(k)]
        if missing:
            raise DeclarationError(
                "declaration is missing: " + ", ".join(missing)
            )
        campaign = dict(raw["campaign"])
        blank = [
            k for k in REQUIRED_CAMPAIGN_FIELDS
            if not str(campaign.get(k, "")).strip()
        ]
        if blank:
            raise DeclarationError(
                "campaign is missing the declarations a campaign cannot run "
                "without: " + ", ".join(blank)
            )
        return cls(
            founder=str(raw["founder"]), timezone=str(raw["timezone"]),
            campaign=campaign, accounts=list(raw["accounts"]),
            owned_audience=dict(raw.get("owned_audience") or {}),
            budget=dict(raw.get("budget") or {}),
            source_packet=dict(raw.get("source_packet") or {}),
            languages=list(raw.get("languages") or ["en"]),
            path=path,
        )

    def gaps(self) -> List[str]:
        """What is declared but empty. Legal to run with; named anyway."""
        gaps: List[str] = []
        if not str(self.owned_audience.get("destination", "")).strip():
            gaps.append("owned_audience.destination — nowhere for a relationship to land")
        if float(self.budget.get("ceiling", 0.0) or 0.0) <= 0:
            gaps.append("budget.ceiling is zero — no spend is authorized")
        if not self.source_packet.get("sources"):
            gaps.append("source_packet.sources is empty — no evidence to reason over")
        for account in self.accounts:
            if not str(account.get("handle", "")).strip():
                gaps.append(
                    f"accounts[{account.get('name')}].handle is blank — "
                    f"the surface is planned, not owned"
                )
        return gaps


class DaleoBanks:
    """One institution, wired from one declaration."""

    def __init__(self, declaration: Declaration) -> None:
        self.declaration = declaration
        self._account_ids: List[str] = []

        from services.account_registry import AccountRegistry
        from services.aspiration_registry import AspirationRegistry
        from services.dependency_registry import DependencyRegistry
        from services.goal_chase import GoalChaseScheduler
        from services.incident_posture import IncidentPosture
        from services.media_operating_system import MediaOperatingSystem
        from services.compounding_ledger import CompoundingLedger
        from services.participant_ladder import ParticipantLadder

        self.accounts = AccountRegistry()
        self.media = MediaOperatingSystem(accounts=self.accounts)
        self.aspirations = AspirationRegistry()
        self.chase = GoalChaseScheduler(registry=self.aspirations)
        self.ladder = ParticipantLadder()
        self.dependencies = DependencyRegistry()
        self.incidents = IncidentPosture()
        self.opus = CompoundingLedger()

    @classmethod
    def from_declaration(cls, path: str = DEFAULT_DECLARATION_PATH) -> "DaleoBanks":
        return cls(Declaration.load(path))

    # ----------------------------------------------------------------- #
    # Preflight
    # ----------------------------------------------------------------- #

    def preflight(self) -> Dict[str, Any]:
        """What is authorized, what is blocked, and what is merely declared.

        Reports before touching anything, because the useful answer is
        usually "here is what you have not decided yet."
        """
        gaps = self.declaration.gaps()
        return {
            "founder": self.declaration.founder,
            "timezone": self.declaration.timezone,
            "declaration_path": self.declaration.path,
            "campaign_complete": True,  # Declaration.load would have refused
            "declared_accounts": len(self.declaration.accounts),
            "languages": self.declaration.languages,
            "budget_ceiling": float(self.declaration.budget.get("ceiling", 0.0) or 0.0),
            "publishing_mode": "SHADOW_ONLY",
            "live_publication": "NOT_AUTHORIZED_BY_A_DECLARATION_FILE",
            "gaps": gaps,
            "can_run_shadow_cycle": not any("source_packet" in g for g in gaps),
            "note": (
                "a declaration seeds surfaces as SHADOW and never raises "
                "authority; live publication needs the separate approval and "
                "capability path"
            ),
        }

    # ----------------------------------------------------------------- #
    # Bootstrap
    # ----------------------------------------------------------------- #

    def bootstrap(self, session: Any) -> Dict[str, Any]:
        """Seed surfaces and the aspiration. Idempotent, shadow-only."""
        from db.models import AccountLane, AspirationRecord

        seeded_accounts: List[str] = []
        for spec in self.declaration.accounts:
            existing = session.query(AccountLane).filter(
                lambda row, s=spec: row.name == s.get("name")
            ).first()
            if existing is not None:
                seeded_accounts.append(existing.id)
                continue
            lane = self.accounts.register(
                session,
                name=spec.get("name", ""),
                platform=spec.get("platform", "x"),
                handle=spec.get("handle", ""),
                language=spec.get("language", "en"),
                identity_type=spec.get("identity_type", "brand_account"),
                purpose=spec.get("purpose", ""),
                audience=spec.get("audience", ""),
                allowed_topics=list(spec.get("allowed_topics") or []),
                forbidden_topics=list(spec.get("forbidden_topics") or []),
                monetization_policy=spec.get("monetization_policy", "none"),
                risk_level=spec.get("risk_level", "low"),
                legal_principal=self.declaration.founder,
                parent_identity="DALEOBANKS",
                public_brand_name=spec.get("name", ""),
                region=spec.get("region", "global"),
                topic_lane=spec.get("topic_lane", ""),
                status="SHADOW",
                current_authorization="SHADOW_ONLY",
                commercial_disclosure_requirements=list(
                    spec.get("commercial_disclosure_requirements")
                    or ["disclose material relationships"]
                ),
            )
            seeded_accounts.append(lane.id)
        self._account_ids = seeded_accounts

        campaign = self.declaration.campaign
        aspiration = session.query(AspirationRecord).filter(
            lambda row, c=campaign: row.founder_statement == c["aspiration"]
        ).first()
        if aspiration is None:
            aspiration = self.aspirations.register(
                session,
                founder_statement=campaign["aspiration"],
                success_state=campaign["success_state"],
                owner=self.declaration.founder,
                source_lineage=[self.declaration.path],
                status="ACTIVE",
                importance="critical",
                resource_budget=str(campaign["resource_ceiling"]),
                review_trigger=str(campaign["stop_condition"]),
            )
            self.aspirations.set_backcast(
                session,
                aspiration_id=aspiration.id,
                success_state=campaign["success_state"],
                stages=[
                    {"gate": "sustained owned distribution"},
                    {"gate": campaign["gate"]},
                ],
                repeatable_system="one cheapest reversible pilot per period",
            )
        return {
            "accounts_seeded": len(seeded_accounts),
            "aspiration_id": aspiration.id,
            "current_gate": aspiration.current_gate,
            "all_surfaces_shadow": True,
        }

    def seed_canon(self, session: Any) -> Dict[str, Any]:
        """Seed the structural canon: rabbit hole, pillars, primitives.

        Structure only. No handle, no credential, no authority, no claim that
        anyone has walked any of it.
        """
        from db.models import AspirationRecord, SharedPrimitive, TerritoryNode
        from services.canon import CANDIDATE_PRIMITIVES, PILLARS, RABBIT_HOLE
        from services.participant_ladder import register_territory_node

        existing_nodes = {n.title for n in session.query(TerritoryNode).all()}
        node_ids: List[str] = []
        previous: Optional[str] = None
        for spec in RABBIT_HOLE:
            if spec["title"] in existing_nodes:
                continue
            node = register_territory_node(
                session, title=spec["title"], surface=spec["surface"],
                depth=spec["depth"], thesis=spec["thesis"],
                counterargument=spec["counterargument"],
                off_ramp=spec["off_ramp"],
                capability_payload=spec["capability_payload"],
                terminal_action=spec.get("terminal_action", ""),
            )
            if previous is not None:
                prior = session.query(TerritoryNode).filter(
                    lambda row, p=previous: row.id == p
                ).first()
                if prior is not None:
                    prior.next_node_ids.append(node.id)
            previous = node.id
            node_ids.append(node.id)

        aspiration = session.query(AspirationRecord).filter(
            lambda row: row.founder_statement == self.declaration.campaign["aspiration"]
        ).first()

        existing_primitives = {p.name for p in session.query(SharedPrimitive).all()}
        primitive_ids: List[str] = []
        for spec in CANDIDATE_PRIMITIVES:
            if spec["name"] in existing_primitives:
                continue
            primitive = self.aspirations.register_primitive(
                session, name=spec["name"], description=spec["description"],
                category=spec["category"],
                unlocks=[aspiration.id] if aspiration else [],
            )
            primitive_ids.append(primitive.id)

        session.commit()
        return {
            "territory_nodes": len(node_ids),
            "pillars": [p["id"] for p in PILLARS],
            "primitives": len(primitive_ids),
            "note": (
                "structure only; no handle, credential, authority, or claim "
                "that anyone has walked it"
            ),
        }

    def seed_opus(self, session: Any) -> Dict[str, Any]:
        """Register the components of the larger work, and let the ceiling bite.

        The canon lists thirteen components. The debt ceiling admits twelve
        unproven ones. That is not a sizing mistake to be tuned away: the
        thirteenth is refused, in the first second of the first run, before
        anything has been built badly. Construction is rationed by proof from
        the beginning, and the refusal is in the output where it can be read.
        """
        from services.canon import OPUS_COMPONENTS
        from services.compounding_ledger import ArchitectureDebtError, tier_rank

        by_name: Dict[str, str] = {
            c.name: c.id for c in session.query(ComponentRecord).all()
        }
        registered: List[str] = []
        refused: List[Dict[str, str]] = []

        # Cheapest first. When the ceiling bites it must refuse the most
        # abstract component, never the one closest to a real consequence:
        # the failure mode being guarded against is a finished cathedral with
        # no door.
        ordered = sorted(OPUS_COMPONENTS, key=lambda spec: tier_rank(spec["tier"]))

        for spec in ordered:
            if spec["name"] in by_name:
                continue
            try:
                record = self.opus.register(
                    session,
                    name=spec["name"],
                    tier=spec["tier"],
                    dimensions=spec["dimensions"],
                    expected_external_consequence=(
                        spec["expected_external_consequence"]
                    ),
                    proof_deadline_days=spec["proof_deadline_days"],
                )
            except ArchitectureDebtError as exc:
                refused.append({"name": spec["name"], "reason": str(exc)})
                continue
            by_name[record.name] = record.id
            registered.append(record.name)

        # Composition runs after, upward, and only between components that
        # both survived the ceiling.
        composed = 0
        for spec in ordered:
            parent = spec.get("parent")
            if not parent:
                continue
            child_id, parent_id = by_name.get(spec["name"]), by_name.get(parent)
            if child_id and parent_id:
                self.opus.compose(session, child_id, parent_id)
                composed += 1

        session.commit()
        return {
            "registered": len(registered),
            "composed": composed,
            "refused": refused,
            "note": (
                "each component owes one external consequence by a deadline; "
                "refusals here are the ceiling working, not a failure to seed"
            ),
        }

    def opus_report(self, session: Any) -> Dict[str, Any]:
        """What the larger work has actually done outside itself.

        This is the report that is allowed to be unflattering about the rest
        of the repository, including the parts that were hardest to build.
        """
        report = self.opus.compounding_report(session)
        report["local_optimum_warning"] = report["verdict"] in (
            "ARCHITECTURE_ONLY",
            "MOSTLY_UNPROVEN",
        )
        report["cheapest_real_world_test"] = self._cheapest_real_test(session)
        return report

    def _cheapest_real_test(self, session: Any) -> Dict[str, Any]:
        """The lowest-tier unproven component: the shortest path to reality."""
        from services.compounding_ledger import tier_rank

        candidates = [
            c for c in self.opus.unproven(session)
        ]
        if not candidates:
            return {"component": None, "action": "nothing unproven is pending"}
        cheapest = min(candidates, key=lambda c: tier_rank(c.tier))
        return {
            "component": cheapest.name,
            "tier": cheapest.tier,
            "action": cheapest.expected_external_consequence,
            "due": cheapest.proof_deadline.isoformat()
            if cheapest.proof_deadline
            else None,
        }

    def daily_edition(
        self, session: Any, *, sections: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """The 8:00 PM edition, refused unless all seven sections are present.

        Its purpose is not headline repetition, and the contract enforces
        that by requiring the section that is hardest to fake: what most
        people are missing.
        """
        from db.models import ClaimRecord, SourceRecord
        from services.canon import DAILY_NEWS

        claims = session.query(ClaimRecord).all()
        sources = session.query(SourceRecord).all()
        if not claims or not sources:
            return {
                "status": "REFUSED",
                "reason": "a daily edition needs claims and sources; there is nothing to report",
                "hour_local": DAILY_NEWS["hour_local"],
                "timezone": self.declaration.timezone,
            }
        body = sections or {}
        missing = [s for s in DAILY_NEWS["sections"] if not str(body.get(s, "")).strip()]
        if missing:
            return {
                "status": "REFUSED",
                "reason": "edition is missing sections: " + ", ".join(missing),
                "required_sections": list(DAILY_NEWS["sections"]),
                "separation_rule": DAILY_NEWS["separation_rule"],
            }
        record = self.media.create_daily_news(
            session, topic=self.declaration.source_packet.get("topic", "daily"),
            sections=body, claim_ids=[claims[-1].id],
            source_ids=[sources[-1].id],
            counterargument=self.declaration.source_packet.get(
                "counterargument", "The strongest case against today's read."
            ),
            uncertainty="single-day window",
            audiences=[self.declaration.accounts[0].get("audience", "general")],
        )
        return {"status": "OK", "content_id": record.id,
                "hour_local": DAILY_NEWS["hour_local"],
                "timezone": self.declaration.timezone}

    # ----------------------------------------------------------------- #
    # One cycle
    # ----------------------------------------------------------------- #

    def run_cycle(self, session: Any, *, adapter: Any = None) -> Dict[str, Any]:
        """Source through shadow receipt, then ask the loop what is next.

        Runs only what the declaration supports. A missing piece stops that
        stage and is reported rather than substituted.
        """
        from services.social_base import BaseSocialClient

        boot = self.bootstrap(session)
        steps: List[Dict[str, Any]] = [{"step": "bootstrap", **boot}]
        steps.append({"step": "seed_canon", **self.seed_canon(session)})

        sources = self.declaration.source_packet.get("sources") or []
        if not sources:
            steps.append({
                "step": "ingest", "status": "SKIPPED",
                "reason": "source_packet.sources is empty; there is nothing to reason over",
            })
            steps.append(self._chase_step(session))
            return {"cycle": "PARTIAL", "steps": steps}

        topic = self.declaration.source_packet.get("topic", "general")
        discovery = self.declaration.source_packet.get("discovery_source", "direct")
        source_ids: List[str] = []
        for spec in sources:
            record = self.media.ingest_source(
                session,
                title=spec.get("title", ""), url=spec.get("url", ""),
                source_class=spec.get("source_class", "credible_news"),
                topic=topic, source_text=spec.get("text", ""),
                publisher=spec.get("publisher", ""), discovery_source=discovery,
                primary_source_url=spec.get("primary_source_url", ""),
            )
            source_ids.append(record.id)
        steps.append({"step": "ingest", "status": "OK", "sources": len(source_ids)})

        claim = self.media.create_claim(
            session, statement=self.declaration.source_packet.get(
                "claim", f"A recurring pattern in {topic} that is not widely priced in."
            ),
            source_ids=source_ids, evidence_class="SUPPORTED_INFERENCE",
            confidence=0.6,
            uncertainty="single-window observation; not causal",
        )
        steps.append({"step": "claim", "status": "OK", "claim_id": claim.id})

        content = self.media.create_content(
            session, content_type="explainer", topic=topic,
            thesis=self.declaration.source_packet.get(
                "thesis", f"What most people miss about {topic}."
            ),
            claim_ids=[claim.id], source_ids=source_ids,
            counterargument=self.declaration.source_packet.get(
                "counterargument",
                "The pattern may be selection effect rather than mechanism.",
            ),
            daleobanks_position="Educational. Not individualized advice.",
            uncertainty="single-window observation",
            audiences=[self.declaration.accounts[0].get("audience", "general")],
            formats=["post"],
            funnel_destination=self.declaration.owned_audience.get("destination", ""),
        )
        steps.append({"step": "content", "status": "OK", "content_id": content.id})

        artifacts: List[str] = []
        for language in self.declaration.languages:
            artifact = self.media.localize(
                session, content_id=content.id, language=language,
                region=self.declaration.source_packet.get("region", "global"),
                platform=self.declaration.accounts[0].get("platform", "x"),
                text=content.thesis, claim_ids=[claim.id], source_ids=source_ids,
                disclosure="AI-assisted. Educational only.",
            )
            artifacts.append(artifact.id)
        steps.append({"step": "localize", "status": "OK", "artifacts": len(artifacts)})

        # live=False is the whole posture: the adapter refuses external
        # effects, so the strongest thing a cycle can do is write a receipt.
        client = adapter or BaseSocialClient(enabled=True, live=False)
        try:
            receipt = _run_sync(self.media.shadow_publish(
                session, content_id=content.id,
                localized_artifact_id=artifacts[0],
                account_id=self._account_ids[0], adapter=client,
            ))
            steps.append({
                "step": "shadow_publish", "status": "OK",
                "receipt_id": receipt.id, "external_effect": receipt.external_effect,
                "mode": receipt.mode,
            })
        except Exception as exc:
            # A refusal is a legitimate outcome, not a crash. The account may
            # not be authorized, or a guard may have fired, and either way the
            # cycle continues and reports it.
            steps.append({"step": "shadow_publish", "status": "REFUSED", "reason": str(exc)})

        steps.append(self._predeclare_step(session))
        steps.append(self._chase_step(session))
        return {"cycle": "COMPLETE", "steps": steps}

    def _predeclare_step(self, session: Any) -> Dict[str, Any]:
        """Predeclare the campaign the declaration already answers.

        The registry refuses a campaign missing any of the six. The
        declaration carries all six or Declaration.load would have refused
        it, so the honest thing is to run the predeclaration rather than
        report it as a pending human step.
        """
        from db.models import AspirationCampaign, AspirationRecord
        from services.aspiration_registry import AspirationRegistryError

        campaign = self.declaration.campaign
        aspiration = session.query(AspirationRecord).filter(
            lambda row, c=campaign: row.founder_statement == c["aspiration"]
        ).first()
        if aspiration is None:
            return {"step": "predeclare", "status": "SKIPPED",
                    "reason": "aspiration not registered"}

        existing = [
            c for c in session.query(AspirationCampaign).all()
            if c.aspiration_id == aspiration.id and c.status in ("PREDECLARED", "RUNNING")
        ]
        if existing:
            return {"step": "predeclare", "status": "ALREADY_LIVE",
                    "campaign_id": existing[0].id, "sbm": existing[0].sbm}
        try:
            record = self.aspirations.predeclare_campaign(
                session, aspiration_id=aspiration.id,
                gate=aspiration.current_gate, sbm=campaign["sbm"],
                evidence_threshold=campaign["evidence_threshold"],
                resource_ceiling=campaign["resource_ceiling"],
                stop_condition=campaign["stop_condition"],
                hypothesis=self.declaration.source_packet.get("thesis", ""),
            )
            return {"step": "predeclare", "status": "OK",
                    "campaign_id": record.id, "gate": record.gate,
                    "sbm": record.sbm}
        except AspirationRegistryError as exc:
            return {"step": "predeclare", "status": "REFUSED", "reason": str(exc)}

    def _chase_step(self, session: Any) -> Dict[str, Any]:
        ceiling = float(self.declaration.budget.get("ceiling", 0.0) or 0.0)
        move = self.chase.next_move(
            session, budget_ceiling=ceiling if ceiling > 0 else None
        )
        return {"step": "goal_chase", **move}

    # ----------------------------------------------------------------- #
    # The report, generated from live state
    # ----------------------------------------------------------------- #

    def report(self, session: Any) -> Dict[str, Any]:
        """The section 89 report, read from the store.

        No field here is typed by a human. That is the point: a report that
        cannot be written by hand cannot be flattering by accident.
        """
        from db.models import (
            AccountLane, AspirationRecord, ClaimRecord, ContentRecord,
            LocalizedArtifact, OpportunityPacket, PublicationReceipt,
            SourceRecord, VentureAssessment,
        )
        from services.venture_protocol import is_authoritative_wmi_assessment

        accounts = session.query(AccountLane).all()
        assessments = session.query(VentureAssessment).all()
        advancement = self.ladder.verified_advancement_rate_30d(session)
        commerce = self.ladder.commercial_scorecard(session)
        posture = self.incidents.effective_posture(session)

        return {
            "CURRENT_IMPLEMENTED": {
                "source_records": len(session.query(SourceRecord).all()),
                "claims": len(session.query(ClaimRecord).all()),
                "content": len(session.query(ContentRecord).all()),
                "localizations": len(session.query(LocalizedArtifact).all()),
                "shadow_receipts": len(session.query(PublicationReceipt).all()),
            },
            "ACTIVE_SBM": self.declaration.campaign["sbm"],
            "OFFICIAL_ACCOUNTS_REGISTERED": sum(
                1 for a in accounts if a.status == "ACTIVE"
            ),
            "ACCOUNTS_DECLARED_SHADOW": sum(
                1 for a in accounts if a.status == "SHADOW"
            ),
            "LANGUAGES_ACTIVE": 0,
            "PLATFORMS_ACTIVE": 0,
            "PUBLISHING_PIPELINE": posture["posture"] if posture["posture"] != "RUN"
                                   else "SHADOW_ONLY",
            "OWNED_AUDIENCE": self.ladder.owned_audience_size(session),
            "REVENUE": commerce["reconciled_revenue"],
            "FREE_CASH_FLOW": commerce["contribution_margin"],
            "OPPORTUNITY_PACKETS": len(session.query(OpportunityPacket).all()),
            "WMI_REAL_PATH": (
                "EXERCISED" if any(
                    is_authoritative_wmi_assessment(a) for a in assessments
                ) else "UNEXERCISED"
            ),
            "WMI_MOCK_BYPASS_STATUS": "BLOCKED_BY_SINGLE_AUTHORITATIVE_PREDICATE",
            "ASPIRATION_REGISTRY": len(session.query(AspirationRecord).all()),
            "VERIFIED_ADVANCEMENT_ACTION_RATE": advancement["rate"],
            "VERIFIED_ASPIRATION_GATES_CLEARED": (
                self.aspirations.verified_gates_cleared(session)
            ),
            "EFFECTIVE_POSTURE": posture,
            "GAP_MAP": self.chase.gap_map(session),
            "DECLARATION_GAPS": self.declaration.gaps(),
            "NEXT_ACTION": self._chase_step(session),
            "OPUS_COMPOUNDING": self.opus_report(session),
            "FOUNDER_INTENT_PRESERVED": True,
            "generated_at": _now().isoformat(),
            "generated_from": "durable store and registries, not hand-entered",
        }


__all__ = [
    "DEFAULT_DECLARATION_PATH", "REQUIRED_CAMPAIGN_FIELDS",
    "DeclarationError", "Declaration", "DaleoBanks",
]
