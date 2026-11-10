# Changelog

All notable changes to the `nce-vertical-engines` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.1.0] - 2026-11-10

### Added
- **Migration `082` WORM Trigger & Composite Tenant Indexes:** Added database-level trigger `trg_sales_signed_baselines_worm` enforcing Write-Once-Read-Many immutability on `sales_signed_baselines`. Added composite performance indexes on `(namespace_id, quote_id)`, `(namespace_id, status)` on `field_tech_work_orders`, and `(namespace_id, entity, is_deleted)` on `sales_read_model`.
- **Project REST Parity Routes (`nce_verticals/admin_handlers/project.py`):** Expanded administrative API surface with complete parity for project stage gates, milestone tracking, and task allocations.
- **Sales & Project Live Bridge Opt-In:** Added verified live bridge synchronization between signed sales quotes and downstream project initialization with confirmation gates.

### Changed
- **Entra ID JWKS Verification Hardening (`nce_verticals/security/entra_id.py`):** Added strict RS256/ES256 cryptographic verification against Microsoft Entra ID JWKS endpoints, bounded TTL caching, and group/role claim enforcement.
- **Dual-Axis Registry Refinements:** Streamlined dependency resolution across all 23 modular engines with topological sorting of prerequisite SQL schemas.

---

## [3.0.1] - 2026-11-10

### Added
- **Dual-Axis Classification & Filtering:** Formalized Axis 1 (5 system types: `core-domain`, `erp-crm`, `infra-iot`, `observability`, `portal`) and Axis 2 (7 business categories: `commercial`, `operations-delivery`, `finance-governance`, `service-support`, `av-it-integrator`, `enterprise-erp`, `field-service-ops`).
- **Selective Installation Extras:** Added packaging extras for individual engines, type filters (`type-*`), category filters (`cat-*`), and `all`.
- **Packaging Entry-Point Discovery:** Registered individual engine plugins and unified `VerticalEnginesPlugin` under the `nce.plugins` entry-point group.

---

## [3.0.0] - 2026-11-10

### Added
- **Initial Modular Extraction:** Decoupled 23 vertical business and IT integration engines from the monolithic NCE core into an independent extension package.
- **23 Modular Vertical Engines:**
  - Commercial & Core: Product Catalog (`product`), Procurement & TCO (`procurement`), Agreements & Rebates (`agreements`), Vendors & Contractors (`vendors`), Sales & Dealroom (`sales`), System Design & FL (`system_design`), Project Execution (`project`), Economy & Accounting (`economy`), Warehouse & Inventory (`inventory`).
  - Delivery, Ops & IoT: Asset Lifecycle & Telemetry (`assets`), Support & SLA Clocks (`support`), Staff & Capacity Allocator (`resources`), Field Tech Work Orders (`field_tech`), NetBox DCIM / IPAM (`netbox`), Lighting DALI-2 & Glamox (`lighting_dali`).
  - Intelligence, Governance & Connectors: HR & Skills Matrix (`hr`), Marketing & Case Studies (`marketing`), Business Insights (`business_insights`), Customer Portal (`customer_portal`), Dynamics 365 Sync (`dynamics365`), Diagnostics Profiler (`diagnostics`), Odoo ERP Connector (`odoo`), Salesforce CRM (`salesforce`).
- **Packaged Standalone ASGI Servers:** Added runnable servers for Portal (`nce-portal-server`), Odoo (`nce-odoo-server`), Salesforce (`nce-salesforce-server`), and Lighting DALI (`nce-lighting-dali-server`).
