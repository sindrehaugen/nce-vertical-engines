"""tests/test_enterprise_23_engines_contract.py
===================================================
Comprehensive enterprise contract tests for NCE Vertical Engines:
1. All 23 Engine Descriptors Contract (registry taxonomy, metadata, schema deps).
2. Entra ID Cryptographic JWKS RS256 Verification (P0-SEC-001).
3. Sales/Project Live Bridge Opt-In Seams & Admin Handlers (P1-VERT-001).
4. Migration 082 WORM & Composite Indexes Contract (P1-VERT-002).
"""

from __future__ import annotations

import ast
import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from nce_verticals.plugin import VerticalEnginesPlugin
from nce_verticals.registry import (
    ENGINE_REGISTRY,
    VALID_CATEGORIES,
    VALID_TYPES,
)
from nce_verticals.security.entra_id import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraVerificationError,
    verify_jwt_signature_with_jwks,
)

os.environ.setdefault(
    "NCE_MASTER_KEY",
    "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2",
)

# ===========================================================================
# Area 1: All 23 Engine Descriptors Contract
# ===========================================================================


def test_registry_has_exact_23_engines_and_valid_descriptors():
    """Verify ENGINE_REGISTRY contains exactly 23 engines with valid descriptors."""
    assert len(ENGINE_REGISTRY) == 23

    for slug, engine_meta in ENGINE_REGISTRY.items():
        assert isinstance(slug, str) and slug.strip()
        assert slug == engine_meta.slug
        assert isinstance(engine_meta.name, str) and engine_meta.name.strip()
        assert (
            isinstance(engine_meta.types, (list, tuple, set, frozenset))
            and len(engine_meta.types) > 0
        )
        for t in engine_meta.types:
            assert t in VALID_TYPES, f"Unknown type '{t}' in engine '{slug}'"
        assert (
            isinstance(engine_meta.categories, (list, tuple, set, frozenset))
            and len(engine_meta.categories) > 0
        )
        for c in engine_meta.categories:
            assert c in VALID_CATEGORIES, f"Unknown category '{c}' in engine '{slug}'"
        assert isinstance(engine_meta.requires_schemas, (list, tuple, set, frozenset))

    plugin = VerticalEnginesPlugin(enabled_engines="all")
    descriptors = plugin.get_engine_descriptors()
    assert len(descriptors) == 23

    slugs = {d["slug"] for d in descriptors}
    assert len(slugs) == 23
    assert slugs == set(ENGINE_REGISTRY.keys())

    for d in descriptors:
        assert d["slug"] in ENGINE_REGISTRY
        assert d["name"]
        assert len(d["types"]) > 0
        assert len(d["categories"]) > 0
        assert isinstance(d["requires_schemas"], list)
        assert d["tool_count"] > 0
        assert d["route_count"] > 0
        assert d["install_extra"] == f"nce-vertical-engines[{d['slug']}]"


# ===========================================================================
# Area 2: Entra ID Cryptographic JWKS RS256 Verification (P0-SEC-001)
# ===========================================================================


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a test RSA-2048 keypair and corresponding JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    raw_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key)
    jwk_dict = json.loads(raw_jwk) if isinstance(raw_jwk, str) else dict(raw_jwk)
    jwk_dict["kid"] = "test-rsa-key-1"
    jwk_dict["alg"] = "RS256"
    return private_key, public_key, jwk_dict


def test_entra_id_jwks_rs256_verification_and_tampering(rsa_keypair):
    """Verify real RS256 cryptographic signature validation against JWKS and tampering rejection."""
    private_key, _, jwk = rsa_keypair
    tenant_id = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"
    client_id = "nce-test-enterprise-client"
    now = int(time.time())

    claims = {
        "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "aud": client_id,
        "tid": tenant_id,
        "oid": "user-oid-888",
        "preferred_username": "architect@company.com",
        "groups": ["group-admins"],
        "roles": ["NCE.Admin"],
        "exp": now + 3600,
        "nbf": now - 60,
    }

    # Construct genuine signed RS256 JWT
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-rsa-key-1"},
    )

    # 1. Success on genuine token
    verified_claims = verify_jwt_signature_with_jwks(token, [jwk])
    assert verified_claims["oid"] == "user-oid-888"
    assert verified_claims["tid"] == tenant_id

    # 2. Rejection when signature is tampered
    parts = token.split(".")
    tampered_sig = parts[2][:-4] + ("AAAA" if parts[2][-4:] != "AAAA" else "BBBB")
    tampered_sig_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    with pytest.raises(PermissionError):
        verify_jwt_signature_with_jwks(tampered_sig_token, [jwk])

    # 3. Rejection when payload is modified without resigning
    forged_claims = dict(claims)
    forged_claims["oid"] = "attacker-oid-999"
    forged_payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(forged_claims).encode()).rstrip(b"=").decode()
    )
    tampered_payload_token = f"{parts[0]}.{forged_payload_b64}.{parts[2]}"
    with pytest.raises(PermissionError):
        verify_jwt_signature_with_jwks(tampered_payload_token, [jwk])


@pytest.mark.asyncio
async def test_entra_authenticator_with_jwks_rs256(rsa_keypair):
    """Verify EntraIDAuthenticator enforces signature verification with JWKS keys."""
    private_key, _, jwk = rsa_keypair
    tenant_id = "77777777-8888-9999-aaaa-bbbbbbbbbbbb"
    client_id = "nce-test-enterprise-client"
    now = int(time.time())

    cfg = EntraConfig(
        entra_tenant_id=tenant_id,
        client_id=client_id,
        enforce_mode="strict",
        allowed_group_ids=["group-admins"],
        allowed_app_roles=["NCE.Admin"],
        require_graph_check=False,
        verify_jwt_signature=True,
        jwks_keys=[jwk],
    )
    auth = EntraIDAuthenticator(config=cfg)

    # Valid signed token passes
    valid_token = jwt.encode(
        {
            "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            "aud": client_id,
            "tid": tenant_id,
            "oid": "user-oid-888",
            "preferred_username": "architect@company.com",
            "groups": ["group-admins"],
            "roles": ["NCE.Admin"],
            "exp": now + 3600,
            "nbf": now - 60,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-rsa-key-1"},
    )
    principal = await auth.verify_token_and_allowlist(valid_token)
    assert principal.oid == "user-oid-888"
    assert principal.upn == "architect@company.com"

    # Forged token signed with another key is rejected
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged_token = jwt.encode(
        {
            "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            "aud": client_id,
            "tid": tenant_id,
            "oid": "forged-oid",
            "preferred_username": "forged@company.com",
            "groups": ["group-admins"],
            "roles": ["NCE.Admin"],
            "exp": now + 3600,
            "nbf": now - 60,
        },
        other_key,
        algorithm="RS256",
        headers={"kid": "test-rsa-key-1"},
    )
    with pytest.raises((EntraVerificationError, PermissionError)):
        await auth.verify_token_and_allowlist(forged_token)


# ===========================================================================
# Area 3: Sales/Project Live Bridge Opt-In (P1-VERT-001)
# ===========================================================================


@pytest.mark.asyncio
async def test_sales_project_live_bridge_opt_in_seams():
    """Verify live bridge opt-in contracts for _propose_quote_to_sales and _read_signed_baseline."""
    for mod_name in (
        "mcp",
        "mcp.types",
        "redis",
        "redis.asyncio",
        "minio",
        "motor",
        "motor.motor_asyncio",
        "nce.orchestrator",
    ):
        sys.modules.setdefault(mod_name, MagicMock())

    from nce_verticals.project.baseline import _read_signed_baseline
    from nce_verticals.system_design.to_quote import _propose_quote_to_sales

    ns_id = uuid.uuid4()

    # 1. System Design -> Sales Seam (_propose_quote_to_sales)
    # Default unconfigured engine raises NotImplementedError
    plain_engine = MagicMock()
    with pytest.raises(NotImplementedError):
        await _propose_quote_to_sales(plain_engine, ns_id, {"quote_id": "Q-100"})

    # Configured engine with sales_bridge_enabled = True succeeds
    bridge_engine = MagicMock()
    bridge_engine.sales_bridge_enabled = True
    fake_quote_propose = MagicMock()
    fake_quote_propose.do_propose_quote = AsyncMock(
        return_value={"accepted": True, "quote_id": "Q-100"}
    )
    with patch.dict(sys.modules, {"nce_verticals.sales.quote_propose": fake_quote_propose}):
        res = await _propose_quote_to_sales(bridge_engine, ns_id, {"quote_id": "Q-100"})
        assert res["accepted"] is True
        assert res["quote_id"] == "Q-100"

    # 2. Project -> Sales Seam (_read_signed_baseline)
    # Default unconfigured engine raises NotImplementedError
    with pytest.raises(NotImplementedError):
        await _read_signed_baseline(plain_engine, ns_id, "Q-100")

    # Configured engine with sales_bridge_enabled = True and mock pg_pool succeeds
    bridge_engine_proj = MagicMock()
    bridge_engine_proj.sales_bridge_enabled = True
    fake_baseline = {
        "id": str(uuid.uuid4()),
        "quote_id": "Q-100",
        "signed_margin_pct": 0.28,
        "signed_total_nok": 150000.0,
        "signed_at": "2026-11-10T00:00:00+00:00",
    }
    fake_sales_baseline = MagicMock()
    fake_sales_baseline.read_signed_baseline = AsyncMock(return_value=fake_baseline)
    with patch.dict(
        sys.modules,
        {"nce_verticals.sales.signed_baseline": fake_sales_baseline},
    ):
        res_baseline = await _read_signed_baseline(bridge_engine_proj, ns_id, "Q-100")
        assert res_baseline == fake_baseline

    # 3. Project Admin Handlers exist as async handlers in nce_verticals/admin_handlers/project.py
    proj_handlers_path = (
        Path(__file__).resolve().parent.parent / "nce_verticals" / "admin_handlers" / "project.py"
    )
    tree = ast.parse(proj_handlers_path.read_text(encoding="utf-8"))
    async_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
    assert "api_project_suggest_pl" in async_funcs
    assert "api_project_record_outcome" in async_funcs
    assert "api_project_can_enter_phase" in async_funcs


# ===========================================================================
# Area 4: Migration 082 WORM & Composite Indexes Contract (P1-VERT-002)
# ===========================================================================


def test_migration_082_worm_and_composite_indexes_contract():
    """Verify migration 082 defines WORM protection and high-cardinality composite indexes."""
    mig_path = (
        Path(__file__).resolve().parent.parent
        / "nce_verticals"
        / "migrations"
        / "082_enterprise_hardening_worm_and_indexes.sql"
    )
    assert mig_path.is_file(), f"Migration 082 not found at {mig_path}"

    sql_content = mig_path.read_text(encoding="utf-8")

    # 1. WORM function & trigger on sales_signed_baselines
    assert "prevent_signed_baseline_mutation" in sql_content
    assert "trg_sales_signed_baselines_worm" in sql_content
    assert "sales_signed_baselines" in sql_content

    # 2. Composite multi-tenant lookup indexes
    assert "idx_sales_signed_baselines_ns_quote" in sql_content
    assert "idx_field_tech_work_orders_ns_status" in sql_content
