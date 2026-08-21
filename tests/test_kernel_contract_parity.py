"""Issue #57 exit evidence: wire parity against kernel contracts v1.1.

The vendored schemas under contracts/kernel/ are pinned by SHA-256 — any
silent drift fails here. Translations between the DALEOBANKS transport
dialect and kernel law preserve the constitution in both directions.

Dependency-light by design: structural validation is hand-rolled (the repo
runs without jsonschema), covering required fields, additionalProperties,
enums, and consts — exactly what these two contracts demand.
"""
import hashlib
import json
import uuid
from pathlib import Path

import pytest

from services import kernel_contracts as kc

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "contracts" / "kernel"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _structural_validate(instance: dict, schema: dict) -> list[str]:
    problems = []
    for req in schema.get("required", []):
        if req not in instance:
            problems.append(f"missing required: {req}")
    if schema.get("additionalProperties") is False:
        extra = set(instance) - set(schema.get("properties", {}))
        if extra:
            problems.append(f"additional properties: {sorted(extra)}")
    for key, spec in schema.get("properties", {}).items():
        if key not in instance:
            continue
        if "enum" in spec and instance[key] not in spec["enum"]:
            problems.append(f"{key} not in enum {spec['enum']}")
        if "const" in spec and instance[key] != spec["const"]:
            problems.append(f"{key} must be const {spec['const']}")
    return problems


PACKET_SCHEMA = json.loads((SCHEMAS / "opportunity-packet.schema.json").read_text())
ASSESSMENT_SCHEMA = json.loads((SCHEMAS / "venture-assessment.schema.json").read_text())


class TestPinnedSchemas:
    def test_vendored_schemas_match_pins(self):
        assert _sha(SCHEMAS / "opportunity-packet.schema.json") == \
            kc.PINNED_SCHEMA_HASHES["opportunity-packet"]
        assert _sha(SCHEMAS / "venture-assessment.schema.json") == \
            kc.PINNED_SCHEMA_HASHES["venture-assessment"]

    def test_vendored_schemas_are_kernel_v11(self):
        assert PACKET_SCHEMA["properties"]["schema_version"]["enum"] == ["1.0", "1.1"]
        assert ASSESSMENT_SCHEMA["properties"]["requires_human_approval"] == \
            {"type": "boolean", "const": True}


class TestOutboundPackets:
    def _wire_packet(self):
        return {"id": str(uuid.uuid4()),
                "observed_pain": "people keep asking how to start budgeting",
                "core_thesis": "budgeting literacy is the first lever",
                "audience": "young professionals", "customer_segment": "consumers",
                "buyer_type": "self-serve", "risk_flags": ["finance_education_only"],
                "evidence": ["sha256:" + "a" * 64, "five replies (unhashed)"],
                "possible_offer": "$19 checklist",
                "smallest_validation_action": "post the checklist outline"}

    def _enrichment(self):
        return {"pain_owner": "consumer", "budget_owner": "consumer",
                "governing_bottleneck": "financial literacy trust",
                "cheapest_decisive_test": "post the checklist outline"}

    def test_dialect_packet_becomes_valid_kernel_law(self):
        kernel = kc.wire_packet_to_kernel(self._wire_packet(),
                                          enrichment=self._enrichment())
        assert _structural_validate(kernel, PACKET_SCHEMA) == []
        assert kernel["observed_failure"] == self._wire_packet()["observed_pain"]
        assert kernel["key_risks"] == ["finance_education_only"]
        # only hash-formatted evidence survives into kernel law
        assert kernel["evidence_refs"] == ["sha256:" + "a" * 64]

    def test_missing_enrichment_refuses(self):
        with pytest.raises(kc.ContractRefusal, match="enrichment"):
            kc.wire_packet_to_kernel(self._wire_packet(), enrichment={})

    def test_missing_id_refuses(self):
        wire = self._wire_packet()
        wire["id"] = ""
        with pytest.raises(kc.ContractRefusal, match="id"):
            kc.wire_packet_to_kernel(wire, enrichment=self._enrichment())


class TestInboundAssessments:
    def _wire_assessment(self, **kw):
        base = {"opportunity_packet_id": str(uuid.uuid4()), "go_no_go": "go",
                "opportunity_score": 0.7, "reasons": ["real pain", "cheap test"],
                "requires_human_approval": True}
        base.update(kw)
        return base

    def test_dialect_assessment_becomes_valid_kernel_law(self):
        kernel = kc.wire_assessment_to_kernel(self._wire_assessment())
        assert _structural_validate(kernel, ASSESSMENT_SCHEMA) == []
        assert kernel["verdict"] == "go"
        assert kernel["requires_human_approval"] is True
        assert kernel["execution_authority"] is False

    def test_constitutional_violation_on_wire_refused_not_sanitized(self):
        with pytest.raises(kc.ContractRefusal, match="constitution"):
            kc.wire_assessment_to_kernel(
                self._wire_assessment(requires_human_approval=False))
        with pytest.raises(kc.ContractRefusal, match="constitution"):
            kc.wire_assessment_to_kernel(self._wire_assessment(execution_authority=True))

    def test_unknown_verdict_refused(self):
        with pytest.raises(kc.ContractRefusal, match="go_no_go"):
            kc.wire_assessment_to_kernel(self._wire_assessment(go_no_go="maybe"))

    def test_all_dialect_verdicts_map(self):
        for verdict in ("go", "defer", "kill", "needs_more_evidence"):
            kernel = kc.wire_assessment_to_kernel(self._wire_assessment(go_no_go=verdict))
            assert kernel["verdict"] == verdict
