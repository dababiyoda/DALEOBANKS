"""Compatibility shim: prompt injection defense spine.

The implementation now lives in the UNIIMENTE kernel SDK
(``uniimente_kernel.prompt_firewall``), extracted from this module in
kernel Phase 2 with identical behavior: same sanitize/scan/wrap rules,
same canary mechanics, same doctrine gate. The kernel class adds an
optional ``extra_patterns`` constructor argument; calling it with no
arguments is unchanged.

The shared-firewall helpers stay here so existing imports keep working.
"""

from __future__ import annotations

from typing import Optional

from uniimente_kernel.prompt_firewall import PromptFirewall

_SHARED_FIREWALL: Optional[PromptFirewall] = None


def get_firewall() -> PromptFirewall:
    global _SHARED_FIREWALL
    if _SHARED_FIREWALL is None:
        _SHARED_FIREWALL = PromptFirewall()
    return _SHARED_FIREWALL


def set_firewall(firewall: Optional[PromptFirewall]) -> None:
    global _SHARED_FIREWALL
    _SHARED_FIREWALL = firewall


__all__ = ["PromptFirewall", "get_firewall", "set_firewall"]
