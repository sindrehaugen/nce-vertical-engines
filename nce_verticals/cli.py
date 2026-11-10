"""CLI for inspecting and filtering the 23 modular NCE Vertical Engines (`nce-verticals`)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from nce_verticals.registry import (
    ENGINE_REGISTRY,
    VALID_CATEGORIES,
    VALID_TYPES,
    is_engine_installed,
    resolve_enabled_engines,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nce-verticals",
        description="Inspect and filter the 23 NCE Vertical Engines across Type and Business Category axes.",
    )
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser(
        "list",
        help="List registered vertical engines with optional Type and Business Category filters.",
    )
    _add_filter_args(list_parser)
    _add_filter_args(parser)
    return parser


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--type",
        dest="type_filter",
        default=None,
        help=f"Filter by engine type ({', '.join(sorted(VALID_TYPES))})",
    )
    p.add_argument(
        "--category",
        dest="category_filter",
        default=None,
        help=f"Filter by business category ({', '.join(sorted(VALID_CATEGORIES))})",
    )
    p.add_argument(
        "--installed-only",
        action="store_true",
        help="Only include engines whose optional SDK dependencies are currently installed.",
    )
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Format output as JSON.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        active_specs = resolve_enabled_engines(
            enabled_raw=None,
            type_filter=args.type_filter,
            category_filter=args.category_filter,
        )
        matched_specs = resolve_enabled_engines(
            enabled_raw="all",
            type_filter=args.type_filter,
            category_filter=args.category_filter,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    active_slugs = {s.slug for s in active_specs}
    rows: list[dict[str, Any]] = []
    for spec in matched_specs:
        installed = is_engine_installed(spec.slug)
        if args.installed_only and not installed:
            continue
        rows.append(
            {
                "slug": spec.slug,
                "title": spec.title,
                "types": sorted(spec.types),
                "categories": sorted(spec.categories),
                "installed": installed,
                "enabled": spec.slug in active_slugs,
                "requires_schemas": list(spec.requires_schemas),
                "aliases": list(spec.aliases),
            }
        )

    if args.as_json:
        print(json.dumps(rows, indent=2))
        return 0

    header = f"{'SLUG':<20} {'TYPES':<24} {'CATEGORIES':<42} {'INSTALLED':<10} {'ENABLED':<8}"
    print(header)
    print("-" * len(header))
    for r in rows:
        types_str = ",".join(r["types"])
        cats_str = ",".join(r["categories"])
        print(
            f"{r['slug']:<20} {types_str:<24} {cats_str:<42} {str(r['installed']):<10} {str(r['enabled']):<8}"
        )
    print(f"\nTotal matching engines: {len(rows)} / {len(ENGINE_REGISTRY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
