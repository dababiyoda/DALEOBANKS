"""Executable source-to-shadow media loop and its negative controls."""

import pytest

from db.models import ContentRecord, PublicationReceipt
from db.session import get_db_session, init_db
from services.account_registry import AccountRegistry
from services.idea_refinery import EDUCATIONAL_DISCLOSURE
from services.ledger import (
    DecisionLedger,
    KillSwitch,
    RateGovernor,
    reset_shared_instances,
    set_shared_instances,
)
from services.media_operating_system import (
    DAILY_NEWS_SECTIONS,
    MediaOperatingSystem,
    MediaOperatingSystemError,
)
from services.raw_vault import RawVault
from services.social_base import BaseSocialClient, SocialPostResult


class RecordingAdapter(BaseSocialClient):
    platform = "x"

    def __init__(self, *, live=False, enabled=True):
        super().__init__(enabled=enabled, live=live)
        self.impl_calls = 0

    async def _publish_impl(
        self, *, content, kind="post", in_reply_to=None, quote_to=None,
        intensity=1, metadata=None,
    ):
        self.impl_calls += 1
        return SocialPostResult(
            platform=self.platform,
            post_id="live-result-that-must-never-happen-in-shadow",
            dry_run=False,
            meta=metadata,
        )


@pytest.fixture
def system(tmp_path):
    init_db()
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(
        ledger=ledger,
        kill_switch=KillSwitch(ledger=ledger),
        governor=RateGovernor(max_actions=10),
    )
    instance = MediaOperatingSystem(
        ledger=ledger,
        vault=RawVault(path=str(tmp_path / "raw.jsonl")),
        accounts=AccountRegistry(ledger=ledger),
    )
    yield instance
    reset_shared_instances()


def _knowledge_record(system, session):
    source = system.ingest_source(
        session,
        title="Official workforce release",
        url="https://example.gov/workforce-release",
        source_class="primary_government",
        topic="immigrant economic mobility",
        source_text="The official release reports a measurable training gap.",
        publisher="Example Labor Department",
        evidence_status="SUPPORTED",
        contradiction_search_status="RUN",
    )
    claim = system.create_claim(
        session,
        statement="The official release reports a measurable training gap.",
        source_ids=[source.id],
        evidence_class="FACT",
        confidence=0.92,
        uncertainty="The release does not establish causation.",
    )
    content = system.create_content(
        session,
        content_type="explainer",
        topic="immigrant economic mobility",
        thesis="Capability gaps can be reduced with practical training paths.",
        claim_ids=[claim.id],
        source_ids=[source.id],
        counterargument="Training alone cannot repair structural barriers.",
        daleobanks_position=(
            "Treat people with dignity while attacking the broken access system."
        ),
        uncertainty="The best intervention still needs a real participant test.",
        audiences=["immigrant builders"],
        formats=["thread", "newsletter"],
        funnel_destination="owned learning diagnostic",
    )
    return source, claim, content


async def test_complete_source_to_shadow_receipt_loop(system):
    adapter = RecordingAdapter(live=False)
    with get_db_session() as session:
        source, claim, content = _knowledge_record(system, session)
        account = system.accounts.register(
            session,
            name="UNIIMENTE flagship shadow",
            platform="x",
            identity_type="brand_account",
            language="es",
            region="US/LatAm",
            topic_lane="capability",
            status="SHADOW",
        )
        localized = system.localize(
            session,
            content_id=content.id,
            language="es",
            region="US/LatAm",
            platform="x",
            text=(
                "La fuente oficial informa una brecha de capacitación medible. "
                "La capacitación ayuda, pero no sustituye la reforma estructural."
            ),
            claim_ids=[claim.id],
            source_ids=[source.id],
            cultural_notes="Plain Spanish; no false identity mimicry.",
        )
        experiment = system.predeclare_experiment(
            session,
            content_id=content.id,
            hypothesis="A sourced Spanish explainer earns qualified saves.",
            audience="Spanish-speaking immigrant builders",
            channel="x",
            expected_outcome="Qualified owned-audience intent",
            metric="qualified diagnostic starts",
            duration="7 days after authorized publication",
            baseline="0; no authorized publication yet",
        )
        receipt = await system.shadow_publish(
            session,
            content_id=content.id,
            localized_artifact_id=localized.id,
            account_id=account.id,
            adapter=adapter,
        )

        stored = session.query(PublicationReceipt).filter(
            lambda row: row.id == receipt.id
        ).first()
        refreshed_content = session.query(ContentRecord).filter(
            lambda row: row.id == content.id
        ).first()

    assert adapter.impl_calls == 0
    assert stored.external_effect is False
    assert stored.status == "SHADOW_COMPLETED"
    assert stored.analytics_status == "NOT_APPLICABLE_SHADOW"
    assert stored.post_id.startswith("x:post/md_dry_")
    assert experiment.evidence_class == "SIMULATION"
    assert refreshed_content.status == "SHADOW"
    assert receipt.id in refreshed_content.publication_receipt_ids
    assert system.ledger.verify_chain() == (True, None)


async def test_duplicate_shadow_publication_is_refused(system):
    adapter = RecordingAdapter(live=False)
    with get_db_session() as session:
        source, claim, content = _knowledge_record(system, session)
        account = system.accounts.register(session, name="shadow", platform="x")
        artifact = system.localize(
            session,
            content_id=content.id,
            language="en",
            region="global",
            platform="x",
            text="The official release reports a measurable training gap.",
            claim_ids=[claim.id],
            source_ids=[source.id],
        )
        await system.shadow_publish(
            session,
            content_id=content.id,
            localized_artifact_id=artifact.id,
            account_id=account.id,
            adapter=adapter,
        )
        with pytest.raises(MediaOperatingSystemError, match="duplicate"):
            await system.shadow_publish(
                session,
                content_id=content.id,
                localized_artifact_id=artifact.id,
                account_id=account.id,
                adapter=adapter,
            )


def test_feedly_discovery_cannot_become_evidence_without_primary_source(system):
    with get_db_session() as session, pytest.raises(
        MediaOperatingSystemError, match="primary_source_url"
    ):
        system.ingest_source(
            session,
            title="Feedly card",
            url="https://feedly.example/item/1",
            source_class="aggregator",
            topic="AI",
            source_text="An aggregator summary.",
            discovery_source="Feedly",
            evidence_status="SUPPORTED",
        )


def test_high_risk_financial_claim_requires_checked_source_and_disclosure(system):
    with get_db_session() as session:
        discovered = system.ingest_source(
            session,
            title="Discussion",
            url="https://example.org/discussion",
            source_class="public_discussion",
            topic="investing",
            source_text="A person discussed investing.",
        )
        with pytest.raises(MediaOperatingSystemError, match="high-risk"):
            system.create_claim(
                session,
                statement="Investing fees reduce financial returns.",
                source_ids=[discovered.id],
                evidence_class="FACT",
                confidence=0.7,
            )

        checked = system.ingest_source(
            session,
            title="Regulator fee bulletin",
            url="https://example.gov/investor-fees",
            source_class="primary_government",
            topic="investing",
            source_text="The bulletin explains how fees compound over time.",
            evidence_status="SUPPORTED",
        )
        claim = system.create_claim(
            session,
            statement="Investing fees can reduce financial returns over time.",
            source_ids=[checked.id],
            evidence_class="FACT",
            confidence=0.9,
        )
        content = system.create_content(
            session,
            content_type="commercial_education",
            topic="investing fees",
            thesis="Fees deserve scrutiny.",
            claim_ids=[claim.id],
            source_ids=[checked.id],
            counterargument="Some fees pay for useful service.",
            daleobanks_position="Compare total costs and service value.",
            uncertainty="Individual suitability varies.",
            audiences=["new investors"],
            formats=["thread"],
        )
        with pytest.raises(MediaOperatingSystemError, match="disclosure"):
            system.localize(
                session,
                content_id=content.id,
                language="en",
                region="US",
                platform="x",
                text="Fees can reduce returns over time.",
                claim_ids=[claim.id],
                source_ids=[checked.id],
            )
        with pytest.raises(MediaOperatingSystemError, match="guardrail"):
            system.localize(
                session,
                content_id=content.id,
                language="en",
                region="US",
                platform="x",
                text=f"You should invest today. {EDUCATIONAL_DISCLOSURE}",
                claim_ids=[claim.id],
                source_ids=[checked.id],
            )


def test_localization_cannot_drift_material_claims(system):
    with get_db_session() as session:
        source, claim, content = _knowledge_record(system, session)
        with pytest.raises(MediaOperatingSystemError, match="claim/source set"):
            system.localize(
                session,
                content_id=content.id,
                language="pt",
                region="BR",
                platform="x",
                text="Uma localização sem a reivindicação canônica.",
                claim_ids=[],
                source_ids=[source.id],
            )


def test_daily_news_contract_preserves_8pm_product(system):
    with get_db_session() as session:
        source, claim, _ = _knowledge_record(system, session)
        sections = {name: f"Verified section: {name}." for name in DAILY_NEWS_SECTIONS}
        edition = system.create_daily_news(
            session,
            topic="important discoveries",
            sections=sections,
            claim_ids=[claim.id],
            source_ids=[source.id],
            counterargument="The development may matter less than first reported.",
            uncertainty="Impact has not yet been measured in the field.",
            audiences=["global builders"],
        )
        assert edition.content_type == "daily_high_signal_news"
        assert edition.metadata["editorial_schedule_local_time"] == "20:00"
        assert edition.metadata["reporting_opinion_separated"] is True

        sections.pop("who_is_exposed")
        with pytest.raises(MediaOperatingSystemError, match="missing sections"):
            system.create_daily_news(
                session,
                topic="important discoveries",
                sections=sections,
                claim_ids=[claim.id],
                source_ids=[source.id],
                counterargument="Counterargument.",
                uncertainty="Uncertain.",
                audiences=["builders"],
            )


async def test_shadow_loop_rejects_live_adapter_before_publish(system):
    adapter = RecordingAdapter(live=True)
    with get_db_session() as session:
        source, claim, content = _knowledge_record(system, session)
        account = system.accounts.register(session, name="shadow", platform="x")
        artifact = system.localize(
            session,
            content_id=content.id,
            language="en",
            region="global",
            platform="x",
            text="The official release reports a measurable training gap.",
            claim_ids=[claim.id],
            source_ids=[source.id],
        )
        with pytest.raises(MediaOperatingSystemError, match="live=False"):
            await system.shadow_publish(
                session,
                content_id=content.id,
                localized_artifact_id=artifact.id,
                account_id=account.id,
                adapter=adapter,
            )
    assert adapter.impl_calls == 0


def test_brand_genome_blocks_humiliation(system):
    with get_db_session() as session:
        source, claim, _ = _knowledge_record(system, session)
        with pytest.raises(MediaOperatingSystemError, match="brand genome"):
            system.create_content(
                session,
                content_type="explainer",
                topic="bad framing",
                thesis="Poor people are stupid and only need discipline.",
                claim_ids=[claim.id],
                source_ids=[source.id],
                counterargument="Systems matter.",
                daleobanks_position="Only losers fail.",
                uncertainty="None.",
                audiences=["general"],
                formats=["thread"],
            )
