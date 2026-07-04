"""Notification transport for the operator line (SMS via Twilio).

`services/operator_line.py` is the public facade; this module owns the
wire-level concerns — is SMS configured, sending a message, and validating
inbound webhook signatures — so the command logic never touches transport
details.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import urllib.parse
import urllib.request
from typing import Dict

from services.logging_utils import get_logger

logger = get_logger(__name__)


def sms_configured() -> bool:
    return all(
        os.getenv(var)
        for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "OPERATOR_PHONE")
    )


def send_sms(body: str) -> bool:
    """Send one SMS to the operator. Returns False (never raises) on failure."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    try:
        data = urllib.parse.urlencode({
            "To": os.getenv("OPERATOR_PHONE", ""),
            "From": os.getenv("TWILIO_FROM", ""),
            "Body": body[:1500],
        }).encode()
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data=data,
            method="POST",
        )
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        logger.error(f"Operator SMS send failed: {exc}")
        return False


def validate_twilio_signature(url: str, params: Dict[str, str], signature: str) -> bool:
    """Validate Twilio's X-Twilio-Signature header (HMAC-SHA1 over the URL
    plus sorted POST params, keyed by the auth token)."""
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token or not signature:
        return False
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


__all__ = ["sms_configured", "send_sms", "validate_twilio_signature"]
