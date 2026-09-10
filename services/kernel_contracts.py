"""Compatibility names for Kernel-owned translations. No forked semantics.

Canonical: uniimente-kernel adapters/daleobanks_opportunity.py and
adapters/wealthmachine_assessment.py; semantic owner Kernel contracts/adapters.
Supported: canonical/wire 1.0 and 1.1. Consumer shim expires when callers import
the boundary dependency directly; remove after schema/translation conformance.
Missing dependency or observation time fails closed. Old code remains in Git.
"""
from adapters.daleobanks_opportunity import AdapterError as ContractRefusal
from adapters.daleobanks_opportunity import enrich as wire_packet_to_kernel
from adapters.daleobanks_opportunity import to_wire as kernel_packet_to_wire
from adapters.wealthmachine_assessment import adapt as _assessment
from adapters.wealthmachine_assessment import to_wire as kernel_assessment_to_wire

KERNEL_SCHEMA_VERSION = "1.1"
# Historical vendored-schema comparison only; executable truth is the dependency.
PINNED_SCHEMA_HASHES = {
    "opportunity-packet": "aaa3970164b14bb7dcca6c9dde10017f5c376c4db40f0292ad4356e0442e4c64",
    "venture-assessment": "c0ad6578fb8ded2319bb03f37c6d99c38514068c5565dbfde0ae2577219f46a7",
}

def wire_assessment_to_kernel(wire):
    return _assessment(wire, transport_identity="wealthmachine")
