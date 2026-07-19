"""Compatibility shim: the DALEOBANKS <-> WealthMachineIntelligence protocol.

Unified in kernel Phase 3: the implementation now lives in the UNIIMENTE
kernel SDK (``uniimente_kernel.contracts``), one module both repos import
instead of keeping mirrored copies in sync. The wire is formalized as
kernel contracts ``venture-signal`` and ``signal-assessment`` (v1.1,
byte-compatible with what this organ already emits). One behavioral note:
``validate_assessment_wire`` now also rejects assessments whose
``requires_human_approval`` is not exactly True — the rule WMI already
enforced on its side, applied on receipt here. WMI assessments always
carry it True.

The core rule stands: the machine prepares, the human authorizes, the
world responds, the system learns. Nothing in this protocol executes
anything.
"""

from uniimente_kernel.contracts import (
    ALLOWED_EVIDENCE_TIERS,
    ALLOWED_GO_NO_GO,
    ALLOWED_IDENTITY_TYPES,
    ALLOWED_RESULT_CLASSIFICATIONS,
    ALLOWED_SIGNAL_TYPES,
    FINANCE_EDUCATION_FLAG,
    FORBIDDEN_IDENTITY_TYPES,
    LANE_POLICY,
    LEGAL_RISK_FLAGS,
    SCHEMA_VERSION,
    assessment_to_wire,
    packet_to_wire,
    validate_assessment_wire,
    validate_identity_type,
    validate_packet_wire,
)

__all__ = [
    "SCHEMA_VERSION", "ALLOWED_SIGNAL_TYPES", "ALLOWED_GO_NO_GO",
    "ALLOWED_RESULT_CLASSIFICATIONS", "ALLOWED_EVIDENCE_TIERS",
    "ALLOWED_IDENTITY_TYPES", "FORBIDDEN_IDENTITY_TYPES", "LANE_POLICY",
    "LEGAL_RISK_FLAGS", "FINANCE_EDUCATION_FLAG",
    "packet_to_wire", "assessment_to_wire", "validate_assessment_wire",
    "validate_identity_type", "validate_packet_wire",
]
