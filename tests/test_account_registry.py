"""Canonical Account Registry invariants and lifecycle controls."""

from datetime import datetime, UTC

import pytest

from db.models import AccountLane
from db.session import get_db_session, init_db
from services.account_registry import AccountRegistry, AccountRegistryError
from services.ledger import DecisionLedger


@pytest.fixture
def registry(tmp_path):
    init_db()
    return AccountRegistry(ledger=DecisionLedger(path=str(tmp_path / "ledger.jsonl")))


def test_shadow_account_is_declared_not_inferred_and_redacts_credential_ref(registry):
    with get_db_session() as session:
        lane = registry.register(
            session,
            name="UNIIMENTE flagship shadow",
            platform="x",
            identity_type="brand_account",
            purpose="Flagship public rabbit-hole rehearsal",
            language="en",
            handle="",
            credential_ref="env:X_ACCESS_TOKEN",
            status="SHADOW",
            current_authorization="SHADOW_ONLY",
        )

    public = registry.public_record(lane)
    assert public["handle"] == ""  # no public-search inference
    assert public["credential_configured"] is True
    assert "credential_ref" not in public
    assert lane.active is False


@pytest.mark.parametrize(
    "identity_type",
    ["fake_person", "impersonation", "ban_evasion_account"],
)
def test_registry_rejects_inauthentic_identity_types(registry, identity_type):
    with get_db_session() as session, pytest.raises(ValueError):
        registry.register(
            session,
            name="fake lane",
            platform="x",
            identity_type=identity_type,
        )


def test_registry_never_stores_secret_shaped_material(registry):
    with get_db_session() as session, pytest.raises(AccountRegistryError, match="never store"):
        registry.register(
            session,
            name="unsafe",
            platform="x",
            credential_ref="token=actual-secret-material",
        )


def test_active_account_requires_verified_authority_envelope(registry):
    with get_db_session() as session, pytest.raises(
        AccountRegistryError, match="missing verified fields"
    ):
        registry.register(
            session,
            name="premature live account",
            platform="x",
            status="ACTIVE",
            current_authorization="STANDING_MANDATE",
        )


def test_explicit_transition_to_active_and_external_prerequisite(registry):
    with get_db_session() as session:
        lane = registry.register(
            session,
            name="declared X account",
            platform="x",
            handle="@declared_by_founder",
            legal_principal="Alfonso Lopez / DALEOBANKS",
            credential_ref="vault:daleobanks/x/main",
            posting_limits={"max_per_day": 4},
            status="SHADOW",
        )
        lane.current_authorization = "APPROVAL_REQUIRED"
        lane = registry.transition(
            session,
            lane.id,
            "ACTIVE",
            actor="alfonso",
            authorization_ref="founder-mandate:DB-AUTH-001",
            last_verified=datetime.now(UTC),
        )
        decision = registry.evaluate_authority(
            session, lane.id, platform="x", external_effect=True
        )

    assert lane.active is True
    assert decision["allowed"] is True
    assert decision["requires_capability_grant"] is True
    assert "still required" in decision["reason"]


def test_active_account_can_always_fail_closed_to_frozen(registry):
    with get_db_session() as session:
        lane = registry.register(
            session,
            name="declared X account",
            platform="x",
            handle="@declared_by_founder",
            legal_principal="Alfonso Lopez / DALEOBANKS",
            credential_ref="vault:daleobanks/x/main",
            posting_limits={"max_per_day": 4},
            status="SHADOW",
        )
        lane.current_authorization = "STANDING_MANDATE"
        registry.transition(
            session,
            lane.id,
            "ACTIVE",
            actor="alfonso",
            authorization_ref="founder-mandate:DB-AUTH-001",
            last_verified=datetime.now(UTC),
        )
        frozen = registry.transition(session, lane.id, "FROZEN", actor="safety")
    assert frozen.status == "FROZEN"
    assert frozen.current_authorization == "NONE"
    assert frozen.active is False


def test_frozen_account_blocks_even_shadow_actions(registry):
    with get_db_session() as session:
        lane = registry.register(session, name="shadow", platform="x")
        registry.transition(session, lane.id, "FROZEN", actor="admin")
        decision = registry.evaluate_authority(
            session, lane.id, platform="x", external_effect=False
        )
    assert decision["allowed"] is False


def test_duplicate_platform_handle_is_rejected(registry):
    with get_db_session() as session:
        registry.register(
            session, name="first", platform="x", handle="@official",
        )
        with pytest.raises(AccountRegistryError, match="already registered"):
            registry.register(
                session, name="second", platform="x", handle="@OFFICIAL",
            )


def test_parent_identity_is_fixed_to_daleobanks(registry):
    with get_db_session() as session, pytest.raises(
        AccountRegistryError, match="DALEOBANKS"
    ):
        registry.register(
            session,
            name="parallel identity",
            platform="x",
            parent_identity="SELF_SOVEREIGN_AGENT",
        )


def test_persistence_round_trip_supports_new_registry_fields(registry, tmp_path, monkeypatch):
    snapshot = tmp_path / "store.jsonl"
    monkeypatch.setenv("PERSIST_STORE", "true")
    monkeypatch.setenv("DB_SNAPSHOT_PATH", str(snapshot))
    init_db()
    with get_db_session() as session:
        lane = registry.register(
            session,
            name="persistent shadow",
            platform="youtube",
            region="US",
            topic_lane="financial_independence",
        )
        lane_id = lane.id
    init_db()
    with get_db_session() as session:
        restored = session.query(AccountLane).filter(lambda row: row.id == lane_id).first()
    assert restored is not None
    assert restored.status == "SHADOW"
    assert restored.parent_identity == "DALEOBANKS"
