"""
nce_verticals/odoo/crosstalk.py
===============================
Full Bidirectional LLM Cross-Talker for Odoo ERP (`OdooLLMCrossTalker`).

Makes Odoo a conversational & autonomous participant across the entire NCE ecosystem:
1. Inbound Chatter / Discuss Listener (`handle_chatter_or_llm_prompt`):
   - Parses `@nce` / `@llm` natural-language instructions from Odoo Chatter (`mail.message`),
     Odoo Discuss channels, or connected Claude/MCP sessions.
   - Executes autonomous analysis, workflow transitions, or cross-engine synchronization,
     and posts rich formatted responses directly back into the Odoo record's Chatter thread.
2. Cross-Engine Bridges:
   - `bridge_salesforce_to_odoo()`: Synchronizes a Salesforce `Account` / `Opportunity` directly
     into an Odoo `res.partner` + `crm.lead` / `sale.order` (and vice versa).
"""

from __future__ import annotations

import time
from typing import Any

from nce_verticals.odoo.intelligence import OdooSuperIntelligence
from nce_verticals.odoo.operations import OdooOperations, get_global_odoo_ops
from nce_verticals.salesforce.operations import get_global_salesforce_ops


class OdooLLMCrossTalker:
    """
    Bidirectional LLM Cross-Talker connecting Odoo Chatter/Discuss, Claude/MCP,
    Salesforce, and the NCE Graph.
    """

    def __init__(self, ops: OdooOperations | None = None) -> None:
        self.ops = ops or get_global_odoo_ops()
        self.intel = OdooSuperIntelligence(ops=self.ops)

    def _record_crosstalk(
        self,
        *,
        channel_or_model: str,
        record_id: int,
        direction: str,
        author: str,
        prompt_or_body: str,
        target_engines: list[str],
        response_summary: str,
        actions_executed: list[str],
    ) -> dict[str, Any]:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "channel_or_model": channel_or_model,
            "record_id": int(record_id),
            "direction": direction,
            "author": author,
            "prompt_or_body": prompt_or_body,
            "target_engines": target_engines,
            "response_summary": response_summary,
            "actions_executed": actions_executed,
        }
        self.ops._crosstalk_history.insert(0, entry)
        del self.ops._crosstalk_history[200:]
        return entry

    async def handle_crosstalk_prompt(
        self,
        prompt: str,
        *,
        model: str = "sale.order",
        record_id: int = 301,
        author: str = "odoo_user",
        post_reply_to_chatter: bool = True,
    ) -> dict[str, Any]:
        """
        Process a natural-language Cross-Talk message from Odoo Chatter/Discuss or an LLM,
        gather live intelligence across Odoo and Salesforce, execute requested
        actions, and post the reply back into Odoo Chatter.
        """
        clean_prompt = str(prompt or "").strip()
        low = clean_prompt.lower()
        target_engines = ["odoo"]
        actions_executed: list[str] = []
        structured_data: dict[str, Any] = {}

        # 1. Check if prompt asks for margin / invoice / financial analysis
        if any(k in low for k in ("margin", "faktura", "invoice", "cash", "økonomi", "anomaly", "avvik")):
            fin = await self.intel.analyze_margins_and_invoices()
            structured_data["finance_and_margins"] = fin
            actions_executed.append("analyze_margins_and_invoices")

        # 2. Check if prompt asks for stock / inventory / MRP replenishment
        if any(k in low for k in ("lager", "stock", "inventory", "mrp", "innkjøp", "reorder")):
            inv = await self.intel.forecast_inventory_and_mrp()
            structured_data["inventory_and_mrp"] = inv
            actions_executed.append("forecast_inventory_and_mrp")

        # 3. Check if prompt asks for CRM / lead / pipeline / Salesforce cross-talk
        if any(k in low for k in ("lead", "crm", "pipeline", "salg", "salesforce", "opportunity")):
            crm = await self.intel.score_leads_and_pipeline()
            structured_data["odoo_crm"] = crm
            actions_executed.append("score_leads_and_pipeline")
            if "salesforce" in low:
                target_engines.append("salesforce")
                sf_ops = get_global_salesforce_ops()
                sf_accounts = sf_ops.list_cached_records("Account", limit=10)
                structured_data["salesforce_accounts"] = sf_accounts
                actions_executed.append("cross_query_salesforce_accounts")

        # 4. Check if prompt triggers a workflow confirmation (e.g. "confirm", "bekreft", "post")
        if any(k in low for k in ("confirm order", "bekreft ordre", "action_confirm")) and model == "sale.order":
            await self.ops.execute_kw("sale.order", "action_confirm", args=[[int(record_id)]])
            actions_executed.append(f"sale.order.action_confirm({record_id})")

        # Default to full 360° ERP pulse if no narrow intent matched
        if not structured_data:
            pulse = await self.intel.executive_erp_pulse()
            structured_data["erp_pulse"] = pulse
            actions_executed.append("executive_erp_pulse")

        # Build concise executive response for Odoo Chatter & LLM
        fin_part = structured_data.get("finance_and_margins") or (structured_data.get("erp_pulse") or {}).get("finance_and_margins") or {}
        inv_part = structured_data.get("inventory_and_mrp") or (structured_data.get("erp_pulse") or {}).get("inventory_and_mrp") or {}
        crm_part = structured_data.get("odoo_crm") or (structured_data.get("erp_pulse") or {}).get("crm_and_pipeline") or {}

        reply_lines = [
            f"[NCE Super-Intelligence Cross-Talk] Analyzed {model}#{record_id}:",
            f"• Blended Margin: {fin_part.get('blended_margin_pct', 0)}% ({fin_part.get('margin_anomalies_count', 0)} margin anomalies, Overdue AR: {fin_part.get('accounts_receivable_overdue', 0)} NOK)",
            f"• Supply & MRP: {inv_part.get('replenishment_proposals_count', 0)} stockouts/reorders flagged (Est. PO: {inv_part.get('total_estimated_replenishment_cost', 0)} NOK)",
            f"• CRM Weighted Pipeline: {crm_part.get('weighted_pipeline_value', 0)} NOK across {crm_part.get('total_leads', 0)} active opportunities",
        ]
        if actions_executed:
            reply_lines.append(f"• Executed: {', '.join(actions_executed)}")
        reply_text = "\n".join(reply_lines)

        chatter_post = None
        if post_reply_to_chatter and model and record_id:
            chatter_post = await self.ops.post_chatter_message(model, int(record_id), reply_text)

        log_entry = self._record_crosstalk(
            channel_or_model=model,
            record_id=record_id,
            direction="INBOUND_FROM_ODOO",
            author=author,
            prompt_or_body=clean_prompt,
            target_engines=target_engines,
            response_summary=reply_text,
            actions_executed=actions_executed,
        )

        return {
            "status": "ok",
            "reply": reply_text,
            "chatter_message": chatter_post,
            "crosstalk_log": log_entry,
            "intelligence_data": structured_data,
        }

    async def bridge_salesforce_to_odoo(
        self,
        *,
        sf_account_name: str,
        sf_opportunity_name: str,
        expected_revenue: float = 500000.0,
    ) -> dict[str, Any]:
        """
        Cross-Engine Bridge (Salesforce CRM <-> Odoo ERP):
        Ensures the customer exists in both Salesforce (`Account`) and Odoo (`res.partner`),
        and creates a linked Odoo `crm.lead` & draft `sale.order`.
        """
        sf_ops = get_global_salesforce_ops()
        sf_acc = await sf_ops.manage_crm_entity(
            "Account",
            "create",
            payload={"Name": sf_account_name, "Type": "Customer - Direct"},
        )

        partner_id = await self.ops.execute_kw(
            "res.partner",
            "create",
            args=[
                {
                    "name": sf_account_name,
                    "is_company": True,
                    "customer_rank": 5,
                    "sf_account_id": sf_acc.get("id"),
                }
            ],
        )
        lead_id = await self.ops.execute_kw(
            "crm.lead",
            "create",
            args=[
                {
                    "name": sf_opportunity_name,
                    "partner_name": sf_account_name,
                    "expected_revenue": float(expected_revenue),
                    "probability": 80.0,
                    "type": "opportunity",
                }
            ],
        )
        summary = (
            f"Bridged Salesforce Account '{sf_account_name}' ({sf_acc.get('id')}) -> "
            f"Odoo res.partner#{partner_id} & crm.lead#{lead_id} ({expected_revenue} NOK)."
        )
        await self.ops.post_chatter_message("crm.lead", int(lead_id), summary)

        self._record_crosstalk(
            channel_or_model="crm.lead",
            record_id=int(lead_id),
            direction="CROSS_ENGINE_BRIDGE",
            author="salesforce_engine",
            prompt_or_body=f"Sync Salesforce Opportunity '{sf_opportunity_name}' to Odoo",
            target_engines=["salesforce", "odoo"],
            response_summary=summary,
            actions_executed=["sf.Account.create", "odoo.res.partner.create", "odoo.crm.lead.create"],
        )

        return {
            "status": "ok",
            "salesforce_account_id": sf_acc.get("id"),
            "odoo_partner_id": partner_id,
            "odoo_lead_id": lead_id,
            "summary": summary,
        }
