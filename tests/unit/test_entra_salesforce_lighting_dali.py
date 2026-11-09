"""
Unit & Integration Validation Suite for:
1. Microsoft Entra ID Identification Point & Company Security Group / Role Allowlist Gate
2. Standalone & Integrated Salesforce Vertical Engine (all 3 auth modes, CRUD, SOQL, Webhooks, Sync)
3. Relux / DIALux Light Design & IEC 62386 DALI-2 / Glamox System Design Connector, Reader & Analyser
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nce_verticals.entra_id.auth import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraVerificationError,
)
from nce_verticals.entra_id.guard import EntraSecurityGate
from nce_verticals.lighting_dali.analyser import (
    analyze_dali2_bus,
    analyze_lighting_project,
    analyze_room_en12464,
    calculate_dali_dimming_level,
    calculate_dt8_mirek,
)
from nce_verticals.lighting_dali.glamox_catalog import (
    decode_glamox_code,
    recommend_glamox_luminaires,
)
from nce_verticals.lighting_dali.parsers import (
    parse_dali_address_csv,
    parse_eulumdat_ldt,
    parse_iesna_ies,
    parse_relux_or_dialux_project,
)
from nce_verticals.plugin import (
    EntraIDPlugin,
    LightingDaliPlugin,
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
    hdr = (
        base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}')
        .rstrip(b"=")
        .decode("ascii")
    )
    body = (
        base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )
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

        principal = await gate.verify_request(
            "sf_query_soql", {"entra_token": valid_token}
        )
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
            await gate.verify_request(
                "sf_create_record", {"entra_token": unauthorized_token}
            )
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
            await gate.verify_request(
                "sf_query_soql", {"entra_token": wrong_tenant_token}
            )
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
            payload={"Name": "Glamox AS", "Industry": "Lighting & Marine"},
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
        self.assertEqual(fetched["record"]["Name"], "Glamox AS")
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
                    "Name": "Oslo Hospital DALI-2 Upgrade",
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


class TestLightingDaliAndGlamoxEngine(unittest.TestCase):
    def test_glamox_decoder_and_recommendations(self) -> None:
        c95 = decode_glamox_code(
            "Glamox C95-R 600x600 4000 TWH 827-865 MP DA-EM 3H SEN"
        )
        self.assertTrue(c95["is_glamox"])
        self.assertEqual(c95["model"], "C95-R")
        self.assertEqual(c95["dimensions_mm"], "600x600")
        self.assertEqual(c95["flux_lm"], 4000.0)
        self.assertTrue(c95["tunable_white_dt8"])
        self.assertEqual(c95["control_type"], "DALI-2_DT8_TUNABLE_WHITE")
        self.assertTrue(c95["has_emergency"])
        self.assertEqual(c95["emergency_duration_h"], 3)
        self.assertTrue(c95["has_integrated_sensor"])
        self.assertEqual(
            c95["dali_ecg_addresses_per_unit"], 2
        )  # 1 DT8 + 1 DT1 Emergency
        self.assertEqual(c95["dali_ecd_addresses_per_unit"], 1)  # 1 integrated sensor

        rec = recommend_glamox_luminaires("CAD_WORKSTATION", require_tunable_white=True)
        self.assertEqual(rec["zone_code"], "CAD_WORKSTATION")
        self.assertIn("Glamox", rec["recommended_order_code"])

    def test_dali2_bus_and_dimming_math(self) -> None:
        # IEC 62386-102 logarithmic dimming curve check: level 254 = 100%, level 0 = 0%
        lvl_254 = calculate_dali_dimming_level(254)
        self.assertAlmostEqual(lvl_254["light_output_pct"], 100.0, places=2)
        lvl_0 = calculate_dali_dimming_level(0)
        self.assertEqual(lvl_0["light_output_pct"], 0.0)

        # IEC 62386-209 DT8 Mirek check: 4000K -> 250 Mirek
        m4000 = calculate_dt8_mirek(4000)
        self.assertEqual(m4000["dt8_mirek"], 250)
        self.assertTrue(m4000["within_glamox_twh_range_2700_6500k"])

        # Compliant DALI-2 line
        bus_ok = analyze_dali2_bus(
            ecg_count=40,
            ecd_sensor_count=6,
            ecd_pushbutton_count=4,
            cable_length_m=150.0,
            cable_cross_section_mm2=1.5,
            psu_rated_current_ma=240.0,
        )
        self.assertTrue(bus_ok["compliant"])
        self.assertLessEqual(bus_ok["voltage_drop_v"], 2.0)

        # Overloaded DALI-2 line (>64 ECGs and >2.0V drop)
        bus_fail = analyze_dali2_bus(
            ecg_count=70,
            ecd_sensor_count=20,
            cable_length_m=320.0,
            cable_cross_section_mm2=0.75,
            topology="closed_ring",
        )
        self.assertFalse(bus_fail["compliant"])
        self.assertGreaterEqual(len(bus_fail["violations"]), 3)

    def test_eulumdat_ies_and_relux_project_analysis(self) -> None:
        # Build a valid 38-line EULUMDAT (.ldt) sample for Glamox C95-R
        ldt_lines = [
            "Glamox AS",
            "1",
            "4",
            "4",
            "90",
            "4",
            "30",
            "REP-C95",
            "Glamox C95-R 600x600 4000 DALI 840 MP",
            "C95-R-4000-DALI",
            "C95R.LDT",
            "2026-11-09",
            "595",
            "595",
            "65",
            "540",
            "540",
            "0",
            "0",
            "0",
            "0",
            "100",
            "100",
            "1.0",
            "0",
            "1",
            "1",
            "LED",
            "4000",
            "4000K",
            "80",
            "30.0",
            "0.65",
            "0.72",
            "0.78",
            "0.82",
            "0.85",
            "0.88",
            "0.90",
            "0.92",
            "0.94",
            "0.95",
            "0 90 180 270",
            "0 30 60 90",
            "420 360 150 0",
        ]
        ldt_res = parse_eulumdat_ldt("\n".join(ldt_lines))
        self.assertEqual(ldt_res["format"], "EULUMDAT_LDT")
        self.assertEqual(ldt_res["total_lamp_flux_lm"], 4000.0)
        self.assertTrue(ldt_res["glamox_decoded"]["is_glamox"])

        # IESNA (.ies) sample
        ies_sample = "\n".join(
            [
                "IESNA:LM-63-2002",
                "[MANUFAC] Glamox AS",
                "[LUMCAT] C77-R 600x600 4200 DALI 840 SI",
                "[LUMINAIRE] Glamox C77-R Low Glare Office",
                "TILT=NONE",
                "1 4200 1.0 3 1 1 2 0.6 0.6 0.06",
                "1.0 1.0 29.0",
                "0 45 90",
                "0",
                "1800 950 0",
            ]
        )
        ies_res = parse_iesna_ies(ies_sample)
        self.assertEqual(ies_res["format"], "IESNA_IES")
        self.assertEqual(ies_res["total_flux_lm"], 4200.0)
        self.assertEqual(ies_res["glamox_decoded"]["model"], "C77-R")

        # Relux project analysis
        relux_proj = parse_relux_or_dialux_project(
            {
                "project_name": "Stavanger Engineering Center",
                "source_tool": "relux",
                "rooms": [
                    {
                        "room_id": "R-101",
                        "name": "Engineering Open Plan",
                        "zone_code": "OFFICE_WRITING",
                        "length_m": 10.0,
                        "width_m": 6.0,
                        "height_m": 2.8,
                        "luminaires": [
                            {
                                "code": "Glamox C95-R 600x600 4000 DALI 840 MP",
                                "quantity": 14,
                            }
                        ],
                    }
                ],
            }
        )
        report = analyze_lighting_project(relux_proj)
        self.assertTrue(report["compliance_passed"])
        self.assertEqual(report["summary"]["total_dali2_subnets"], 1)
        self.assertEqual(report["summary"]["glamox_eth2dali_controllers"], 1)

    def test_plugins_register_tools(self) -> None:
        reg: dict = {}
        EntraIDPlugin().register_tools(reg)
        SalesforcePlugin().register_tools(reg)
        LightingDaliPlugin().register_tools(reg)
        self.assertIn("entra_whoami", reg)
        self.assertIn("sf_query_soql", reg)
        self.assertIn("sf_manage_account", reg)
        self.assertIn("lighting_analyze_relux_project", reg)
        self.assertIn("dali2_analyze_bus", reg)
        self.assertIn("glamox_decode_and_recommend", reg)


if __name__ == "__main__":
    unittest.main()
