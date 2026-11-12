"""v3.3.0 Security & Replay Fencing Verification Suite for nce-vertical-engines."""

from __future__ import annotations

from pathlib import Path

import pytest

from nce_verticals.dynamics365.client import DataverseClient
from nce_verticals.odoo.auth import OdooAuthConfig
from nce_verticals.odoo.client import OdooClient
from nce_verticals.replay_fence import (
    ReplaySandboxFenceError,
    assert_not_replay_sandbox,
    check_replay_sandbox_env,
)
from nce_verticals.salesforce.client import SalesforceClient
from nce_verticals.security.entra_id import EntraPrincipal, extract_mcp_gateway_claims


@pytest.mark.asyncio
async def test_vertical_replay_sandbox_fencing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify replay sandbox fences external mutations in Odoo, Salesforce, and Dynamics 365."""
    monkeypatch.setenv("NCE_REPLAY_SANDBOX", "true")
    assert check_replay_sandbox_env() is True

    with pytest.raises(ReplaySandboxFenceError):
        await assert_not_replay_sandbox()

    odoo = OdooClient(
        OdooAuthConfig(
            url="https://odoo.example.com",
            db_name="prod",
            username="u",
            api_key="p",
            uid=1,
        )
    )
    with pytest.raises(ReplaySandboxFenceError):
        await odoo.execute_kw("res.partner", "create", [[{"name": "Test"}]])

    sf = SalesforceClient(instance_url="https://sf.example.com", access_token="tok")
    with pytest.raises(ReplaySandboxFenceError):
        await sf.create_sobject("Account", {"Name": "Test"})

    d365 = DataverseClient(
        org_url="https://org.crm4.dynamics.com",
        access_token="tok",
    )
    with pytest.raises(ReplaySandboxFenceError):
        await d365._send("POST", "/api/data/v9.2/accounts", json_body={"name": "Test"})


def test_entra_id_mcp_gateway_claim_alignment() -> None:
    """Verify Entra ID OIDC claims map cleanly to /mcp gateway session parameters."""
    claims = {
        "oid": "user-oid-123",
        "upn": "alice@contoso.com",
        "tid": "00000000-0000-4000-8000-000000000077",
        "roles": ["NCE.Operator"],
        "scp": "mcp.tools.call",
        "nce_allowed_engines": ["type:erp-crm", "cat:commercial"],
        "nce_tool_exposure_mode": "compact",
    }
    mapped = extract_mcp_gateway_claims(claims)
    assert mapped["principal_id"] == "user-oid-123"
    assert mapped["namespace_id"] == "00000000-0000-4000-8000-000000000077"
    assert "type:erp-crm" in mapped["allowed_engines"]
    assert mapped["tool_exposure_mode"] == "compact"

    principal = EntraPrincipal(
        oid="user-oid-123",
        tid="00000000-0000-4000-8000-000000000077",
        upn="alice@contoso.com",
        display_name="Alice",
        pc_hostname="workstation-01",
        os_username="alice",
        auth_method="oidc_bearer",
        matched_groups=[],
        matched_roles=["NCE.Operator"],
        verified_at=1000.0,
        expires_at=2000.0,
    )
    session_dict = principal.to_mcp_gateway_session()
    assert session_dict["principal_id"] == "user-oid-123"
    assert session_dict["tool_exposure_mode"] == "compact"


def test_pyproject_pep508_offline_safe_metadata() -> None:
    """Verify pyproject.toml does not embed git+https:// direct URLs in dependencies."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject_path.read_text(encoding="utf-8")
    assert "git+https://" not in text
    assert any(f'version = "{v}"' in text for v in ("3.4.3", "3.4.2", "3.4.1", "3.4.0", "3.3.0"))
