"""Evidence-bound, multilingual media operating substrate.

This module closes one controlled institutional loop without inventing a
second generator, ledger, approval queue, or publish path:

source -> claim -> knowledge record -> localization -> shadow adapter
       -> publication receipt -> predeclared experiment state

Draft generation remains owned by ``IdeaRefinery``.  External publication
remains owned by the existing capability and social gates.  Phase 0 only
permits shadow receipts, so this service cannot make a live platform call.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlparse

from db.models import (
    ClaimRecord,
    ContentExperiment,
    ContentRecord,
    LocalizedArtifact,
    PublicationReceipt,
    SourceRecord,
)
from services.account_registry import AccountRegistry
from services.idea_refinery import EDUCATIONAL_DISCLOSURE, check_educational
from services.ledger import DecisionLedger, get_ledger
from services.raw_vault import RawVault, get_raw_vault
from services.social_base import BaseSocialClient


SOURCE_CLASSES = frozenset({
    "primary_government", "peer_reviewed_research", "company_filing",
    "standards_body", "academic_paper", "official_announcement",
    "credible_news", "specialist_media", "expert_commentary",
    "public_discussion", "community_signal", "aggregator",
})
EVIDENCE_CLASSES = frozenset({
    "FACT", "SUPPORTED_INFERENCE", "PROPOSAL", "EXPERIMENT", "ASPIRATION",
    "SPECULATION",
})
EVIDENCE_STATUSES = frozenset({
    "DISCOVERED", "CHECKED", "SUPPORTED", "CONTRADICTED", "RETRACTED",
})
CONTENT_TYPES = frozenset({
    "explainer", "short_video", "long_video", "thread", "article",
    "newsletter", "daily_high_signal_news", "debate", "community_challenge",
    "commercial_education", "aspiration_campaign",
})
RISK_CLASSES = frozenset({"tier1", "tier2", "tier3", "tier4"})

DAILY_NEWS_SECTIONS = (
    "what_happened",
    "why_it_matters",
    "what_most_people_are_missing",
    "who_benefits",
    "who_is_exposed",
    "what_changes",
    "what_to_watch_next",
)

_FINANCE_TERMS = (
    "invest", "money", "financial", "finance", "fire", "retirement",
    "wealth", "credit", "tax", "insurance",
)
_HIGH_RISK_TERMS = {
    "medical": ("diagnose", "treatment", "cure", "medical advice"),
    "legal": ("legal advice", "immigration advice", "you should sue"),
    "accusation": ("criminal", "fraudster", "stole", "corrupt person"),
    "political_persuasion": ("vote for", "vote against"),
}
_HUMILIATION_TERMS = (
    "poor people are stupid", "immigrants are stupid", "idiots deserve",
    "only losers", "weak people deserve",
)


class MediaOperatingSystemError(ValueError):
    """A media object failed a provenance, identity, or authority invariant."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _material_facts_hash(claim_ids: Iterable[str], source_ids: Iterable[str]) -> str:
    material = "claims:" + "|".join(sorted(set(claim_ids)))
    material += "\nsources:" + "|".join(sorted(set(source_ids)))
    return _sha256(material)


def classify_risk(*texts: str) -> Dict[str, Any]:
    """Deterministic first-pass classifier; specialist review may tighten it."""
    combined = " ".join(texts).lower()
    categories = [
        name for name, terms in _HIGH_RISK_TERMS.items()
        if any(term in combined for term in terms)
    ]
    if any(term in combined for term in _FINANCE_TERMS):
        categories.append("financial_education")
    if categories:
        return {"risk_class": "tier3", "categories": sorted(set(categories))}
    return {"risk_class": "tier1", "categories": []}


class MediaOperatingSystem:
    """Build and shadow-test canonical media artifacts."""

    def __init__(
        self,
        *,
        ledger: Optional[DecisionLedger] = None,
        vault: Optional[RawVault] = None,
        accounts: Optional[AccountRegistry] = None,
    ) -> None:
        self._ledger = ledger
        self._vault = vault
        self.accounts = accounts or AccountRegistry(ledger=ledger)

    @property
    def ledger(self) -> DecisionLedger:
        return self._ledger or get_ledger()

    @property
    def vault(self) -> RawVault:
        return self._vault or get_raw_vault()

    # ------------------------------------------------------------------ #
    # Source and claim ledger
    # ------------------------------------------------------------------ #
    def ingest_source(
        self,
        session: Any,
        *,
        title: str,
        url: str,
        source_class: str,
        topic: str,
        source_text: str,
        publisher: str = "",
        discovery_source: str = "direct",
        primary_source_url: str = "",
        published_at: Optional[datetime] = None,
        evidence_status: str = "DISCOVERED",
        contradiction_search_status: str = "NOT_RUN",
        risk_class: str = "tier1",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SourceRecord:
        self._validate_url(url)
        source_class = source_class.lower()
        evidence_status = evidence_status.upper()
        if source_class not in SOURCE_CLASSES:
            raise MediaOperatingSystemError(
                f"source_class must be one of {sorted(SOURCE_CLASSES)}"
            )
        if evidence_status not in EVIDENCE_STATUSES:
            raise MediaOperatingSystemError(
                f"evidence_status must be one of {sorted(EVIDENCE_STATUSES)}"
            )
        if risk_class not in RISK_CLASSES:
            raise MediaOperatingSystemError(
                f"risk_class must be one of {sorted(RISK_CLASSES)}"
            )
        if not title.strip() or not topic.strip() or not source_text.strip():
            raise MediaOperatingSystemError("title, topic, and source_text are required")
        aggregator_discovery = (
            source_class == "aggregator"
            or discovery_source.strip().lower() in {"feedly", "aggregator"}
        )
        if aggregator_discovery and evidence_status in {"CHECKED", "SUPPORTED"}:
            if not primary_source_url:
                raise MediaOperatingSystemError(
                    "aggregator discovery needs primary_source_url before it can support a claim"
                )
            self._validate_url(primary_source_url)

        vault_id = self.vault.deposit(
            source=discovery_source or source_class,
            text=source_text,
            raw_ref=url,
            meta={"title": title, "topic": topic, "source_class": source_class},
        )
        if not vault_id:
            raise MediaOperatingSystemError("raw source could not be preserved")
        record = SourceRecord(
            title=title.strip(),
            url=url.strip(),
            source_class=source_class,
            discovery_source=discovery_source.strip() or "direct",
            primary_source_url=primary_source_url.strip(),
            topic=topic.strip(),
            publisher=publisher.strip(),
            published_at=published_at,
            content_hash=_sha256(source_text),
            evidence_status=evidence_status,
            contradiction_search_status=contradiction_search_status.upper(),
            risk_class=risk_class,
            raw_vault_ref=vault_id,
            metadata=dict(metadata or {}),
        )
        session.add(record)
        session.commit()
        self.ledger.record("source_ingested", {
            "source_id": record.id,
            "source_class": record.source_class,
            "discovery_source": record.discovery_source,
            "evidence_status": record.evidence_status,
            "content_hash": record.content_hash,
        })
        return record

    def create_claim(
        self,
        session: Any,
        *,
        statement: str,
        source_ids: Sequence[str],
        evidence_class: str,
        evidence_status: str = "SUPPORTED",
        confidence: float,
        contradiction_notes: Optional[Sequence[str]] = None,
        uncertainty: str = "",
        risk_class: Optional[str] = None,
    ) -> ClaimRecord:
        evidence_class = evidence_class.upper()
        evidence_status = evidence_status.upper()
        if evidence_class not in EVIDENCE_CLASSES:
            raise MediaOperatingSystemError(
                f"evidence_class must be one of {sorted(EVIDENCE_CLASSES)}"
            )
        if evidence_status not in EVIDENCE_STATUSES:
            raise MediaOperatingSystemError(
                f"evidence_status must be one of {sorted(EVIDENCE_STATUSES)}"
            )
        if not 0.0 <= float(confidence) <= 1.0:
            raise MediaOperatingSystemError("confidence must be within [0, 1]")
        if not statement.strip():
            raise MediaOperatingSystemError("claim statement is required")
        sources = self._sources(session, source_ids)
        if evidence_class in {"FACT", "SUPPORTED_INFERENCE"} and not sources:
            raise MediaOperatingSystemError("factual claims require registered sources")
        detected = classify_risk(statement)
        resolved_risk = risk_class or detected["risk_class"]
        if resolved_risk not in RISK_CLASSES:
            raise MediaOperatingSystemError(
                f"risk_class must be one of {sorted(RISK_CLASSES)}"
            )
        if resolved_risk in {"tier3", "tier4"} and any(
            source.evidence_status not in {"CHECKED", "SUPPORTED"} for source in sources
        ):
            raise MediaOperatingSystemError(
                "high-risk factual claims require CHECKED or SUPPORTED sources"
            )
        record = ClaimRecord(
            statement=statement.strip(),
            source_ids=list(dict.fromkeys(source_ids)),
            evidence_class=evidence_class,
            evidence_status=evidence_status,
            confidence=float(confidence),
            contradiction_notes=list(contradiction_notes or []),
            uncertainty=uncertainty.strip(),
            risk_class=resolved_risk,
        )
        session.add(record)
        session.commit()
        self.ledger.record("claim_created", {
            "claim_id": record.id,
            "source_ids": record.source_ids,
            "evidence_class": record.evidence_class,
            "evidence_status": record.evidence_status,
            "confidence": record.confidence,
            "risk_class": record.risk_class,
        })
        return record

    # ------------------------------------------------------------------ #
    # Content knowledge and localization
    # ------------------------------------------------------------------ #
    def create_content(
        self,
        session: Any,
        *,
        content_type: str,
        topic: str,
        thesis: str,
        claim_ids: Sequence[str],
        source_ids: Sequence[str],
        counterargument: str,
        daleobanks_position: str,
        uncertainty: str,
        audiences: Sequence[str],
        formats: Sequence[str],
        funnel_destination: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContentRecord:
        if content_type not in CONTENT_TYPES:
            raise MediaOperatingSystemError(
                f"content_type must be one of {sorted(CONTENT_TYPES)}"
            )
        claims = self._claims(session, claim_ids)
        sources = self._sources(session, source_ids)
        referenced_sources = {source_id for claim in claims for source_id in claim.source_ids}
        if not claims or not sources:
            raise MediaOperatingSystemError("content requires claims and sources")
        if not referenced_sources.issubset(set(source_ids)):
            raise MediaOperatingSystemError(
                "content source_ids must include every source referenced by its claims"
            )
        if not counterargument.strip():
            raise MediaOperatingSystemError("strongest counterargument is required")
        if not daleobanks_position.strip() or not uncertainty.strip():
            raise MediaOperatingSystemError(
                "DALEOBANKS position and uncertainty boundary are required"
            )
        combined = " ".join((thesis, counterargument, daleobanks_position))
        if any(term in combined.lower() for term in _HUMILIATION_TERMS):
            raise MediaOperatingSystemError(
                "brand genome violation: ruthless toward the problem, humane toward the person"
            )
        risk_order = {"tier1": 1, "tier2": 2, "tier3": 3, "tier4": 4}
        risk_class = max((claim.risk_class for claim in claims), key=risk_order.get)
        evidence_status = (
            "SUPPORTED" if all(claim.evidence_status == "SUPPORTED" for claim in claims)
            else "CHECKED"
        )
        record = ContentRecord(
            content_type=content_type,
            topic=topic.strip(),
            thesis=thesis.strip(),
            claim_ids=list(dict.fromkeys(claim_ids)),
            source_ids=list(dict.fromkeys(source_ids)),
            counterargument=counterargument.strip(),
            daleobanks_position=daleobanks_position.strip(),
            uncertainty=uncertainty.strip(),
            evidence_status=evidence_status,
            risk_class=risk_class,
            audiences=list(dict.fromkeys(audiences)),
            formats=list(dict.fromkeys(formats)),
            funnel_destination=funnel_destination.strip(),
            metadata=dict(metadata or {}),
        )
        session.add(record)
        session.commit()
        self.ledger.record("content_record_created", {
            "content_id": record.id,
            "content_type": record.content_type,
            "claim_ids": record.claim_ids,
            "source_ids": record.source_ids,
            "risk_class": record.risk_class,
        })
        return record

    def localize(
        self,
        session: Any,
        *,
        content_id: str,
        language: str,
        region: str,
        platform: str,
        text: str,
        claim_ids: Sequence[str],
        source_ids: Sequence[str],
        disclosure: str = "",
        cultural_notes: str = "",
    ) -> LocalizedArtifact:
        content = self._content(session, content_id)
        if set(claim_ids) != set(content.claim_ids) or set(source_ids) != set(content.source_ids):
            raise MediaOperatingSystemError(
                "localization changed the canonical claim/source set"
            )
        if not text.strip() or not language.strip() or not platform.strip():
            raise MediaOperatingSystemError("localized text, language, and platform are required")
        claims = self._claims(session, claim_ids)
        finance = any(
            category == "financial_education"
            for claim in claims
            for category in classify_risk(claim.statement)["categories"]
        )
        if finance:
            violations = check_educational(text)
            if violations:
                raise MediaOperatingSystemError(
                    f"finance localization violates education guardrail: {violations}"
                )
            if EDUCATIONAL_DISCLOSURE.lower() not in disclosure.lower() and (
                EDUCATIONAL_DISCLOSURE.lower() not in text.lower()
            ):
                raise MediaOperatingSystemError(
                    "financial education localization requires the canonical disclosure"
                )
        artifact = LocalizedArtifact(
            content_id=content.id,
            language=language.strip().lower(),
            region=region.strip() or "global",
            platform=platform.strip().lower(),
            text=text.strip(),
            claim_ids=list(content.claim_ids),
            source_ids=list(content.source_ids),
            material_facts_hash=_material_facts_hash(claim_ids, source_ids),
            disclosure=disclosure.strip(),
            cultural_notes=cultural_notes.strip(),
        )
        session.add(artifact)
        content.localization_ids.append(artifact.id)
        session.commit()
        self.ledger.record("content_localized", {
            "content_id": content.id,
            "artifact_id": artifact.id,
            "language": artifact.language,
            "region": artifact.region,
            "platform": artifact.platform,
            "material_facts_hash": artifact.material_facts_hash,
        })
        return artifact

    def create_daily_news(
        self,
        session: Any,
        *,
        topic: str,
        sections: Mapping[str, str],
        claim_ids: Sequence[str],
        source_ids: Sequence[str],
        counterargument: str,
        uncertainty: str,
        audiences: Sequence[str],
    ) -> ContentRecord:
        missing = [name for name in DAILY_NEWS_SECTIONS if not sections.get(name, "").strip()]
        if missing:
            raise MediaOperatingSystemError(
                f"daily news edition is missing sections: {', '.join(missing)}"
            )
        thesis = sections["what_happened"].strip()
        position = "\n".join(
            f"{name.replace('_', ' ').upper()}: {sections[name].strip()}"
            for name in DAILY_NEWS_SECTIONS
        )
        return self.create_content(
            session,
            content_type="daily_high_signal_news",
            topic=topic,
            thesis=thesis,
            claim_ids=claim_ids,
            source_ids=source_ids,
            counterargument=counterargument,
            daleobanks_position=position,
            uncertainty=uncertainty,
            audiences=audiences,
            formats=["newsletter", "short_video", "thread"],
            metadata={
                "editorial_schedule_local_time": "20:00",
                "reporting_opinion_separated": True,
                "sections": list(DAILY_NEWS_SECTIONS),
            },
        )

    # ------------------------------------------------------------------ #
    # Experiment and shadow receipt
    # ------------------------------------------------------------------ #
    def predeclare_experiment(
        self,
        session: Any,
        *,
        content_id: str,
        hypothesis: str,
        audience: str,
        channel: str,
        expected_outcome: str,
        metric: str,
        duration: str,
        baseline: str,
        budget: float = 0.0,
        currency: str = "USD",
    ) -> ContentExperiment:
        self._content(session, content_id)
        if not all(value.strip() for value in (
            hypothesis, audience, channel, expected_outcome, metric, duration, baseline
        )):
            raise MediaOperatingSystemError("experiment fields must be predeclared")
        if budget < 0:
            raise MediaOperatingSystemError("experiment budget cannot be negative")
        experiment = ContentExperiment(
            content_id=content_id,
            hypothesis=hypothesis.strip(),
            audience=audience.strip(),
            channel=channel.strip(),
            expected_outcome=expected_outcome.strip(),
            metric=metric.strip(),
            budget=float(budget),
            currency=currency.strip().upper(),
            duration=duration.strip(),
            baseline=baseline.strip(),
        )
        session.add(experiment)
        session.commit()
        self.ledger.record("content_experiment_predeclared", {
            "experiment_id": experiment.id,
            "content_id": content_id,
            "metric": experiment.metric,
            "budget": experiment.budget,
            "status": experiment.status,
            "evidence_class": experiment.evidence_class,
        })
        return experiment

    async def shadow_publish(
        self,
        session: Any,
        *,
        content_id: str,
        localized_artifact_id: str,
        account_id: str,
        adapter: BaseSocialClient,
        authority_ref: str = "PHASE0_SHADOW_ONLY",
    ) -> PublicationReceipt:
        content = self._content(session, content_id)
        artifact = session.query(LocalizedArtifact).filter(
            lambda row: row.id == localized_artifact_id
        ).first()
        if artifact is None or artifact.content_id != content.id:
            raise MediaOperatingSystemError("localized artifact does not belong to content")
        if not adapter.enabled:
            raise MediaOperatingSystemError("platform adapter is disabled")
        if adapter.live:
            raise MediaOperatingSystemError(
                "Phase 0 media loop accepts shadow adapters only (live=False)"
            )
        authority = self.accounts.evaluate_authority(
            session, account_id,
            platform=artifact.platform,
            external_effect=False,
        )
        if not authority["allowed"]:
            raise MediaOperatingSystemError(authority["reason"])
        duplicate = session.query(PublicationReceipt).filter(
            lambda receipt: receipt.localized_artifact_id == artifact.id
            and receipt.account_id == account_id
            and receipt.mode == "SHADOW"
        ).first()
        if duplicate is not None:
            raise MediaOperatingSystemError("duplicate shadow publication refused")

        idempotency_key = _sha256(f"shadow:{content.id}:{artifact.id}:{account_id}")
        result = await adapter.publish(
            content=artifact.text,
            kind="post",
            metadata={
                "content_id": content.id,
                "localized_artifact_id": artifact.id,
                "account_id": account_id,
                "idempotency_key": idempotency_key,
                "source_ids": artifact.source_ids,
                "claim_ids": artifact.claim_ids,
                "authority_ref": authority_ref,
            },
        )
        if not result.dry_run:
            self.ledger.record("constitutional_violation", {
                "reason": "shadow adapter returned a live result",
                "content_id": content.id,
                "account_id": account_id,
                "post_id": result.post_id,
            })
            raise MediaOperatingSystemError("shadow adapter produced an external effect")

        receipt = PublicationReceipt(
            content_id=content.id,
            localized_artifact_id=artifact.id,
            account_id=account_id,
            platform=result.platform,
            post_id=result.post_id,
            content_hash=_sha256(artifact.text),
            source_ids=list(artifact.source_ids),
            claim_ids=list(artifact.claim_ids),
            authority_ref=authority_ref,
            idempotency_key=idempotency_key,
        )
        session.add(receipt)
        content.publication_receipt_ids.append(receipt.id)
        content.status = "SHADOW"
        session.commit()
        self.ledger.record("content_shadowed", {
            "receipt_id": receipt.id,
            "content_id": content.id,
            "artifact_id": artifact.id,
            "account_id": account_id,
            "platform": receipt.platform,
            "external_effect": False,
            "content_hash": receipt.content_hash,
        })
        return receipt

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MediaOperatingSystemError("source URL must be an absolute http(s) URL")

    @staticmethod
    def _sources(session: Any, source_ids: Sequence[str]) -> list[SourceRecord]:
        unique = list(dict.fromkeys(source_ids))
        rows = session.query(SourceRecord).filter(lambda row: row.id in unique).all()
        if len(rows) != len(unique):
            raise MediaOperatingSystemError("one or more source_ids are not registered")
        return rows

    @staticmethod
    def _claims(session: Any, claim_ids: Sequence[str]) -> list[ClaimRecord]:
        unique = list(dict.fromkeys(claim_ids))
        rows = session.query(ClaimRecord).filter(lambda row: row.id in unique).all()
        if len(rows) != len(unique):
            raise MediaOperatingSystemError("one or more claim_ids are not registered")
        return rows

    @staticmethod
    def _content(session: Any, content_id: str) -> ContentRecord:
        record = session.query(ContentRecord).filter(lambda row: row.id == content_id).first()
        if record is None:
            raise MediaOperatingSystemError("content record is not registered")
        return record


__all__ = [
    "CONTENT_TYPES", "DAILY_NEWS_SECTIONS", "EVIDENCE_CLASSES",
    "EVIDENCE_STATUSES", "RISK_CLASSES", "SOURCE_CLASSES",
    "MediaOperatingSystem", "MediaOperatingSystemError", "classify_risk",
]
