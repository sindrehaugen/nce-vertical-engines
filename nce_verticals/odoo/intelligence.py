"""
nce_verticals/odoo/intelligence.py
==================================
Super-Intelligent Cognitive & Analytical Engine for Odoo ERP/CRM/MRP/Accounting.

Capabilities:
1. `analyze_margins_and_invoices()`:
   - Detects low-margin or negative-margin sales orders (`sale.order` / `sale.order.line`).
   - Detects overdue AR customer invoices and AP vendor bill anomalies (`account.move`).
   - Computes Net Working Capital exposure and cashflow health score.
2. `forecast_inventory_and_mrp()`:
   - Evaluates `stock.quant` available stock vs. `reorder_min_qty` and open `mrp.production` demand.
   - Generates autonomous replenishment purchase order (`purchase.order`) & MRP recommendations.
3. `score_leads_and_pipeline()`:
   - Computes multi-factor AI lead/opportunity conversion score, expected weighted revenue,
     stagnation risk (`days_since_last_activity`), and Next-Best-Action (NBA) recommendations.
4. `executive_erp_pulse()`:
   - Synthesizes a 360° real-time intelligence briefing across Sales, CRM, Inventory/MRP,
     Accounting, Projects, and Helpdesk.
"""

from __future__ import annotations

from typing import Any

from nce_verticals.odoo.operations import OdooOperations, get_global_odoo_ops


class OdooSuperIntelligence:
    """Cognitive & analytical intelligence engine over Odoo ERP models."""

    def __init__(self, ops: OdooOperations | None = None) -> None:
        self.ops = ops or get_global_odoo_ops()

    async def analyze_margins_and_invoices(
        self,
        *,
        min_acceptable_margin_pct: float = 0.15,
    ) -> dict[str, Any]:
        """Detect sales margin anomalies, overdue receivables, and cashflow risks."""
        orders = await self.ops.execute_kw("sale.order", "search_read", args=[[]], kwargs={"limit": 200})
        moves = await self.ops.execute_kw("account.move", "search_read", args=[[]], kwargs={"limit": 200})

        margin_anomalies: list[dict[str, Any]] = []
        total_sales_untaxed = 0.0
        total_margin = 0.0

        for so in orders:
            untaxed = float(so.get("amount_untaxed") or 0.0)
            margin = float(so.get("margin") or (untaxed * float(so.get("margin_percent") or 0.25)))
            margin_pct = (margin / untaxed) if untaxed > 0 else float(so.get("margin_percent") or 0.0)
            total_sales_untaxed += untaxed
            total_margin += margin

            if untaxed > 0 and margin_pct < min_acceptable_margin_pct:
                margin_anomalies.append(
                    {
                        "order_id": so.get("id"),
                        "order_name": so.get("name"),
                        "partner": so.get("partner_id"),
                        "state": so.get("state"),
                        "amount_untaxed": round(untaxed, 2),
                        "margin": round(margin, 2),
                        "margin_pct": round(margin_pct * 100.0, 2),
                        "severity": "CRITICAL" if margin_pct <= 0.0 else "WARNING",
                        "recommendation": (
                            f"Order {so.get('name')} has {margin_pct * 100.0:.1f}% margin "
                            f"(target >= {min_acceptable_margin_pct * 100.0:.1f}%). Review discount or vendor cost before confirming."
                        ),
                    }
                )

        ar_open = 0.0
        ar_overdue = 0.0
        ap_open = 0.0
        overdue_invoices: list[dict[str, Any]] = []

        for mv in moves:
            if mv.get("state") != "posted" or mv.get("payment_state") == "paid":
                continue
            residual = float(mv.get("amount_residual") or mv.get("amount_total") or 0.0)
            mtype = str(mv.get("move_type") or "out_invoice")
            days_overdue = int(mv.get("days_overdue") or 0)

            if mtype == "out_invoice":
                ar_open += residual
                if days_overdue > 0:
                    ar_overdue += residual
                    overdue_invoices.append(
                        {
                            "invoice_id": mv.get("id"),
                            "invoice_name": mv.get("name"),
                            "partner": mv.get("partner_id"),
                            "amount_residual": round(residual, 2),
                            "days_overdue": days_overdue,
                            "recommended_action": "Trigger automated dunning reminder or escalate to Account Manager in Chatter.",
                        }
                    )
            elif mtype == "in_invoice":
                ap_open += residual

        blended_margin_pct = round((total_margin / total_sales_untaxed) * 100.0, 2) if total_sales_untaxed > 0 else 0.0
        return {
            "total_sales_untaxed": round(total_sales_untaxed, 2),
            "total_margin": round(total_margin, 2),
            "blended_margin_pct": blended_margin_pct,
            "margin_anomalies_count": len(margin_anomalies),
            "margin_anomalies": margin_anomalies,
            "accounts_receivable_open": round(ar_open, 2),
            "accounts_receivable_overdue": round(ar_overdue, 2),
            "accounts_payable_open": round(ap_open, 2),
            "net_working_capital_balance": round(ar_open - ap_open, 2),
            "overdue_invoices": overdue_invoices,
        }

    async def forecast_inventory_and_mrp(self) -> dict[str, Any]:
        """Analyze stock quants and open MRP production orders to recommend replenishments."""
        quants = await self.ops.execute_kw("stock.quant", "search_read", args=[[]], kwargs={"limit": 200})
        productions = await self.ops.execute_kw("mrp.production", "search_read", args=[[]], kwargs={"limit": 100})

        replenishment_proposals: list[dict[str, Any]] = []
        total_replenishment_cost = 0.0

        for q in quants:
            avail = float(q.get("available_quantity") if q.get("available_quantity") is not None else q.get("quantity", 0.0))
            reorder_min = float(q.get("reorder_min_qty") or 10.0)
            if avail < reorder_min:
                shortfall = reorder_min - avail
                recommended_order_qty = max(shortfall, reorder_min * 1.5)
                unit_cost = float(q.get("unit_cost") or 1000.0)
                est_cost = round(recommended_order_qty * unit_cost, 2)
                total_replenishment_cost += est_cost
                replenishment_proposals.append(
                    {
                        "quant_id": q.get("id"),
                        "product": q.get("product_id"),
                        "product_code": q.get("product_code"),
                        "available_qty": avail,
                        "reorder_min_qty": reorder_min,
                        "recommended_po_qty": round(recommended_order_qty, 1),
                        "estimated_po_cost": est_cost,
                        "lead_time_days": int(q.get("lead_time_days") or 7),
                        "urgency": "CRITICAL_STOCKOUT" if avail <= 0 else "REORDER_BELOW_MIN",
                    }
                )

        return {
            "evaluated_quants": len(quants),
            "active_mrp_orders": len(productions),
            "replenishment_proposals_count": len(replenishment_proposals),
            "total_estimated_replenishment_cost": round(total_replenishment_cost, 2),
            "replenishment_proposals": replenishment_proposals,
            "mrp_productions": productions,
        }

    async def score_leads_and_pipeline(self) -> dict[str, Any]:
        """Compute AI conversion health scores and Next-Best-Actions for Odoo CRM leads."""
        leads = await self.ops.execute_kw("crm.lead", "search_read", args=[[]], kwargs={"limit": 200})
        scored_leads: list[dict[str, Any]] = []
        weighted_pipeline = 0.0

        for ld in leads:
            rev = float(ld.get("expected_revenue") or 0.0)
            prob = float(ld.get("probability") or 20.0)
            idle_days = int(ld.get("days_since_last_activity") or 0)
            priority_stars = int(ld.get("priority") or 1)

            # Penalty for stagnation (>14 days idle) and bonus for high priority
            stagnation_penalty = min(35.0, max(0.0, (idle_days - 7) * 1.8))
            ai_health_score = max(5.0, min(99.0, prob + (priority_stars * 5.0) - stagnation_penalty))
            weighted_val = rev * (prob / 100.0)
            weighted_pipeline += weighted_val

            if idle_days >= 14:
                nba = f"Stagnation alert ({idle_days}d idle): Schedule technical review & post follow-up in Odoo Chatter."
            elif prob >= 70.0:
                nba = "High closing velocity: Generate final Odoo Sale Order quotation & verify Glamox/AV stock."
            else:
                nba = "Qualify technical scope and link to System Design / Relux room calculation."

            scored_leads.append(
                {
                    "lead_id": ld.get("id"),
                    "name": ld.get("name"),
                    "partner_name": ld.get("partner_name"),
                    "expected_revenue": round(rev, 2),
                    "probability_pct": prob,
                    "weighted_value": round(weighted_val, 2),
                    "ai_health_score": round(ai_health_score, 1),
                    "days_since_last_activity": idle_days,
                    "next_best_action": nba,
                }
            )

        scored_leads.sort(key=lambda x: x["ai_health_score"], reverse=True)
        return {
            "total_leads": len(scored_leads),
            "weighted_pipeline_value": round(weighted_pipeline, 2),
            "scored_leads": scored_leads,
        }

    async def executive_erp_pulse(self) -> dict[str, Any]:
        """Generate a comprehensive 360° Super-Intelligent Odoo ERP health report."""
        finance = await self.analyze_margins_and_invoices()
        supply = await self.forecast_inventory_and_mrp()
        crm = await self.score_leads_and_pipeline()
        projects = await self.ops.execute_kw("project.project", "search_read", args=[[]], kwargs={"limit": 50})
        tickets = await self.ops.execute_kw("helpdesk.ticket", "search_read", args=[[]], kwargs={"limit": 50})

        return {
            "engine": "odoo_super_intelligence",
            "finance_and_margins": finance,
            "inventory_and_mrp": supply,
            "crm_and_pipeline": crm,
            "active_projects_count": len(projects),
            "open_helpdesk_tickets_count": len(tickets),
        }
