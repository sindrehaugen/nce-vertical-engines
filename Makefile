# NCE Vertical Engines — Automation & Quality Gates
#
# Standard developer and CI workflows.

.PHONY: help test lint fmt fmt-check typecheck clean

help:
	@echo "NCE Vertical Engines"
	@echo ""
	@echo "Targets:"
	@echo "  test       Run test suite with pytest"
	@echo "  lint       Run ruff check + ruff format --check"
	@echo "  typecheck  Run mypy type checking"
	@echo "  fmt        Apply ruff auto-formatting"
	@echo "  fmt-check  Check formatting without modifying files"
	@echo "  clean      Remove temporary files, build caches, and test artifacts"

test:
	pytest tests/

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .

fmt-check:
	ruff format --check .

typecheck:
	mypy nce_verticals/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist build *.egg-info
