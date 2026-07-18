"""Tests for the admin token exchange (ADMIN_TOKEN -> short-lived JWT)."""

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from config import get_config
from services.ledger import DecisionLedger, set_shared_instances, reset_shared_instances


async def test_valid_admin_token_mints_admin_jwt(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        config = get_config()
        response = await app_module.issue_admin_token(
            app_module.TokenRequest(admin_token=config.ADMIN_TOKEN)
        )

        claims = pyjwt.decode(
            response["token"],
            config.JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        assert claims["sub"] == "admin"
        assert claims["roles"] == ["admin"]
        assert response["expires_in"] == 3600
        assert ledger.replay("admin_token_issued")
    finally:
        reset_shared_instances()


async def test_wrong_admin_token_is_rejected(tmp_path):
    ledger = DecisionLedger(path=str(tmp_path / "ledger.jsonl"))
    set_shared_instances(ledger=ledger)
    try:
        import app as app_module

        with pytest.raises(HTTPException) as exc_info:
            await app_module.issue_admin_token(
                app_module.TokenRequest(admin_token="not-the-token")
            )
        assert exc_info.value.status_code == 401
        assert ledger.replay("admin_token_issued") == []
        assert ledger.replay("admin_token_rejected")
    finally:
        reset_shared_instances()
