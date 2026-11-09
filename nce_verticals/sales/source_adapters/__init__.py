"""
nce_verticals/sales/source_adapters/__init__.py
========================================================
Source adapters for the Sales vertical module.
"""

from nce_verticals.sales.source_adapters.d365 import SalesD365SyncEngine

__all__ = ["SalesD365SyncEngine"]
