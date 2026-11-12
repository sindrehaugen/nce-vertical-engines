"""
tests/expected_tenant_rls_table_count.py
=========================================
Single source of truth for the vertical-engines forced-RLS tenant table count:
``len(VerticalEnginesPlugin().get_tenant_rls_tables()) == 96``
(18 shared vertical-spine tables + 78 per-engine tables across migrations 001..082).

In v3.4.3, Core's ``nce.event_log.EXPECTED_TENANT_RLS_TABLES`` was trimmed strictly
to Pure-Core forced-RLS tables, while vertical engines declare their forced-RLS
tables dynamically through ``VerticalEnginesPlugin.get_tenant_rls_tables()``.
"""

from __future__ import annotations

EXPECTED_TENANT_RLS_TABLE_COUNT = 96
