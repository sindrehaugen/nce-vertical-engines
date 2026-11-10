# Contributing to NCE Vertical Engines

Thank you for your interest in contributing to **NCE Vertical Engines**! This project houses the 23 domain-specific business engines, ERP/CRM enterprise connectors, and IoT device controllers built on top of the Neuro-Cognitive Engine (`nce`) substrate.

---

## Development Setup

The repository uses Python 3.10+ (tested across Python 3.10, 3.11, and 3.12).

### 1. Environment Setup

```bash
git clone https://github.com/sindrehaugen/nce-vertical-engines.git
cd nce-vertical-engines

python3 -m venv .venv
source .venv/bin/activate
```

### 2. Installing Extras

The vertical engines package is organized into modular extras. For development, install with the `dev` extra (and optionally specific engines or `all`):

```bash
# Install package in editable mode with development tools
pip install -e ".[dev]"

# Or install with all 23 engine dependencies
pip install -e ".[all,dev]"

# Or install for a specific system type or business category
pip install -e ".[type-erp-crm,dev]"
pip install -e ".[cat-commercial,dev]"
```

---

## Dual-Axis Registry Rules

All engines are declared in `nce_verticals/registry.py` under `ENGINE_REGISTRY`. When contributing or modifying an engine:

1. **Dual-Axis Classification:** Every engine must specify:
   - At least one valid **Type** from `VALID_TYPES`: `core-domain`, `erp-crm`, `infra-iot`, `observability`, `portal`.
   - At least one valid **Business Category** from `VALID_CATEGORIES`: `commercial`, `operations-delivery`, `finance-governance`, `service-support`, `av-it-integrator`, `enterprise-erp`, `field-service-ops`.
2. **Schema Prerequisites (`requires_schemas`):** If an engine references database tables owned by another engine, it **must** declare those dependencies under `requires_schemas`. For example:
   - `support` requires `assets`
   - `assets` requires `product`, `inventory`
   - `project` requires `sales`
   - `agreements` requires `sales`
   - `economy` requires `sales`, `agreements`
3. **Topological Order:** The registry automatically sorts schema migrations using `resolve_schema_dependencies`. Never bypass or introduce circular dependencies between schemas.

---

## Lazy Loading Invariants

`VerticalEnginesPlugin` (`nce_verticals/plugin.py`) dynamically mounts vertical tools and endpoints based on active runtime filters (`NCE_ENABLED_ENGINES`, `NCE_ENGINE_TYPE_FILTER`, and `NCE_ENGINE_CATEGORY_FILTER`).

- **Lazy Import Guarantees:** Do not import heavy third-party SDKs (such as `pynetbox`, `msal`, `simple_salesforce`, or `scipy`) at the top level of `nce_verticals/plugin.py` or `nce_verticals/__init__.py`.
- **Graceful Fallbacks:** If an optional SDK extra is not installed for an enabled engine, the engine handler must fail gracefully or skip registration rather than crashing the NCE host application.
- **Support Package Bundling:** The shared-core support packages (`documents`, `geodata`, `legal_entities`, `notifications`, `sites`, `shared`, `security`, `servers`) are always bundled inside the wheel and available to all engines.

---

## Testing & Quality Assurance

Before submitting a pull request, ensure all linting, typing, and test gates pass:

### 1. Code Style & Linting

```bash
# Lint codebase with Ruff
ruff check nce_verticals tests/test_registry_filters.py

# Format check
ruff format --check nce_verticals tests/
```

### 2. Static Type Checking

```bash
mypy nce_verticals
```

### 3. Test Suites

```bash
# Run unit and registry tests
pytest tests/test_registry_filters.py
pytest tests/

# Run integration tests against database
pytest -m integration
```

---

## Pull Request Checklist

- [ ] All new tools/routes have corresponding tests.
- [ ] Any new schema migrations follow numbered naming conventions (e.g. `083_...sql`) and include WORM triggers where applicable.
- [ ] No circular dependencies introduced in `nce_verticals/registry.py`.
- [ ] `ruff check` and `mypy` pass with zero errors.
