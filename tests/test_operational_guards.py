"""The six controls the adversarial list named and the repository lacked.

Every guard gets a refusal case and a case proving it permits the legitimate
version. A guard only ever observed permitting has not been tested, and a
guard that blocks real work is worse than the failure it prevents.
"""

from datetime import datetime, timedelta, timezone

import pytest

from services.operational_guards import (
    BudgetExceededError,
    DuplicatePublicationError,
    PurposeViolationError,
    SchedulerStaleError,
    UnsolicitedMessageError,
    UnsupportedHealthClaimError,
    assert_dm_permitted,
    assert_health_claim_supported,
    assert_not_duplicate,
    assert_purpose_permitted,
    assert_scheduler_alive,
    assert_within_budget,
    budget_check,
    publication_fingerprint,
    scheduler_health,
)


def _now():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Budget
# ------------------------------------------------------------------ #

def test_undeclared_ceiling_is_zero_not_unlimited():
    """The one that would bite hardest. Budgets come from the founder; an
    absent ceiling is an absent decision, not permission."""
    verdict = budget_check(ceiling=None, committed=0.0, requested=1.0)
    assert verdict["allowed"] is False
    with pytest.raises(BudgetExceededError, match="no budget ceiling"):
        assert_within_budget(ceiling=None, committed=0.0, requested=1.0,
                             purpose="ad test")


def test_spend_beyond_remaining_is_refused():
    with pytest.raises(BudgetExceededError, match="exceeds remaining"):
        assert_within_budget(ceiling=100.0, committed=90.0, requested=25.0,
                             purpose="ad test")


def test_spend_within_ceiling_is_permitted():
    verdict = assert_within_budget(ceiling=100.0, committed=90.0, requested=10.0,
                                   purpose="ad test")
    assert verdict["allowed"] is True
    assert verdict["remaining"] == 10.0


# ------------------------------------------------------------------ #
# Scheduler liveness
# ------------------------------------------------------------------ #

def test_no_heartbeat_is_death_not_unknown():
    verdict = scheduler_health(last_heartbeat=None)
    assert verdict["alive"] is False
    assert verdict["posture"] == "PAUSE"
    with pytest.raises(SchedulerStaleError):
        assert_scheduler_alive(last_heartbeat=None)


def test_stale_heartbeat_degrades_to_pause():
    stale = _now() - timedelta(hours=3)
    with pytest.raises(SchedulerStaleError, match="not confirmed alive"):
        assert_scheduler_alive(last_heartbeat=stale)


def test_current_heartbeat_permits_running():
    verdict = assert_scheduler_alive(last_heartbeat=_now() - timedelta(seconds=30))
    assert verdict["alive"] is True
    assert verdict["posture"] == "RUN"


# ------------------------------------------------------------------ #
# Duplicate publication
# ------------------------------------------------------------------ #

def test_reposting_the_same_artifact_is_refused():
    body = "Check line 802 against the good-faith estimate."
    first = assert_not_duplicate(account_id="a1", surface="x", body=body, seen=[])
    with pytest.raises(DuplicatePublicationError, match="already been published"):
        assert_not_duplicate(account_id="a1", surface="x", body=body, seen=[first])


def test_reformatting_does_not_make_it_a_new_post():
    """Negative control on the normalizer: whitespace is not a new artifact."""
    a = publication_fingerprint(account_id="a1", surface="x", body="one   two\nthree")
    b = publication_fingerprint(account_id="a1", surface="x", body="One two three")
    assert a == b


def test_same_body_on_a_different_surface_is_allowed():
    """Cross-posting is legitimate; duplicate posting to one surface is not."""
    body = "the same thesis"
    first = assert_not_duplicate(account_id="a1", surface="x", body=body, seen=[])
    assert_not_duplicate(account_id="a1", surface="tiktok", body=body, seen=[first])


# ------------------------------------------------------------------ #
# Direct messages
# ------------------------------------------------------------------ #

def test_uninvited_dm_is_refused():
    with pytest.raises(UnsolicitedMessageError, match="uninvited"):
        assert_dm_permitted(recipient_ref="u1", inbound_initiated=False,
                            capability_grant_id="grant-1")


def test_invitation_without_a_capability_grant_is_still_refused():
    """Negative control: permission from the person is not authority from the
    institution. Both are required."""
    with pytest.raises(UnsolicitedMessageError, match="capability grant"):
        assert_dm_permitted(recipient_ref="u1", inbound_initiated=True,
                            capability_grant_id="")


def test_reply_to_an_inbound_message_with_a_grant_is_permitted():
    verdict = assert_dm_permitted(recipient_ref="u1", inbound_initiated=True,
                                  capability_grant_id="grant-1")
    assert verdict["permitted"] is True


def test_consented_contact_with_a_grant_is_permitted():
    verdict = assert_dm_permitted(recipient_ref="u1", inbound_initiated=False,
                                  consent_evidence_ref="optin-1",
                                  capability_grant_id="grant-1")
    assert verdict["consented"] is True


# ------------------------------------------------------------------ #
# Health claims
# ------------------------------------------------------------------ #

def test_diagnosing_the_reader_is_refused():
    with pytest.raises(UnsupportedHealthClaimError, match="diagnoses the reader"):
        assert_health_claim_supported(
            "If you feel this way in the morning, you have depression."
        )


def test_promising_a_cure_is_refused():
    with pytest.raises(UnsupportedHealthClaimError, match="cure"):
        assert_health_claim_supported(
            "This breathing practice cures anxiety. You don't need therapy."
        )


def test_unqualified_health_content_is_refused():
    with pytest.raises(UnsupportedHealthClaimError, match="no qualifier"):
        assert_health_claim_supported(
            "Trauma changes how you handle money and here is what it does."
        )


def test_qualified_educational_health_content_passes():
    """Negative control: pillar three has to remain writable. Education with a
    qualifier and a route to a professional is the intended shape."""
    assessment = assert_health_claim_supported(
        "Survival-mode thinking can make long-horizon saving feel unsafe. "
        "This is educational only and not a diagnosis — if it sounds like "
        "your daily experience, speak to a clinician."
    )
    assert assessment["touches_health"] is True
    assert assessment["qualifiers"]


def test_non_health_content_is_untouched():
    assessment = assert_health_claim_supported("Compound interest works like this.")
    assert assessment["touches_health"] is False


# ------------------------------------------------------------------ #
# Purpose limitation
# ------------------------------------------------------------------ #

def test_reading_a_record_outside_consented_purpose_is_refused():
    with pytest.raises(PurposeViolationError, match="outside the consented"):
        assert_purpose_permitted(
            requested_purpose="build a psychological profile",
            consented_purposes=["deliver the newsletter"],
            subject_ref="participant-1",
        )


def test_reading_without_stating_a_purpose_is_refused():
    with pytest.raises(PurposeViolationError, match="stated purpose is required"):
        assert_purpose_permitted(requested_purpose="",
                                 consented_purposes=["deliver the newsletter"],
                                 subject_ref="participant-1")


def test_reading_for_a_consented_purpose_is_permitted():
    verdict = assert_purpose_permitted(
        requested_purpose="Deliver the newsletter",
        consented_purposes=["deliver the newsletter", "research"],
        subject_ref="participant-1",
    )
    assert verdict["permitted"] is True
