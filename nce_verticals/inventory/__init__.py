"""
nce_verticals/inventory/__init__.py
==========================================
Inventory Engine vertical module (Module 11).

Exports public core functions for stock levels, transfers, reservations,
goods receipt, replenishment, valuation, and RMA handling.
"""

from __future__ import annotations

from nce_verticals.inventory._guard import (
    InventoryDisabledError,
    require_inventory_enabled,
)
from nce_verticals.inventory.forecast import do_forecast_demand
from nce_verticals.inventory.goods_receipt import do_record_goods_receipt
from nce_verticals.inventory.kitting import (
    do_release_kit,
    do_reserve_kit,
)
from nce_verticals.inventory.reconcile import do_reconcile_dead_stock
from nce_verticals.inventory.replenishment import do_recommend_restock
from nce_verticals.inventory.reservation import (
    do_release_stock,
    do_reserve_stock,
)
from nce_verticals.inventory.restock_po import do_create_restock_po
from nce_verticals.inventory.rma import (
    do_dispose_rma_weee,
    do_record_rma,
    do_restock_from_rma,
)
from nce_verticals.inventory.stock import (
    do_record_consumption,
    do_stock_levels,
    do_transfer_stock,
)
from nce_verticals.inventory.transactions import do_valuation
from nce_verticals.inventory.triggers import (
    do_advance_bom_line_to_delivered,
    do_record_goods_receipt_and_evaluate_match,
)
from nce_verticals.inventory.watchers import do_flag_stock_alerts

__all__ = [
    "InventoryDisabledError",
    "do_advance_bom_line_to_delivered",
    "do_create_restock_po",
    "do_dispose_rma_weee",
    "do_flag_stock_alerts",
    "do_forecast_demand",
    "do_record_consumption",
    "do_record_goods_receipt",
    "do_record_goods_receipt_and_evaluate_match",
    "do_record_rma",
    "do_reconcile_dead_stock",
    "do_recommend_restock",
    "do_release_kit",
    "do_release_stock",
    "do_reserve_kit",
    "do_reserve_stock",
    "do_restock_from_rma",
    "do_stock_levels",
    "do_transfer_stock",
    "do_valuation",
    "require_inventory_enabled",
]
