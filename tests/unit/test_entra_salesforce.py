"""
Unit & Integration Validation Suite for:
1. Microsoft Entra ID Identification Point & Company Security Group / Role Allowlist Gate
2. Standalone & Integrated Salesforce Vertical Engine (all 3 auth modes, CRUD, SOQL, Webhooks, Sync)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import unittest

from nce_verticals.entra_id.auth import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraVerificationError,
)
from nce_verticals.entra_id.guard import EntraSecurityGate
from nce_verticals.plugin import (
    EntraIDPlugin,
    SalesforcePlugin,
)
from nce_verticals.salesforce.auth import (
    SalesforceAuthConfig,
    SalesforceTokenManager,
    build_salesforce_jwt_assertion,
)
from nce_verticals.salesforce.operations import SalesforceOperations
from nce_verticals.salesforce.webhooks import SalesforceWebhookReceiver


def _make_mock_jwt(claims: dict) -> str:
    hdr = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode("ascii")
    body = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).rstrip(b"=").decode("ascii")
    sig = base64.urlsafe_b64encode(b"mock-signature").rstrip(b"=").decode("ascii")
    return f"{hdr}.{body}.{sig}"


class TestEntraIDGate(unittest.IsolatedAsyncioTestCase):
    async def test_entra_allowlist_group_and_role_enforcement(self) -> None:
        cfg = EntraConfig(
            entra_tenant_id="11111111-2222-3333-4444-555555555555",
            client_id="nce-enterprise-app-id",
            enforce_mode="strict",
            allowed_group_ids=["group-nce-authorized"],
            allowed_app_roles=["NCE.User", "NCE.Salesforce.Write"],
            require_graph_check=False,
        )
        auth = EntraIDAuthenticator(config=cfg)
        gate = EntraSecurityGate(authenticator=auth)

        now = int(time.time())
        valid_token = _make_mock_jwt(
            {
                "tid": "11111111-2222-3333-4444-555555555555",
                "aud": "nce-enterprise-app-id",
                "oid": "user-oid-123",
                "preferred_username": "engineer@company.no",
                "name": "Senior Engineer",
                "groups": ["group-nce-authorized"],
                "roles": ["NCE.User"],
                "exp": now + 3600,
                "nbf": now - 60,
            }
        )

        principal = await gate.verify_request("sf_query_soql", {"entra_token": valid_token})
        self.assertIsNotNone(principal)
        assert principal is not None
        self.assertEqual(principal.upn, "engineer@company.no")
        self.assertIn("group-nce-authorized", principal.matched_groups)

        # Unauthorized user not in company's Entra Security Group must be denied
        unauthorized_token = _make_mock_jwt(
            {
                "tid": "11111111-2222-3333-4444-555555555555",
                "aud": "nce-enterprise-app-id",
                "oid": "user-oid-999",
                "preferred_username": "guest@company.no",
                "groups": ["other-random-group"],
                "roles": [],
                "exp": now + 3600,
            }
        )
        with self.assertRaises(EntraVerificationError) as ctx:
            await gate.verify_request("sf_create_record", {"entra_token": unauthorized_token})
        self.assertEqual(ctx.exception.code, "NOT_IN_COMPANY_ALLOWLIST")

        # Wrong Tenant ID must be denied
        wrong_tenant_token = _make_mock_jwt(
            {
                "tid": "99999999-9999-9999-9999-999999999999",
                "aud": "nce-enterprise-app-id",
                "oid": "user-oid-123",
                "preferred_username": "engineer@external.com",
                "groups": ["group-nce-authorized"],
                "exp": now + 3600,
            }
        )
        with self.assertRaises(EntraVerificationError) as ctx2:
            await gate.verify_request("sf_query_soql", {"entra_token": wrong_tenant_token})
        self.assertEqual(ctx2.exception.code, "TENANT_MISMATCH")


class TestSalesforceVerticalEngine(unittest.IsolatedAsyncioTestCase):
    async def test_standalone_crud_and_soql(self) -> None:
        sf_cfg = SalesforceAuthConfig(
            instance_url="",  # Standalone mode without remote org
            auth_mode="client_credentials",
            require_entra_gate=False,
        )
        ops = SalesforceOperations(token_manager=SalesforceTokenManager(config=sf_cfg))

        # 1. Create Account
        created = await ops.manage_crm_entity(
            "Account",
            "create",
            payload={"Name": "Nordic Systems AS", "Industry": "IT & Infrastructure"},
        )
        self.assertTrue(created["success"])
        acc_id = created["id"]

        # 2. Update Account
        updated = await ops.manage_crm_entity(
            "Account",
            "update",
            record_id=acc_id,
            payload={"Phone": "+47 22 02 11 00"},
        )
        self.assertTrue(updated["updated"])

        # 3. Get Account
        fetched = await ops.manage_crm_entity("Account", "get", record_id=acc_id)
        self.assertEqual(fetched["record"]["Name"], "Nordic Systems AS")
        self.assertEqual(fetched["record"]["Phone"], "+47 22 02 11 00")

        # 4. Query via SOQL
        queried = await ops.query_soql("SELECT Id, Name, Industry FROM Account")
        self.assertEqual(queried["totalSize"], 1)
        self.assertEqual(queried["records"][0]["Id"], acc_id)

        # 5. Delete Account
        deleted = await ops.manage_crm_entity("Account", "delete", record_id=acc_id)
        self.assertTrue(deleted["deleted"])

    def test_jwt_bearer_assertion_and_webhook_verification(self) -> None:
        assertion = build_salesforce_jwt_assertion(
            client_id="connected-app-key",
            subject="integration@company.no",
            audience="https://login.salesforce.com",
            private_key_pem="test-signing-key-secret",
        )
        self.assertEqual(len(assertion.split(".")), 3)

        sf_cfg = SalesforceAuthConfig(webhook_secret="my-sf-webhook-secret")
        ops = SalesforceOperations(token_manager=SalesforceTokenManager(config=sf_cfg))
        receiver = SalesforceWebhookReceiver(ops=ops)

        body = json.dumps(
            {
                "event_id": "evt-001",
                "sobject_type": "Opportunity",
                "Id": "006ABC123456789",
                "change_type": "UPSERT",
                "record": {
                    "Id": "006ABC123456789",
                    "Name": "Oslo Hospital Network Upgrade",
                    "StageName": "Closed Won",
                },
            }
        ).encode("utf-8")

        sig = base64.b64encode(
            hmac.new(b"my-sf-webhook-secret", body, hashlib.sha256).digest()
        ).decode("ascii")
        self.assertTrue(receiver.verify_signature(body, sig))
        self.assertFalse(receiver.verify_signature(body, "invalid-sig"))

        events = receiver.parse_payload(body, "application/json")
        stats = receiver.process_events(events)
        self.assertEqual(stats["processed"], 1)
        # Idempotency check: second delivery of same event_id is skipped
        stats_dup = receiver.process_events(events)
        self.assertEqual(stats_dup["duplicates_skipped"], 1)


class TestOdooSuperEngineAndCrossTalker(unittest.IsolatedAsyncioTestCase):
    async def test_odoo_orm_workflows_and_super_intelligence(self) -> None:
        from nce_verticals.odoo.auth import OdooAuthConfig
        from nce_verticals.odoo.intelligence import OdooSuperIntelligence
        from nce_verticals.odoo.operations import OdooOperations

        ops = OdooOperations(config=OdooAuthConfig(url="", require_entra_gate=False))
        intel = OdooSuperIntelligence(ops=ops)

        # 1. Create a new customer partner & draft sale order
        partner_id = await ops.execute_kw(
            "res.partner",
            "create",
            args=[{"name": "Kongsberg Maritime AS", "city": "Kongsberg", "is_company": True}],
        )
        self.assertGreater(partner_id, 1000)

        order_id = await ops.execute_kw(
            "sale.order",
            "create",
            args=[
                {
                    "partner_id": [partner_id, "Kongsberg Maritime AS"],
                    "amount_untaxed": 250000.0,
                    "amount_total": 312500.0,
                    "margin": 85000.0,
                    "margin_percent": 0.34,
                }
            ],
        )
        # Confirm order via workflow action
        await ops.execute_kw("sale.order", "action_confirm", args=[[order_id]])
        confirmed = await ops.execute_kw("sale.order", "read", args=[[order_id]])
        self.assertEqual(confirmed[0]["state"], "sale")

        # 2. Run 360° Super-Intelligence Pulse
        pulse = await intel.executive_erp_pulse()
        self.assertIn("finance_and_margins", pulse)
        self.assertGreaterEqual(pulse["finance_and_margins"]["margin_anomalies_count"], 1)
        self.assertGreaterEqual(pulse["inventory_and_mrp"]["replenishment_proposals_count"], 1)
        self.assertGreaterEqual(pulse["crm_and_pipeline"]["total_leads"], 2)

    async def test_odoo_llm_crosstalk_and_cross_engine_bridges(self) -> None:
        from nce_verticals.odoo.auth import OdooAuthConfig
        from nce_verticals.odoo.crosstalk import OdooLLMCrossTalker
        from nce_verticals.odoo.operations import OdooOperations
        from nce_verticals.odoo.webhooks import OdooWebhookReceiver
        from nce_verticals.plugin import OdooPlugin

        ops = OdooOperations(
            config=OdooAuthConfig(
                url="", webhook_secret="odoo-secret-123", require_entra_gate=False
            )
        )
        ct = OdooLLMCrossTalker(ops=ops)

        # 1. Bidirectional Chatter @nce prompt
        res = await ct.handle_crosstalk_prompt(
            "@nce Check margin anomalies, stockouts, and confirm order",
            model="sale.order",
            record_id=302,
            author="sindre@company.no",
        )
        self.assertEqual(res["status"], "ok")
        self.assertIn("NCE Super-Intelligence Cross-Talk", res["reply"])
        self.assertIsNotNone(res["chatter_message"])

        # 2. Cross-Engine Bridge: Salesforce -> Odoo CRM
        bridge_sf = await ct.bridge_salesforce_to_odoo(
            sf_account_name="Aker Solutions ASA",
            sf_opportunity_name="Offshore Control Room Network & AV",
            expected_revenue=1800000.0,
        )
        self.assertEqual(bridge_sf["status"], "ok")
        self.assertTrue(bridge_sf["salesforce_account_id"])
        self.assertGreater(bridge_sf["odoo_lead_id"], 1000)

        # 4. Webhook HMAC verification & @nce Chatter auto-trigger
        wh = OdooWebhookReceiver(ops=ops)
        raw_payload = json.dumps(
            {
                "model": "sale.order",
                "res_id": 301,
                "event": "chatter_mention",
                "author": "erp_manager",
                "body": "@nce Give me an inventory and MRP forecast",
            }
        ).encode("utf-8")
        sig = hmac.new(b"odoo-secret-123", raw_payload, hashlib.sha256).hexdigest()
        self.assertTrue(wh.verify_signature(raw_payload, sig))
        self.assertFalse(wh.verify_signature(raw_payload, "bad-signature"))
        wh_out = await wh.process_webhook(raw_payload)
        self.assertTrue(wh_out["crosstalk_triggered"])

        # 5. Plugin registration check
        reg: dict = {}
        OdooPlugin().register_tools(reg)
        self.assertIn("odoo_execute_kw", reg)
        self.assertIn("odoo_super_intelligence", reg)
        self.assertIn("odoo_llm_crosstalk", reg)


class TestAuditFixesAndContracts(unittest.IsolatedAsyncioTestCase):
    async def test_entra_issuer_validation_and_route_mounting(self) -> None:
        from nce_verticals.mcp_tool_defs import TOOLS

        cfg = EntraConfig(
            entra_tenant_id="11111111-2222-3333-4444-555555555555",
            client_id="nce-enterprise-app-id",
            enforce_mode="strict",
            allowed_group_ids=["group-nce-authorized"],
            require_graph_check=False,
        )
        auth = EntraIDAuthenticator(config=cfg)
        now = int(time.time())

        # Valid v2.0 issuer should pass
        valid_iss_tok = _make_mock_jwt(
            {
                "tid": "11111111-2222-3333-4444-555555555555",
                "iss": "https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/v2.0",
                "aud": "nce-enterprise-app-id",
                "oid": "user-oid-123",
                "preferred_username": "engineer@company.no",
                "groups": ["group-nce-authorized"],
                "exp": now + 3600,
            }
        )
        p = await auth.verify_token_and_allowlist(valid_iss_tok)
        self.assertEqual(p.oid, "user-oid-123")

        # Spoofed / invalid issuer must be rejected with ISSUER_MISMATCH
        bad_iss_tok = _make_mock_jwt(
            {
                "tid": "11111111-2222-3333-4444-555555555555",
                "iss": "https://evil-idp.example.com/11111111-2222-3333-4444-555555555555/v2.0",
                "aud": "nce-enterprise-app-id",
                "oid": "user-oid-123",
                "preferred_username": "engineer@company.no",
                "groups": ["group-nce-authorized"],
                "exp": now + 3600,
            }
        )
        with self.assertRaises(EntraVerificationError) as ctx:
            await auth.verify_token_and_allowlist(bad_iss_tok)
        self.assertEqual(ctx.exception.code, "ISSUER_MISMATCH")

        # Verify _mount_routes keeps both GET and POST routes for same path
        from nce_verticals.plugin import OdooPlugin

        routes_list: list = []
        EntraIDPlugin().register_routes(routes_list)
        SalesforcePlugin().register_routes(routes_list)
        OdooPlugin().register_routes(routes_list)
        odoo_cfg_routes = [
            r for r in routes_list if getattr(r, "path", None) == "/api/admin/odoo/config"
        ]
        self.assertEqual(len(odoo_cfg_routes), 2)

        # Verify late-binding _h wrapper sets __qualname__
        reg: dict = {}
        OdooPlugin().register_tools(reg)
        self.assertIn("odoo_sync_now", reg)
        self.assertIn(
            "nce_verticals.odoo.mcp_handlers.handle_odoo_sync_now",
            reg["odoo_sync_now"].handler.__qualname__,
        )

        # Verify tools are advertised in mcp_tool_defs.TOOLS
        tool_names = {t.name for t in TOOLS}
        for expected in (
            "entra_whoami",
            "entra_verify_access",
            "entra_login_device_code",
            "entra_logout",
            "sf_query_soql",
            "sf_manage_account",
            "sf_sync_now",
            "odoo_execute_kw",
            "odoo_super_intelligence",
            "odoo_llm_crosstalk",
            "odoo_sync_now",
        ):
            self.assertIn(expected, tool_names)

    async def test_odoo_sync_engine(self) -> None:
        from nce_verticals.odoo.auth import OdooAuthConfig
        from nce_verticals.odoo.operations import OdooOperations
        from nce_verticals.odoo.sync import OdooSyncEngine

        ops = OdooOperations(config=OdooAuthConfig(url="", require_entra_gate=False))
        sync_engine = OdooSyncEngine(ops=ops)
        summary = await sync_engine.run_sync(models=["res.partner", "sale.order"])
        self.assertEqual(summary["status"], "completed")
        self.assertGreaterEqual(summary["total_records"], 4)
