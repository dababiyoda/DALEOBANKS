"""Portability is only real if it was written down before it was needed.

By the time a vendor leaves, the thing that knew its bounds is the thing that
left. Every guard here refuses an incompletely declared dependency going
live, and every refusal is paired with the complete version passing.
"""

import pytest

from db.session import get_db_session, init_db
from services.dependency_registry import (
    ALLOWED_CREDENTIAL_PREFIXES,
    KINDS,
    CredentialLeakError,
    DependencyError,
    DependencyRegistry,
    missing_live_requirements,
    validate_credential_reference,
)
from services.ledger import DecisionLedger


@pytest.fixture
def registry(tmp_path):
    init_db()
    return DependencyRegistry(ledger=DecisionLedger(path=str(tmp_path / "l.jsonl")))


def _complete_platform(**over):
    payload = dict(
        role="publish short-form to one lane", authorized_capabilities=["post"],
        permitted_content_classes=["explainer"], posting_limit_per_day=5,
        rate_limit_per_hour=2, risk_class="tier2", credential_owner="Alfonso Lopez",
        credential_reference="vault:x/main", evidence_requirements=["receipt"],
        rollback_mechanism="delete within 15 minutes", freeze_mechanism="kill switch",
    )
    payload.update(over)
    return payload


# ------------------------------------------------------------------ #
# Credentials
# ------------------------------------------------------------------ #

def test_raw_credential_material_is_refused():
    with pytest.raises(CredentialLeakError, match="never the secret"):
        validate_credential_reference("sk-live-abc123")


def test_references_to_a_secret_store_are_accepted():
    for prefix in ALLOWED_CREDENTIAL_PREFIXES:
        assert validate_credential_reference(f"{prefix}some/path")


def test_empty_reference_is_allowed():
    """Negative control: many dependencies need no credential at all."""
    assert validate_credential_reference("") == ""


def test_declaring_with_a_raw_key_is_refused(registry):
    with get_db_session() as session:
        with pytest.raises(CredentialLeakError):
            registry.declare(session, kind="platform_adapter", name="x",
                             credential_reference="ghp_realtokenvalue")


# ------------------------------------------------------------------ #
# Nothing half-declared goes live
# ------------------------------------------------------------------ #

def test_declaring_is_not_activating(registry):
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="tiktok")
    assert record.status == "NOT_CONFIGURED"


def test_platform_adapter_cannot_go_live_incompletely(registry):
    """The failure this prevents: the code works, someone turns it on, and the
    rate limit nobody wrote down becomes the incident."""
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="tiktok",
                                  **_complete_platform(rate_limit_per_hour=None))
        with pytest.raises(DependencyError, match="rate_limit_per_hour"):
            registry.activate(session, dependency_id=record.id)


def test_fully_declared_platform_adapter_activates(registry):
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="x",
                                  **_complete_platform())
        activated = registry.activate(session, dependency_id=record.id)
    assert activated.status == "ACTIVE"
    assert missing_live_requirements(activated) == []


def test_automation_without_reversibility_cannot_run(registry):
    """An automation nobody can see or stop is not automation."""
    with get_db_session() as session:
        record = registry.declare(
            session, kind="automation", name="nightly repurposer",
            role="repurpose", version="1.0", owner="ops",
            documentation_ref="docs/x.md", rollback_mechanism="disable flag",
            reversible=False, observable=True,
        )
        with pytest.raises(DependencyError, match="reversible"):
            registry.activate(session, dependency_id=record.id)


def test_model_provider_without_a_fallback_cannot_go_live(registry):
    """Replacing a model means knowing what runs instead."""
    with get_db_session() as session:
        record = registry.declare(
            session, kind="model_provider", name="primary planner",
            role="planning", version="1", owner="ops",
            failure_modes=["refusal", "timeout"], cost_note="per 1k tokens",
            latency_note="p95 3s",
        )
        with pytest.raises(DependencyError, match="fallback_dependency_id"):
            registry.activate(session, dependency_id=record.id)


def test_revoked_dependency_cannot_be_reactivated(registry):
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="x",
                                  **_complete_platform())
        registry.activate(session, dependency_id=record.id)
        registry.revoke(session, dependency_id=record.id, reason="terms changed")
        with pytest.raises(DependencyError, match="REVOKED"):
            registry.activate(session, dependency_id=record.id)


def test_revocation_requires_a_reason(registry):
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="x")
        with pytest.raises(DependencyError, match="reason"):
            registry.revoke(session, dependency_id=record.id, reason="  ")


# ------------------------------------------------------------------ #
# Portability
# ------------------------------------------------------------------ #

def test_revocation_names_what_it_stranded(registry):
    """The moment portability is tested. Anything left without an alternative
    is named here rather than discovered later."""
    with get_db_session() as session:
        primary = registry.declare(session, kind="model_provider", name="primary")
        registry.declare(session, kind="model_provider", name="dependent",
                         fallback_dependency_id=primary.id)
        result = registry.revoke(session, dependency_id=primary.id,
                                 reason="provider deprecated the endpoint")
    stranded = [row["name"] for row in result["dependents_left_without_fallback"]]
    assert stranded == ["dependent"]


def test_portability_report_flags_live_without_fallback(registry):
    with get_db_session() as session:
        record = registry.declare(session, kind="platform_adapter", name="x",
                                  **_complete_platform())
        registry.activate(session, dependency_id=record.id)
        report = registry.portability_report(session)
    assert report["live"] == 1
    assert "x" in report["live_without_fallback"]
    assert report["by_kind"]["platform_adapter"] == 1


def test_all_four_kinds_share_one_registry(registry):
    with get_db_session() as session:
        for kind in KINDS:
            registry.declare(session, kind=kind, name=f"{kind}-1")
        report = registry.portability_report(session)
    assert report["declared"] == 4
    assert all(report["by_kind"][kind] == 1 for kind in KINDS)


def test_unknown_kind_is_refused(registry):
    with get_db_session() as session:
        with pytest.raises(DependencyError, match="kind must be"):
            registry.declare(session, kind="blockchain", name="x")
