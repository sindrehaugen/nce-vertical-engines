-- 074_product_catalog_successor.sql
-- Wave R-13 Product Catalog EOL watcher columns:
-- Successor SKU and lifecycle confidence on product_catalog (Charter §13 Item 7 / Q-12)
-- ============================================================================

-- 2. Successor SKU and lifecycle confidence on product_catalog (Charter §13 Item 7)
ALTER TABLE product_catalog ADD COLUMN IF NOT EXISTS successor_sku TEXT;
ALTER TABLE product_catalog ADD COLUMN IF NOT EXISTS lifecycle_confidence DOUBLE PRECISION;
