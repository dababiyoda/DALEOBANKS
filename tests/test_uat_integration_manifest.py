import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "services" / "uat_integration_manifest.json"


def test_uat_integration_is_a_held_service_contract() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["classification"] == "separate_sibling_service"
    assert manifest["protocol"]["schema_version"] == "1.0"
    assert manifest["protocol"]["requires_human_approval"] is True
    assert manifest["runtime"]["status"] == "not_configured"
    assert manifest["runtime"]["execution_authority"] == "none"
    assert manifest["runtime"]["live_mode_required"] is False


def test_site_and_live_player_cannot_gain_authority() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert "store_service_secret" in manifest["website_boundary"]["prohibited"]
    assert "claim_live_connection_from_intent" in (
        manifest["website_boundary"]["prohibited"]
    )
    assert manifest["live_player"]["classification"] == (
        "uat_agent_context_not_connector"
    )
    assert manifest["live_player"]["included_in_protocol"] is False
    assert manifest["live_player"]["authority"] == "none"
    assert len(manifest["required_activation_evidence"]) >= 9
