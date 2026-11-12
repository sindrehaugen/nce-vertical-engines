# Security Policy & Enterprise Governance

`nce-vertical-engines` provides domain business logic, ERP/CRM bridges, and IoT integrations for the Neuro-Cognitive Engine (NCE) ecosystem. This document defines supported versions, vulnerability reporting mechanisms, and domain-level enterprise security controls.

---

## Supported Versions

Security updates and vulnerability patches are maintained for the following versions:

| Version | Supported | Status |
| :--- | :--- | :--- |
| **3.4.x** | :white_check_mark: Yes | Current Stable Release (Hardened HTTP Ingress, XML-RPC Defusal & SSRF Egress Gates) |
| **3.3.x** | :white_check_mark: Yes | Maintenance Release (Entra ID MCP Gateway Claims Alignment & Replay Sandbox) |
| **3.0.x**–**3.2.x** | :white_check_mark: Yes | Long-Term Support (LTS) Baseline (Modular Dual-Axis Release) |
| **< 3.0.0** | :x: No | End of Life (Legacy internal prototypes) |

---

## Vulnerability Disclosure Policy

Security issues should be reported directly to our security maintainers rather than through public issues:

1. **Email:** Send full vulnerability descriptions, proof-of-concept exploits, and environment details to **security@sindrehaugen.no** (or via GitHub Private Vulnerability Reporting on `sindrehaugen/nce-vertical-engines`).
2. **Triage SLA:** Initial acknowledgement within **48 hours**, severity classification within **5 business days**.
3. **Patch Window:** Targeted critical patches released within **14 business days**.
4. **Coordinated Disclosure:** 90-day embargo timeline prior to public disclosure.

---

## Domain Security & Cryptographic Governance

Vertical engines operate under strict enterprise defense-in-depth policies:

### 1. Microsoft Entra ID (Azure AD) OIDC & JWKS Cryptographic Token Verification

All standalone vertical servers (`nce-portal-server`, `nce-odoo-server`, `nce-salesforce-server`) and administrative entrypoints verify incoming identities via Microsoft Entra ID (`nce_verticals/security/entra_id.py`):

- **Asymmetric Signature Verification:** Tokens are verified against Microsoft Entra OpenID Connect discovery JWKS endpoints (`https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys`).
- **Cryptographic Algorithms:** Only `RS256` and `ES256` asymmetric algorithms are permitted (`ALLOWED_JWT_ALGORITHMS`). Symmetric algorithms (e.g. `HS256`) and unencrypted tokens are strictly rejected.
- **Strict Claims Checking:** Validation enforces `iss`, `aud`, `exp`, `nbf`, `tid`, and `oid` claims.
- **Bounded JWKS Cache:** In-memory JWKS public keys are cached with bounded TTL (`jwks_cache_ttl_seconds`, default 3,600s) to prevent memory exhaustion and cache poisoning.
- **Role & Group Allowlisting:** Transitive Microsoft Graph security group object IDs and Enterprise Application App Roles are enforced prior to granting access to domain commands.
- **Migration `075` Security Gate:** Schema gate `075_entra_id_security_gate.sql` and `EntraIDHttpMiddleware` validate tenant identity bindings, app role claims, and cryptographic JWKS signatures (`RS256`/`ES256`) on protected `/api/admin/*` routes across both `nce-odoo-server` and `nce-salesforce-server` (while leaving `/healthz`, `/health`, `/ready` probes and HMAC-authenticated `/api/webhooks/*` ingress operational).

### 2. HTTP Ingress Protection & BoundedBodyMiddleware

All standalone ASGI servers (`nce-portal-server`, `nce-odoo-server`, `nce-salesforce-server`) enforce `BoundedBodyMiddleware` from `nce_verticals.security.http_guard`:
- **Hard Request Body Limits:** Enforces `live_max_http_body_bytes()` (configured via `NCE_MAX_HTTP_BODY_BYTES`, default 10 MiB).
- **HTTP 413 Denial-of-Service Defense:** Incoming payloads exceeding the configured ceiling are rejected immediately with `HTTP 413 Payload Too Large` before memory buffering, preventing denial-of-service and memory exhaustion attacks.

### 3. Outbound SSRF & Egress Hardening (validate_outbound_url)

All external HTTP integrations across Odoo, Salesforce, Lucid, NetBox, and geodata adapters pass through `validate_outbound_url`:
- **Private Subnet Blocking:** Rejects RFC 1918 private subnets, loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), and broadcast destinations.
- **Carrier-Grade NAT (CGNAT) Blocking:** Explicitly blocks `100.64.0.0/10` to eliminate traversal of shared carrier and intranet backbones.
- **IPv4-Mapped IPv6 Traversal Protection:** Intercepts and parses IPv4 addresses mapped inside IPv6 formats (e.g. `::ffff:169.254.169.254`), closing cloud metadata exfiltration vectors.

### 4. Odoo XML-RPC Defusal & XXE Protection (defusedxml.xmlrpc)

The Odoo ERP connector routes all XML-RPC communications through `defusedxml.xmlrpc`:
- **Billion Laughs & Quadratic Blowup Mitigation:** Blocks entity expansion and recursive XML entity attacks.
- **XXE Prevention:** Completely blocks XML External Entity references and arbitrary local file inclusion during Odoo XML-RPC serialization and deserialization.

### 5. Workplace Telemetry & Operator Privacy Governance

In adherence to European privacy frameworks (GDPR) and Norwegian labor legislation (*Arbeidsmiljøloven* § 13):

- **Strict Opt-In Default:** Longitudinal operator stress and cognitive load tracking is disabled by default via `NCE_ENABLE_WORKPLACE_TELEMETRY=false`.
- **Fail-Safe Neutral Baselines:**
  - When disabled, NetBox contact evaluation immediately returns `{"status": "telemetry_disabled", "telemetry_enabled": False}` without querying `v3_cognitive_ledger`.
  - Dynamics 365 ingestion yields a constant neutral tensor (`[5.0, 0.0, 5.0, 0.0, 0.0, 0.0]`) and skips writing to cognitive ledgers.
  - Support case stress handlers fail closed without touching operator historical records.
- **Explicit Activation:** Workplace telemetry can only be activated with explicit enterprise agreement and worker council consent.

### 6. Customer Portal C3 External-Scope Confinement

The Customer Portal engine (`nce_verticals/servers/portal.py`) serves external clients and partners outside the corporate boundary:

- **Unprivileged Execution Shell:** Runs as an isolated ASGI application separate from administrative APIs.
- **C3 Security Primitive:** Enforces PostgreSQL Row-Level Security scoped to external partner and customer principals.
- **Strict Allowlist Redaction:** Outbound JSON payloads are filtered through C8 field redaction rules, preventing internal employee notes, margin structures, or partner metadata from crossing the perimeter.
- **Sliding-Window Rate Limiting:** Built-in IP and token rate limiting prevents scraping and brute-force discovery.

### 7. WORM Immutability on Signed Baselines (`sales_signed_baselines`)

Commercial quotes and project baselines require absolute legal immutability:

- **Database-Level Trigger:** PostgreSQL trigger `trg_sales_signed_baselines_worm` intercepts and blocks any `UPDATE` or `DELETE` statement against `sales_signed_baselines`.
- **Tamper-Evident State:** Once a quotation is cryptographically signed and converted to an active baseline, its scope, financial line items, and terms cannot be mutated by application code or administrative maintenance roles.
- **Audit Preservation:** Changes or scope variations require issuing an explicit, sequential change order or amendment record rather than editing historical records.

---

## Security Contact

- **Security Team:** security@sindrehaugen.no
- **PGP Key Fingerprint:** Available upon request or via keybase/DNS TXT records.
