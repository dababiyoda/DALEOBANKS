"""One declaration in, one wired institution out.

Everything else in this repository is a part. These tests cover the machine:
that it refuses an incomplete declaration by naming the missing decision,
that it never raises its own authority, and that the report is computed
rather than typed — a report that cannot be written by hand cannot be
flattering by accident.
"""

import textwrap

import pytest

from db.session import get_db_session, init_db
from services.institution import DaleoBanks, Declaration, DeclarationError

COMPLETE = """
founder: "Alfonso Lopez"
timezone: "America/New_York"
campaign:
  aspiration: "Prove one real source-to-owned-relationship transaction"
  success_state: "One retained external observation"
  gate: "Founder-declared surface and exact authority"
  sbm: "AUTHORIZED_EXTERNAL_EVIDENCE_LOOP_CLOSURE_RATE"
  evidence_threshold: "One retained observation, positive or negative"
  resource_ceiling: "USD 250"
  stop_condition: "No response within 14 days"
owned_audience:
  destination: "newsletter:weekly"
  channel: "email"
budget:
  ceiling: 250.0
accounts:
  - name: "UNIIMENTE"
    platform: "x"
    handle: "uniimente"
    language: "en"
    identity_type: "brand_account"
    purpose: "Flagship rabbit hole"
    audience: "Cross-border earners"
    risk_level: "medium"
source_packet:
  topic: "cross-border financial friction"
  discovery_source: "feedly"
  claim: "Remittance corridors carry fees that compound against saving."
  thesis: "Why hard work may not compound across borders."
  counterargument: "Remittances buy option value a spreadsheet does not price."
  sources:
    - title: "Remittance Prices Worldwide"
      url: "https://example.org/rpw"
      source_class: "primary_government"
      publisher: "World Bank"
      text: "Average cost of sending USD 200."
languages: ["en"]
"""


def _write(tmp_path, body, name="decl.yaml"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


@pytest.fixture
def declaration_path(tmp_path):
    return _write(tmp_path, COMPLETE)


# ------------------------------------------------------------------ #
# It refuses a decision nobody made
# ------------------------------------------------------------------ #

def test_missing_declaration_file_names_the_next_step(tmp_path):
    with pytest.raises(DeclarationError, match="founder_declaration.example"):
        Declaration.load(str(tmp_path / "absent.yaml"))


def test_incomplete_campaign_names_every_missing_field(tmp_path):
    body = COMPLETE.replace('  resource_ceiling: "USD 250"\n', "").replace(
        '  stop_condition: "No response within 14 days"\n', ""
    )
    path = _write(tmp_path, body, "partial.yaml")
    with pytest.raises(DeclarationError) as excinfo:
        Declaration.load(path)
    message = str(excinfo.value)
    assert "resource_ceiling" in message
    assert "stop_condition" in message


def test_missing_top_level_section_is_named(tmp_path):
    body = COMPLETE.replace('timezone: "America/New_York"\n', "")
    path = _write(tmp_path, body, "notz.yaml")
    with pytest.raises(DeclarationError, match="timezone"):
        Declaration.load(path)


def test_gaps_are_named_without_blocking(declaration_path, tmp_path):
    """A blank handle is legal to run with and worth saying out loud."""
    body = COMPLETE.replace('    handle: "uniimente"', '    handle: ""')
    path = _write(tmp_path, body, "nohandle.yaml")
    gaps = Declaration.load(path).gaps()
    assert any("handle is blank" in gap for gap in gaps)


def test_complete_declaration_has_no_gaps(declaration_path):
    assert Declaration.load(declaration_path).gaps() == []


# ------------------------------------------------------------------ #
# It never raises its own authority
# ------------------------------------------------------------------ #

def test_preflight_states_shadow_only(declaration_path):
    preflight = DaleoBanks.from_declaration(declaration_path).preflight()
    assert preflight["publishing_mode"] == "SHADOW_ONLY"
    assert preflight["live_publication"] == "NOT_AUTHORIZED_BY_A_DECLARATION_FILE"


def test_bootstrap_seeds_surfaces_as_shadow(declaration_path):
    """A config file is not a standing mandate. This is the boundary most
    likely to erode in a composition layer, so it is asserted directly."""
    from db.models import AccountLane

    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.bootstrap(session)
        lanes = session.query(AccountLane).all()

    assert lanes
    for lane in lanes:
        assert lane.status == "SHADOW"
        assert lane.current_authorization == "SHADOW_ONLY"
        assert lane.active is False


def test_bootstrap_is_idempotent(declaration_path):
    from db.models import AccountLane

    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.bootstrap(session)
        institution.bootstrap(session)
        assert len(session.query(AccountLane).all()) == 1


# ------------------------------------------------------------------ #
# The cycle
# ------------------------------------------------------------------ #

def test_full_cycle_produces_a_shadow_receipt_and_no_external_effect(declaration_path):
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        result = institution.run_cycle(session)

    assert result["cycle"] == "COMPLETE"
    steps = {step["step"]: step for step in result["steps"]}
    assert steps["ingest"]["status"] == "OK"
    assert steps["content"]["status"] == "OK"
    assert steps["shadow_publish"]["status"] == "OK"
    assert steps["shadow_publish"]["external_effect"] is False
    assert steps["shadow_publish"]["mode"] == "SHADOW"


def test_cycle_predeclares_the_campaign_the_declaration_answers(declaration_path):
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        result = institution.run_cycle(session)
    steps = {step["step"]: step for step in result["steps"]}
    assert steps["predeclare"]["status"] == "OK"
    assert steps["predeclare"]["sbm"] == "AUTHORIZED_EXTERNAL_EVIDENCE_LOOP_CLOSURE_RATE"


def test_second_cycle_does_not_open_a_second_campaign(declaration_path):
    """One gate at a time survives the composition layer."""
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.run_cycle(session)
        result = institution.run_cycle(session)
    steps = {step["step"]: step for step in result["steps"]}
    assert steps["predeclare"]["status"] == "ALREADY_LIVE"
    assert steps["goal_chase"]["action"] == "AWAIT_OUTCOME"


def test_empty_source_packet_stops_the_stage_rather_than_inventing_one(tmp_path):
    body = COMPLETE.split("  sources:")[0] + "  sources: []\nlanguages: [\"en\"]\n"
    path = _write(tmp_path, body, "nosource.yaml")
    init_db()
    institution = DaleoBanks.from_declaration(path)
    with get_db_session() as session:
        result = institution.run_cycle(session)
    steps = {step["step"]: step for step in result["steps"]}
    assert result["cycle"] == "PARTIAL"
    assert steps["ingest"]["status"] == "SKIPPED"


# ------------------------------------------------------------------ #
# The report is computed
# ------------------------------------------------------------------ #

def test_report_counts_only_what_actually_happened(declaration_path):
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.run_cycle(session)
        report = institution.report(session)

    assert report["CURRENT_IMPLEMENTED"]["shadow_receipts"] == 1
    # A full cycle ran and nothing went live. Both are true at once.
    assert report["OFFICIAL_ACCOUNTS_REGISTERED"] == 0
    assert report["ACCOUNTS_DECLARED_SHADOW"] == 1
    assert report["LANGUAGES_ACTIVE"] == 0
    assert report["PLATFORMS_ACTIVE"] == 0
    assert report["REVENUE"] == 0
    assert report["OWNED_AUDIENCE"] == 0
    assert report["WMI_REAL_PATH"] == "UNEXERCISED"
    assert report["VERIFIED_ASPIRATION_GATES_CLEARED"] == 0
    assert report["VERIFIED_ADVANCEMENT_ACTION_RATE"] is None
    assert report["generated_from"].startswith("durable store")


def test_report_before_any_cycle_is_all_zeros(declaration_path):
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        report = institution.report(session)
    assert report["CURRENT_IMPLEMENTED"]["shadow_receipts"] == 0
    assert report["VERIFIED_ASPIRATION_GATES_CLEARED"] == 0
