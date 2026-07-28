"""Gate C-ORGAN-SHADOW: DALEOBANKS publication governed by the Reality Aperture.

Real organ code, real local controls, zero real publications.

Every test here would fail loudly if shadow mode could reach a production
adapter or if a production credential were visible on the aperture path.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from governance.aperture_shadow import (APERTURE_AVAILABLE, FakePlatform,
                                        ORGAN_ID, PRODUCTION_CREDENTIAL_VARS,
                                        SHADOW_WORKLOAD, ShadowConfigurationError,
                                        ShadowPublicationPath,
                                        assert_no_production_credentials,
                                        resolve_adapter)

pytestmark = pytest.mark.skipif(
    not APERTURE_AVAILABLE,
    reason="uniimente-kernel aperture not on the path; see PACKAGING GAP in "
           "governance/aperture_shadow.py")

if APERTURE_AVAILABLE:
    from aperture import (AuthorityIssuer, BudgetOffice, Ed25519SigningProvider,
                          Principal, Proposal, VerificationRegistry)
    from aperture.revocation import RevocationAuthority, RevocationState

POLICY, CONSTITUTION = "policy-1.0", "const-1.0"
ACTOR = ORGAN_ID + "/agent/publisher"
TARGET = "shadow:fake-platform/outbox"
TEXT = "A governed shadow publication. No real platform was contacted."


@pytest.fixture
def kernel():
    """The Kernel side. DALEOBANKS never holds this signer."""
    signer = Ed25519SigningProvider.generate("kernel-shadow-key-1")
    registry = VerificationRegistry()
    registry.register(signer.key_id, signer.public_key_hex())
    issuer = AuthorityIssuer(
        signer=signer, policy_version=POLICY, constitution_version=CONSTITUTION,
        policy_evaluator=lambda p, pr: "PERMIT",
        known_capabilities={"draft.publish"}, known_targets={TARGET},
        budget=BudgetOffice())
    issuer.register_principal(Principal(
        actor_id=ACTOR, organ_id=ORGAN_ID, workload_identity=SHADOW_WORKLOAD,
        legal_principal="alfonso_lopez",
        declared_capabilities=("draft.publish",),
        consequence_ceiling="external_contact", budget_ceiling_usd=1.0))
    ra = RevocationAuthority(signer)
    state = RevocationState(registry)
    state.accept(ra.publish())
    return {"signer": signer, "registry": registry, "issuer": issuer,
            "ra": ra, "state": state}


def cert_for(kernel, text=TEXT, request_id="cand-1"):
    return kernel["issuer"].issue(actor_id=ACTOR, proposal=Proposal(
        request_id=request_id, capability_id="draft.publish",
        action_class="draft.publish", target_id=TARGET, payload={"text": text},
        consequence_class="external_contact",
        evidence_refs=["sha256:" + "e" * 64], estimated_cost_usd=0.0,
        expected_outcome="one shadow post exists"))


def path_for(kernel, platform=None, guard=None, switch=None):
    p = ShadowPublicationPath(
        registry=kernel["registry"], revocation=kernel["state"],
        policy_version=POLICY, constitution_version=CONSTITUTION,
        constitution_guard=guard, kill_switch=switch, platform=platform)
    return p


class ArmedSwitch:
    armed = True


class DisarmedSwitch:
    armed = False


# ------------------------------------------------------------ configuration

def test_shadow_cannot_resolve_a_production_adapter():
    """The hard stop. If this ever passes silently, shadow is not shadow."""
    class ProdAdapter:
        adapter_id = "x-live"
        is_production = True

    with pytest.raises(ShadowConfigurationError):
        resolve_adapter("x-live")
    with pytest.raises(ShadowConfigurationError):
        resolve_adapter("twitter")


def test_only_the_fake_adapter_is_reachable():
    assert resolve_adapter(FakePlatform.adapter_id) is FakePlatform


def test_production_credentials_on_the_path_fail_closed():
    for var in PRODUCTION_CREDENTIAL_VARS:
        with pytest.raises(ShadowConfigurationError):
            assert_no_production_credentials({var: "secret-value"})


def test_no_production_credential_is_present_in_this_run():
    assert_no_production_credentials()          # no exception
    for var in PRODUCTION_CREDENTIAL_VARS:
        assert not os.environ.get(var), f"{var} is set during a shadow test"


def test_the_organ_holds_no_signing_capability(kernel):
    p = path_for(kernel)
    assert not hasattr(p.aperture, "signer")
    assert not hasattr(p.aperture, "sign")
    assert not hasattr(p.aperture.registry, "sign")


# ------------------------------------------------------------ the full path

def test_full_shadow_path_commits_and_publishes_nothing_real(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, guard=None, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="shadow run authorized")
    r = p.run({"id": "c1", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "committed"
    assert r.readback_verified is True
    assert platform.readback()[0]["text"] == TEXT
    assert p.real_publications() == 0
    assert p.metrics.external_publications == 0


def test_veto_starts_engaged_so_a_shadow_run_refuses_by_default(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=ArmedSwitch())
    r = p.run({"id": "c2", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "local_veto"
    assert platform.readback() == []


def test_disarmed_killswitch_blocks_before_any_certificate_is_used(kernel):
    """DALEOBANKS' real KillSwitch semantics: armed=False means do not act."""
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=DisarmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="testing the switch")
    r = p.run({"id": "c3", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "local_refusal"
    assert "KillSwitch" in r.reason
    assert platform.readback() == []


def test_constitution_guard_drift_refuses(kernel):
    class DriftedGuard:
        def verify(self):
            return False

    platform = FakePlatform()
    p = path_for(kernel, platform, guard=DriftedGuard(), switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="testing the guard")
    r = p.run({"id": "c4", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "local_refusal"
    assert "ConstitutionGuard" in r.reason
    assert platform.readback() == []


def test_the_organ_cannot_authorize_its_own_publication(kernel):
    """DALEOBANKS may refuse. It may not manufacture permission."""
    from aperture import Aperture
    import inspect
    assert "signer" not in inspect.signature(Aperture.__init__).parameters
    assert "signing_provider" not in inspect.signature(Aperture.__init__).parameters


# ------------------------------------------------- independent external state

def test_executor_cannot_fabricate_the_readback(kernel):
    """The adapter claims success and writes nothing. Readback disagrees."""
    platform = FakePlatform(drop_silently=True)
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    r = p.run({"id": "c5", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "reconciliation_mismatch"
    assert r.readback_verified is False
    assert platform.submissions == 1        # it really was called
    assert platform.readback() == []        # and really did nothing


def test_missing_external_state_is_not_treated_as_success(kernel):
    platform = FakePlatform(drop_silently=True)
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    r = p.run({"id": "c6", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status != "committed"


def test_submitted_intent_and_observed_result_can_differ(kernel):
    """The platform mutates what it stores. The verifier notices."""
    platform = FakePlatform(mutate=lambda t: t.replace("governed", "ungoverned"))
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    r = p.run({"id": "c7", "text": TEXT, "actor_id": ACTOR}, cert_for(kernel))
    assert r.status == "reconciliation_mismatch"
    assert platform.readback()[0]["text"] != TEXT


def test_duplicate_execution_does_not_produce_two_valid_outcomes(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    c = cert_for(kernel)
    assert p.run({"id": "c8", "text": TEXT, "actor_id": ACTOR}, c).status == "committed"
    second = p.run({"id": "c8", "text": TEXT, "actor_id": ACTOR}, c)
    assert second.status == "replay"
    assert len(platform.readback()) == 1


def test_forged_certificate_is_refused_by_the_organ(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    c = cert_for(kernel)
    c.signature = "00" * 64
    r = p.run({"id": "c9", "text": TEXT, "actor_id": ACTOR}, c)
    assert r.status == "bad_signature"
    assert platform.readback() == []


def test_another_organ_cannot_use_a_daleobanks_certificate(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    r = p.run({"id": "c10", "text": TEXT,
               "actor_id": "spiffe://uniimente.internal/organ/wmi/agent/x"},
              cert_for(kernel))
    assert r.status == "actor_mismatch"
    assert platform.readback() == []


def test_revoked_certificate_is_refused_in_shadow(kernel):
    platform = FakePlatform()
    c = cert_for(kernel)
    kernel["ra"].revoke_certificate(c.authority_record_id)
    kernel["state"].accept(kernel["ra"].publish())
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    r = p.run({"id": "c11", "text": TEXT, "actor_id": ACTOR}, c)
    assert r.status == "certificate_revoked"
    assert platform.readback() == []


# ------------------------------------------------------------ metrics

def test_metrics_are_produced_and_report_zero_real_publications(kernel):
    platform = FakePlatform()
    p = path_for(kernel, platform, switch=ArmedSwitch())
    p.release_veto(operator="alfonso_lopez", reason="run")
    p.run({"id": "m1", "text": TEXT, "actor_id": ACTOR},
          cert_for(kernel, request_id="m1"), legacy_would_publish=True)
    p.run({"id": "m2", "text": TEXT, "actor_id": "spiffe://other"},
          cert_for(kernel, request_id="m2"), legacy_would_publish=True)
    m = p.metrics.as_dict()
    assert m["candidates_processed"] == 2
    assert m["certificates_issued"] == 1
    assert m["identity_mismatches"] == 1
    assert m["external_publications"] == 0
    assert m["legacy_path_disagreements"] == 1
    assert isinstance(m["false_refusals"], str)     # deliberately unclassified
    assert m["mean_validation_latency_ms"] is not None
