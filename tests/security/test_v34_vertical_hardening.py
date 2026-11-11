"""v3.4.0 Red-Team Security Suite for nce-vertical-engines.

Verifies:
1. Odoo XML-RPC Billion Laughs / DTD entity expansion bomb rejection via defusedxml.xmlrpc.
2. Pure-ASGI BoundedBodyMiddleware HTTP 413 enforcement (Content-Length + chunked stream)
   across Odoo, Salesforce, and Customer Portal standalone apps.
3. SSRF blocking of 169.254.169.254, [::ffff:169.254.169.254], 100.64.0.1 (CGNAT),
   and internal container hostnames across http_guard and vertical HTTP clients.
4. Microsoft Entra ID 075_entra_id_security_gate.sql prerequisite verification.
"""

from __future__ import annotations

import asyncio
import xmlrpc.client  # noqa: S411
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from defusedxml.common import DefusedXmlException, DTDForbidden, EntitiesForbidden

from nce_verticals.customer_portal.app import build_customer_portal_app
from nce_verticals.odoo.app import create_standalone_odoo_app
from nce_verticals.odoo.auth import OdooAuthConfig
from nce_verticals.odoo.client import OdooClient
from nce_verticals.salesforce.app import create_standalone_salesforce_app
from nce_verticals.salesforce.client import SalesforceClient
from nce_verticals.security.http_guard import (
    SSRFBlockedError,
    is_ip_blocked,
    validate_outbound_url,
    verify_entra_id_schema_gate,
)


def test_odoo_xmlrpc_defusedxml_rejects_billion_laughs_bomb() -> None:
    """Ensure importing nce_verticals.odoo.client patches xmlrpc against Billion Laughs DTD bombs."""
    # Ensure OdooClient module import activated defusedxml.xmlrpc.monkey_patch()
    assert OdooClient is not None

    billion_laughs_xml = (
        b'<?xml version="1.0"?>\n'
        b"<!DOCTYPE lolz [\n"
        b' <!ENTITY lol "lol">\n'
        b' <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
        b' <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">\n'
        b"]>\n"
        b"<methodResponse><params><param><value><string>&lol2;</string></value></param></params></methodResponse>"
    )

    parser, unmarshaller = xmlrpc.client.getparser()
    with pytest.raises((DTDForbidden, EntitiesForbidden, DefusedXmlException)):
        parser.feed(billion_laughs_xml)
        parser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("surface_name", "app_factory", "post_path"),
    [
        ("odoo", create_standalone_odoo_app, "/api/webhooks/odoo"),
        ("salesforce", create_standalone_salesforce_app, "/api/admin/entra/verify-user"),
        ("customer_portal", build_customer_portal_app, "/api/portal/login"),
    ],
)
async def test_vertical_apps_enforce_http_413_content_length_and_chunked(
    monkeypatch: pytest.MonkeyPatch,
    surface_name: str,
    app_factory: Any,
    post_path: str,
) -> None:
    monkeypatch.setenv("NCE_MAX_HTTP_BODY_BYTES", "256")
    app = app_factory()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Oversized Content-Length
        resp_cl = await client.post(
            post_path,
            content=b"a" * 600,
            headers={"Content-Type": "application/json"},
        )
        assert resp_cl.status_code == 413, (
            f"{surface_name} Content-Length got {resp_cl.status_code}"
        )
        assert resp_cl.json()["error"] == "payload_too_large"

        # 2. Oversized chunked streaming body
        async def _chunks() -> AsyncIterator[bytes]:
            for _ in range(6):
                await asyncio.sleep(0)
                yield b"b" * 100

        resp_chunked = await client.post(
            post_path,
            content=_chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert resp_chunked.status_code == 413, (
            f"{surface_name} chunked got {resp_chunked.status_code}"
        )


@pytest.mark.parametrize(
    "ssrf_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/latest/meta-data/",
        "https://[::ffff:127.0.0.1]/rpc",
        "http://100.64.0.1/internal",
        "https://100.100.100.200/metadata",
        "http://host.docker.internal:8069",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_vertical_ssrf_guard_blocks_metadata_ipv4_mapped_and_cgnat(
    monkeypatch: pytest.MonkeyPatch,
    ssrf_url: str,
) -> None:
    monkeypatch.setenv("NCE_SSRF_ALLOWLIST_HOSTS", "")

    with pytest.raises(SSRFBlockedError):
        validate_outbound_url(ssrf_url, resolve_dns=False)

    with pytest.raises(SSRFBlockedError):
        OdooClient(
            OdooAuthConfig(
                url=ssrf_url,
                db_name="prod",
                username="svc",
                api_key="tok",
            )
        )

    with pytest.raises(SSRFBlockedError):
        SalesforceClient(instance_url=ssrf_url, access_token="tok")


def test_ip_unwrapping_and_ssrf_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    import ipaddress

    assert is_ip_blocked(ipaddress.ip_address("::ffff:169.254.169.254")) is True
    assert is_ip_blocked(ipaddress.ip_address("100.64.0.1")) is True
    assert is_ip_blocked(ipaddress.ip_address("93.184.216.34")) is False

    monkeypatch.setenv("NCE_SSRF_ALLOWLIST_HOSTS", "host.docker.internal,100.64.0.1")
    assert validate_outbound_url("http://host.docker.internal:8069", resolve_dns=False)
    assert validate_outbound_url("http://100.64.0.1/api", resolve_dns=False)


@pytest.mark.asyncio
async def test_entra_id_schema_gate_verifies_075_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NCE_ENTRA_ENFORCE_MODE", "strict")

    missing_conn = AsyncMock()
    missing_conn.fetchval = AsyncMock(side_effect=["entra_id_configs", "entra_id_sessions", None])
    with pytest.raises(RuntimeError, match="075_entra_id_security_gate.sql"):
        await verify_entra_id_schema_gate(missing_conn)

    present_conn = AsyncMock()
    present_conn.fetchval = AsyncMock(
        side_effect=["entra_id_configs", "entra_id_sessions", "entra_id_audit_log"]
    )
    assert await verify_entra_id_schema_gate(present_conn) is True

    monkeypatch.setenv("NCE_ENTRA_ENFORCE_MODE", "disabled")
    assert await verify_entra_id_schema_gate(missing_conn) is True
