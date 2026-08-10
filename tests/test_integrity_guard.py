"""The optimizer's reward function has no term for whether anyone was served.

fame is engagement plus follower growth; penalty counts rate limits, mutes,
blocks, and ethics violations. So content that makes people angry, gets
shared, and never trips a platform block raises the J-score, and Thompson
sampling samples that arm more often. These guards exist because that is what
the live reward currently rewards.

The most important test in this file is not one of the refusals. It is
test_forceful_attack_on_a_broken_system_passes. A guard that flattens the
brand's actual register would be worse than no guard at all.
"""

import pytest

from services.integrity_guard import (
    ContemptError,
    FakeEngagementError,
    IntegrityGuardError,
    RageBaitError,
    assert_disclosed,
    assert_engagement_ingestible,
    assert_publishable,
    assert_reward_admissible,
    classify_target,
    disclosure_required,
    engagement_plausible,
    rage_bait_assessment,
    reward_admissible,
)

FORCEFUL_AND_USEFUL = (
    "These lenders bury a junk fee in the closing documents and count on you "
    "not reading page nine. It is predatory and it is legal. Here's how to "
    "check whether yours did it: request the itemized statement and compare "
    "line 802 against the good-faith estimate."
)
OUTRAGE_ONLY = (
    "This is outrageous and frankly disgusting. It should be illegal. "
    "Wake up, nobody is talking about this."
)
CONTEMPT = (
    "These people are too stupid to read a contract before signing it. "
    "They deserve what they get."
)
LAUNDERED_CONTEMPT = (
    "These predatory lenders are running a scam, but honestly, if you're this "
    "gullible you deserve it. Here's how to check line 802."
)


# ------------------------------------------------------------------ #
# The register the brand is supposed to have
# ------------------------------------------------------------------ #

def test_forceful_attack_on_a_broken_system_passes():
    """The load-bearing case. Ruthless toward the problem is the brand, and a
    guard that softened it would do more damage than the failure it prevents."""
    assessment = assert_publishable(FORCEFUL_AND_USEFUL)
    assert assessment["target"] == "system"
    assert assessment["capability_payload"] is True
    assert assessment["rage_bait"] is False
    assert assessment["contempt"] is False


def test_plain_reporting_about_a_protected_group_is_not_contempt():
    """Negative control on the contempt guard: naming who is harmed is
    reporting, not humiliation."""
    text = "Immigrant families are overcharged by these predatory lenders."
    assert classify_target(text) == "system"
    assert_publishable(text)


def test_strong_language_with_a_payload_survives():
    text = ("This fee structure is a disgrace. Here's how to get out of it: "
            "ask for the fee schedule in writing before you sign.")
    assessment = assert_publishable(text)
    assert assessment["outrage_present"] is True
    assert assessment["capability_payload"] is True


# ------------------------------------------------------------------ #
# Refusals
# ------------------------------------------------------------------ #

def test_outrage_without_a_payload_is_refused():
    with pytest.raises(RageBaitError, match="nothing the reader can do"):
        assert_publishable(OUTRAGE_ONLY)


def test_contempt_at_people_is_refused():
    with pytest.raises(ContemptError, match="humane toward the person"):
        assert_publishable(CONTEMPT)


def test_a_legitimate_target_does_not_launder_contempt():
    """Naming a real predator in the same sentence does not buy a sneer at the
    person harmed, even when a capability payload is present."""
    with pytest.raises(ContemptError):
        assert_publishable(LAUNDERED_CONTEMPT)


def test_assessment_reports_shape_without_raising():
    assessment = rage_bait_assessment(OUTRAGE_ONLY)
    assert assessment["rage_bait"] is True
    assert assessment["outrage_markers"]
    assert assessment["capability_markers"] == []


# ------------------------------------------------------------------ #
# The learning loop
# ------------------------------------------------------------------ #

def test_engagement_rising_while_capability_falls_is_refused():
    """The shortcut mid-formation. This is the only place it can be caught —
    by the time it reaches the J-score it has already been learned."""
    with pytest.raises(RageBaitError, match="shortcut"):
        assert_reward_admissible(
            arm="topic:outrage_thread",
            engagement_delta=+0.42, capability_delta=-0.11, trust_delta=-0.03,
        )


def test_engagement_rising_while_trust_falls_is_refused():
    with pytest.raises(RageBaitError):
        assert_reward_admissible(
            arm="topic:accusation", engagement_delta=+0.30,
            capability_delta=+0.01, trust_delta=-0.09,
        )


def test_engagement_rising_with_capability_is_admissible():
    """Negative control: growth is not the thing being punished. Engagement
    climbing alongside capability is exactly what the brand wants."""
    verdict = assert_reward_admissible(
        arm="topic:explainer", engagement_delta=+0.51,
        capability_delta=+0.22, trust_delta=+0.04,
    )
    assert verdict["admissible"] is True
    assert verdict["shortcut_detected"] is False


def test_quality_falling_without_engagement_rising_is_not_the_shortcut():
    """A bad week is not the shortcut. The signature requires both halves."""
    verdict = reward_admissible(
        engagement_delta=-0.20, capability_delta=-0.30, trust_delta=-0.10,
    )
    assert verdict["admissible"] is True


def test_small_fluctuations_do_not_trip_the_guard():
    verdict = reward_admissible(
        engagement_delta=+0.05, capability_delta=-0.01, trust_delta=-0.01,
    )
    assert verdict["admissible"] is True


# ------------------------------------------------------------------ #
# Fake engagement
# ------------------------------------------------------------------ #

def test_engagement_beyond_twice_the_follower_count_is_refused():
    with pytest.raises(FakeEngagementError, match="follower count"):
        assert_engagement_ingestible(observed=5000, baseline=40, followers=100)


def test_engagement_far_beyond_baseline_is_refused():
    with pytest.raises(FakeEngagementError, match="baseline"):
        assert_engagement_ingestible(observed=4000, baseline=50, followers=100000)


def test_negative_engagement_is_not_a_measurement():
    with pytest.raises(FakeEngagementError, match="negative"):
        assert_engagement_ingestible(observed=-5, baseline=40, followers=1000)


def test_ordinary_good_day_is_ingestible():
    """Negative control: a genuine strong post must not be discarded."""
    verdict = assert_engagement_ingestible(observed=320, baseline=40, followers=9000)
    assert verdict["plausible"] is True


def test_cold_start_with_no_baseline_is_ingestible():
    verdict = engagement_plausible(observed=12, baseline=0, followers=500)
    assert verdict["plausible"] is True


# ------------------------------------------------------------------ #
# Material-relationship disclosure
# ------------------------------------------------------------------ #

def test_promoting_pumpstation_without_disclosure_is_refused():
    with pytest.raises(IntegrityGuardError, match="without a disclosure"):
        assert_disclosed("PumpStation is the best way to get started building.")


def test_promoting_with_disclosure_passes():
    verdict = assert_disclosed(
        "Disclosure: PumpStation is a UNIIMENTE venture cell we own. "
        "With that stated, here is what it does."
    )
    assert verdict["disclosed"] is True
    assert "pumpstation" in verdict["entities"]


def test_unrelated_content_needs_no_disclosure():
    """Negative control: the guard must not demand a disclosure on everything."""
    verdict = assert_disclosed("Here's how compound interest works.")
    assert verdict["entities"] == []
    assert verdict["disclosed"] is True


def test_extra_entities_are_honored():
    assert disclosure_required("We like AcmeCo", extra_entities=["AcmeCo"]) == ["acmeco"]
    with pytest.raises(IntegrityGuardError):
        assert_disclosed("AcmeCo is excellent.", extra_entities=["AcmeCo"])


# ------------------------------------------------------------------ #
# The guard is wired to the thing it guards
# ------------------------------------------------------------------ #

def test_optimizer_calls_the_guard():
    """A guard nothing calls is documentation. This asserts the call site."""
    import inspect

    from services.optimizer import Optimizer

    source = inspect.getsource(Optimizer._thompson_sample)
    assert "_apply_integrity_guard" in source


def test_optimizer_withholds_reinforcement_on_the_signature():
    from services.optimizer import Optimizer

    optimizer = Optimizer.__new__(Optimizer)
    successes, failures = optimizer._apply_integrity_guard(
        "topic", "outrage_thread",
        {"engagement_delta": 0.40, "capability_delta": -0.12, "trust_delta": 0.0},
        8, 2,
    )
    # The pulls happened; they just do not count as wins.
    assert successes == 0
    assert failures == 10


def test_optimizer_leaves_healthy_arms_alone():
    """Negative control: growth is not what is being punished."""
    from services.optimizer import Optimizer

    optimizer = Optimizer.__new__(Optimizer)
    assert optimizer._apply_integrity_guard(
        "topic", "explainer",
        {"engagement_delta": 0.40, "capability_delta": 0.20, "trust_delta": 0.05},
        8, 2,
    ) == (8, 2)


def test_guard_is_inert_without_quality_telemetry_and_says_so():
    """The honest state today. The guard cannot see, and the system reports
    that rather than letting its presence imply protection."""
    from services.optimizer import Optimizer

    optimizer = Optimizer.__new__(Optimizer)
    assert optimizer._apply_integrity_guard(
        "topic", "anything", {"mean_reward": 0.9, "count": 10}, 8, 2
    ) == (8, 2)

    status = Optimizer.integrity_guard_status(
        {"topic": {"a": {"mean_reward": 0.9, "count": 10}}}
    )
    assert status["wired"] is True
    assert status["bound_to_telemetry"] is False
    assert "inert" in status["note"]


def test_status_reports_bound_once_telemetry_exists():
    from services.optimizer import Optimizer

    status = Optimizer.integrity_guard_status(
        {"topic": {"a": {"capability_delta": -0.2, "trust_delta": 0.0}}}
    )
    assert status["bound_to_telemetry"] is True
    assert status["arms_with_quality_signal"] == 1
