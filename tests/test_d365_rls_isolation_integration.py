"""Postgres RLS integration: cross-namespace isolation for d365_integrations."""

from __future__ import annotations

from uuid import uuid4

import pytest
from nce.auth import set_namespace_context


@pytest.mark.integration
@pytest.mark.asyncio
async def test_d365_integrations_cross_namespace_isolation(
    pg_app_conn,
    make_namespace,
) -> None:
    """Verify that d365_integrations table is properly isolated between namespaces by RLS."""
    exists = await pg_app_conn.fetchval("SELECT to_regclass('public.d365_integrations')")
    if exists is None:
        pytest.skip("d365_integrations table requires nce_verticals migrations")
    ns_a = await make_namespace()
    ns_b = await make_namespace()
    org_url = f"https://pytest-org-{uuid4().hex}.crm.dynamics.com"

    async with pg_app_conn.transaction():
        await set_namespace_context(pg_app_conn, ns_a)
        row_id = await pg_app_conn.fetchval(
            """
            INSERT INTO d365_integrations (
                namespace_id, org_url, status
            )
            VALUES ($1, $2, 'ACTIVE')
            RETURNING id
            """,
            ns_a,
            org_url,
        )

    assert row_id is not None

    # Verify namespace B cannot see namespace A's integration
    async with pg_app_conn.transaction():
        await set_namespace_context(pg_app_conn, ns_b)
        visible = await pg_app_conn.fetchval(
            "SELECT count(*) FROM d365_integrations WHERE id = $1",
            row_id,
        )
        assert visible == 0

    # Verify namespace A can see its own integration
    async with pg_app_conn.transaction():
        await set_namespace_context(pg_app_conn, ns_a)
        visible = await pg_app_conn.fetchval(
            "SELECT count(*) FROM d365_integrations WHERE id = $1",
            row_id,
        )
        assert visible == 1
