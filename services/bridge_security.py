"""Temporary compatibility import; no independent security implementation.

Canonical source: uniimente-kernel adapters/bridge_transport.py.
Semantic owner: Kernel adapters/contracts. Consumer owner: this organ.
Supported transport: v2; wire contracts: 1.0/1.1. Missing dependency fails closed.
Expiry: all consumers import the pinned Kernel boundary directly.
Removal: migrate import paths and pass the same conformance/restart suite.
Historical v1 remains in Git; never an unsigned or in-process fallback.
"""
from adapters.bridge_transport import *  # noqa: F403
