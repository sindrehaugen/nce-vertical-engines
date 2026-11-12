# Changelog

All notable changes to the `nce-vertical-engines` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.4.2] - 2026-11-12

### Security
- **Standalone `nce-odoo-server` & `nce-salesforce-server` Entra ID HTTP Gate (`EntraIDHttpMiddleware`):** Wired pure-ASGI Microsoft Entra ID OIDC/JWKS (`RS256`/`ES256`) bearer verification onto protected `/api/admin/*` routes in `nce_verticals/odoo/app.py` (`nce_verticals.servers.odoo:app`) and `nce_verticals/salesforce/app.py` while keeping `/healthz`, `/health`, and `/ready` container probes unauthenticated and preserving outermost `BoundedBodyMiddleware` HTTP `413` enforcement.

### Changed
- **Odoo & NetBox Registry & Packaging Alignment:** Added `075_entra_id_security_gate` to `odoo` `requires_schemas` in `nce_verticals/registry.py`, added `cryptography>=43.0.0` to the `odoo`, `salesforce`, `type-erp-crm`, `cat-commercial`, and `cat-enterprise-erp` extras in `pyproject.toml`, and documented `netbox`'s shared `001_d365_integrations_and_mappings.sql` wheel-bundled mapping table.
- **Core `v3.4.2` Pin & Lockfile Sync:** Updated `pyproject.toml` to `version = "3.4.2"` and `neuro-cognitive-engine>=3.4.2,<4.0.0`, and regenerated `requirements.lock` cleanly against NCE Core `v3.4.2`.

---

## [3.4.1] - 2026-11-11

### Fixed
- **Overlay Container Healthchecks (`docker-compose.verticals.yml`):** Updated `nce-odoo` (`8011`) and `nce-salesforce` (`8012`) container healthchecks to probe `/healthz` (`200 OK`) matching standalone server routes.
- **`nce_app` Non-Superuser RLS Table & Sequence Grants (`017`, `082`):** Added explicit `GRANT USAGE, SELECT ON SEQUENCE sales_read_model_id_seq TO nce_app` and idempotent `GRANT SELECT, INSERT, UPDATE, DELETE` across vertical tenant RLS tables for strict non-superuser runtime execution.
- **Product Enrichment Namespace Privilege Guard (`nce_verticals/product/enrich.py`):** Guarded optional `public.namespaces` metadata lookup with `has_table_privilege(current_user, 'public.namespaces', 'SELECT')` so `nce_app` transactions never abort on `InsufficientPrivilegeError`.
- **Live Integration Suite Alignment:** Updated post-split integration tests and aligned PEP 508 Core floor to `neuro-cognitive-engine>=3.4.1,<4.0.0`.

---

## [3.4.0] - 2026-11-11

### Added
- **ASGI Ingress Cap (`BoundedBodyMiddleware`):** Integrated `BoundedBodyMiddleware` (`NCE_MAX_HTTP_BODY_BYTES`, default 10 MiB) across all standalone servers (`nce-portal-server`, `nce-odoo-server`, `nce-salesforce-server`), rejecting oversized payloads with HTTP `413 Payload Too Large`.
- **SSRF Outbound Egress Guard (`validate_outbound_url`):** Hardened external integration endpoints across Odoo, Salesforce, NetBox, Lucid, and geodata against private subnets, Carrier-Grade NAT (`100.64.0.0/10`), and IPv4-mapped IPv6 metadata traversal (`::ffff:169.254.169.254`).
- **Odoo XML-RPC Defusal (`defusedxml.xmlrpc`):** Replaced standard XML-RPC parsing with `defusedxml.xmlrpc` in the Odoo ERP connector, mitigating Billion Laughs entity expansion and XXE attacks.
- **Migration `075` Entra ID Security Gate:** Enforced schema gate `075_entra_id_security_gate.sql` ensuring verified tenant claims, app roles, and JWKS algorithm restrictions before runtime initialization.
- **`entra_id` Packaging Extra:** Added dedicated `entra_id` dependency extra to `pyproject.toml` for modular enterprise identity verification.

### Changed
- **Substrate Requirement Alignment:** Aligned Core substrate dependency to `neuro-cognitive-engine>=3.4.0,<4.0.0`.
- **Dual-Axis Classification Consistency:** Maintained exact canonical taxonomy across 5 system types (`core-domain`, `erp-crm`, `infra-iot`, `observability`, `portal`) and 7 business categories (`commercial`, `operations-delivery`, `finance-governance`, `service-support`, `av-it-integrator`, `enterprise-erp`, `field-service-ops`).

### Security
- **Inherited Core Security Architecture:** Full operational alignment with NCE Core v3.4.0 WORM advisory locks, KEK/DEK envelope encryption, and CI security gates.

---

## [3.3.0] - 2026-11-10

### Added
- **Entra ID MCP Gateway Claims Mapper (`nce_verticals/security/entra_id.py`):** Added `extract_mcp_gateway_claims` and `to_mcp_gateway_session` on `EntraPrincipal` mapping verified OIDC claims (`oid`/`sub`/`upn`, `tid`/`namespace_id`, `roles`/`scp`, `nce_allowed_engines`, `nce_tool_exposure_mode`) to canonical `/mcp` gateway sessions.
- **Replay Sandbox Fencing:** Added strict external mutation gating preventing outbound ERP/CRM side effects during memory simulation and replay runs.
- **Contributor License Agreement (`CLA.md`):** Formally codified vertical engines contributor intellectual property, copyright, and patent licensing terms.

### Changed
- **Canonical Dual-Axis Taxonomy Alignment:** Preserved and validated dual-axis classifications across 5 system types (`core-domain`, `erp-crm`, `infra-iot`, `observability`, `portal`) and 7 business categories (`commercial`, `operations-delivery`, `finance-governance`, `service-support`, `av-it-integrator`, `enterprise-erp`, `field-service-ops`).

---

## [3.1.0] - 2026-11-10

### Added
- **Migration `082` WORM Trigger & Composite Tenant Indexes:** Added database-level trigger `trg_sales_signed_baselines_worm` enforcing Write-Once-Read-Many immutability on `sales_signed_baselines`. Added composite performance indexes on `(namespace_id, quote_id)`, `(namespace_id, status)` on `field_tech_work_orders`, and `(namespace_id, entity, is_deleted)` on `sales_read_model`.
- **Project REST Parity Routes (`nce_verticals/admin_handlers/project.py`):** Expanded administrative API surface with complete parity for project stage gates, milestone tracking, and task allocations.
- **Sales & Project Live Bridge Opt-In:** Added verified live bridge synchronization between signed sales quotes and downstream project initialization with confirmation gates.

### Changed
- **Entra ID JWKS Verification Hardening (`nce_verticals/security/entra_id.py`):** Added strict RS256/ES256 cryptographic verification against Microsoft Entra ID JWKS endpoints, bounded TTL caching, and group/role claim enforcement.
- **Dual-Axis Registry Refinements:** Streamlined dependency resolution across all 22 modular engines with topological sorting of prerequisite SQL schemas.

---

## [3.0.1] - 2026-11-10

### Added
- **Dual-Axis Classification & Filtering:** Formalized Axis 1 (5 system types: `core-domain`, `erp-crm`, `infra-iot`, `observability`, `portal`) and Axis 2 (7 business categories: `commercial`, `operations-delivery`, `finance-governance`, `service-support`, `av-it-integrator`, `enterprise-erp`, `field-service-ops`).
- **Selective Installation Extras:** Added packaging extras for individual engines, type filters (`type-*`), category filters (`cat-*`), and `all`.
- **Packaging Entry-Point Discovery:** Registered individual engine plugins and unified `VerticalEnginesPlugin` under the `nce.plugins` entry-point group.

---

## [3.0.0] - 2026-11-10

### Added
- **Initial Modular Extraction:** Decoupled 22 vertical business and IT integration engines from the monolithic NCE core into an independent extension package.
- **22 Modular Vertical Engines:**
  - Commercial & Core: Product Catalog (`product`), Procurement & TCO (`procurement`), Agreements & Rebates (`agreements`), Vendors & Contractors (`vendors`), Sales & Dealroom (`sales`), System Design & FL (`system_design`), Project Execution (`project`), Economy & Accounting (`economy`), Warehouse & Inventory (`inventory`).
  - Delivery, Ops & IoT: Asset Lifecycle & Telemetry (`assets`), Support & SLA Clocks (`support`), Staff & Capacity Allocator (`resources`), Field Tech Work Orders (`field_tech`), NetBox DCIM / IPAM (`netbox`).
  - Intelligence, Governance & Connectors: HR & Skills Matrix (`hr`), Marketing & Case Studies (`marketing`), Business Insights (`business_insights`), Customer Portal (`customer_portal`), Dynamics 365 Sync (`dynamics365`), Diagnostics Profiler (`diagnostics`), Odoo ERP Connector (`odoo`), Salesforce CRM (`salesforce`).
- **Packaged Standalone ASGI Servers:** Added runnable servers for Portal (`nce-portal-server`), Odoo (`nce-odoo-server`), and Salesforce (`nce-salesforce-server`).
