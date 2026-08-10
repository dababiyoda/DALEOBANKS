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

def test_missing_declaration_file_falls_back_to_canon(tmp_path):
    """No file is not an error. It means run the mandate's own defaults and
    report what is still undecided."""
    declaration = Declaration.load(str(tmp_path / "absent.yaml"))
    assert declaration.path == "<canon>"
    assert declaration.accounts[0]["name"] == "UNIIMENTE"
    # Canon supplies structure and cannot supply ownership.
    assert any("handle is blank" in gap for gap in declaration.gaps())


def test_a_present_but_incomplete_declaration_still_refuses(tmp_path):
    """Negative control on the fallback: canon rescues an absent file, never
    a half-written one. A partial declaration is a decision in progress."""
    path = tmp_path / "partial.yaml"
    path.write_text("founder: \"Alfonso Lopez\"\ntimezone: \"UTC\"\n")
    with pytest.raises(DeclarationError, match="campaign"):
        Declaration.load(str(path))


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


# ------------------------------------------------------------------ #
# The defaults carry the mandate
# ------------------------------------------------------------------ #

def test_canon_seeds_the_rabbit_hole_with_off_ramps():
    """Every node in the shipped journey carries the opposing case and a way
    out, because the territory graph refuses one that does not."""
    from services.canon import RABBIT_HOLE

    assert len(RABBIT_HOLE) >= 4
    for node in RABBIT_HOLE:
        assert node["counterargument"].strip()
        assert node["off_ramp"].strip()
        assert node["capability_payload"].strip()


def test_canon_marks_the_public_channel_as_not_the_kernel():
    """The most expensive confusion available, refused in data."""
    from services.canon import FLAGSHIP_CHANNEL

    assert FLAGSHIP_CHANNEL["kernel_distinction"].startswith("PUBLIC_MEDIA_CHANNEL")
    assert "NOT the Golden Kernel" in FLAGSHIP_CHANNEL["purpose"]


def test_canon_ships_one_language_lane_not_three():
    """Success is not language count. Two lanes are candidates, not active."""
    from services.canon import LANGUAGE_LANES, default_declaration

    assert default_declaration()["languages"] == ["en"]
    assert {lane["status"] for lane in LANGUAGE_LANES} == {"PRIMARY", "CANDIDATE"}


def test_canon_declares_no_budget_and_no_handle():
    """Canon knows what the channel is for and nothing about who owns it."""
    from services.canon import default_declaration

    declaration = default_declaration()
    assert declaration["accounts"][0]["handle"] == ""
    assert declaration["budget"]["ceiling"] == 0.0
    assert declaration["source_packet"]["sources"] == []


def test_seeding_canon_is_idempotent(declaration_path):
    from db.models import TerritoryNode

    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        first = institution.seed_canon(session)
        second = institution.seed_canon(session)
        nodes = session.query(TerritoryNode).all()

    assert first["territory_nodes"] == 4
    assert second["territory_nodes"] == 0
    assert len(nodes) == 4


def test_zero_config_run_seeds_canon_and_refuses_the_rest(tmp_path):
    """The out-of-the-box path: no file, real structure, honest refusals."""
    init_db()
    institution = DaleoBanks.from_declaration(str(tmp_path / "absent.yaml"))
    with get_db_session() as session:
        result = institution.run_cycle(session)
    steps = {step["step"]: step for step in result["steps"]}

    assert steps["seed_canon"]["territory_nodes"] == 4
    assert steps["seed_canon"]["primitives"] == 5
    assert steps["ingest"]["status"] == "SKIPPED"
    assert steps["goal_chase"]["code"] == "NO_BUDGET_CEILING"


def test_daily_edition_refuses_a_missing_section(declaration_path):
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.run_cycle(session)
        result = institution.daily_edition(session, sections={"what_happened": "x"})
    assert result["status"] == "REFUSED"
    assert "what_most_people_are_missing" in result["reason"]


def test_daily_edition_publishes_with_all_seven_sections(declaration_path):
    from services.canon import DAILY_NEWS

    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        institution.run_cycle(session)
        result = institution.daily_edition(
            session, sections={s: f"content for {s}" for s in DAILY_NEWS["sections"]}
        )
    assert result["status"] == "OK"
    assert result["hour_local"] == 20


def test_daily_edition_refuses_with_nothing_to_report(declaration_path):
    """Negative control: an edition with no claims is headline repetition."""
    init_db()
    institution = DaleoBanks.from_declaration(declaration_path)
    with get_db_session() as session:
        result = institution.daily_edition(session)
    assert result["status"] == "REFUSED"
    assert "nothing to report" in result["reason"]
