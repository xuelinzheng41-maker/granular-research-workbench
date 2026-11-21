#!/usr/bin/env python3
"""Validate a read-only baseline registry for performance pilots.

A registry is a JSON object with a ``baselines`` list. Each entry records one
comparison arm and the fairness facts needed before a pilot: where it comes
from, how it is implemented, its budget and parameters, and whether it is a
base method, a naive concatenation, or a random control. Validation checks form
only: it does not prove that the implementation matches the cited source or
that the budgets are actually equal at runtime.

Exit codes: 0 for a valid registry, 2 for a malformed or incomplete one.
"""
import argparse
import json
import sys
from pathlib import Path

FIELDS = ("id", "source", "implementation", "budget", "params", "role")
ROLES = ("base", "naive", "random")
REQUIRED_ROLES = ("naive", "random")
MIN_BASELINES = 2


def _text(entry, key, where):
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key}: missing or blank")
    return value.strip()


def validate(registry):
    """Return a normalized summary or raise ValueError for a malformed registry."""
    if not isinstance(registry, dict):
        raise ValueError("top-level input must be an object")
    entries = registry.get("baselines")
    if not isinstance(entries, list) or len(entries) < MIN_BASELINES:
        raise ValueError(f"baselines: must list at least {MIN_BASELINES} entries")
    rows = []
    ids = set()
    for index, entry in enumerate(entries):
        where = f"baselines[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: must be an object")
        row = {field: _text(entry, field, where) for field in FIELDS}
        if row["role"] not in ROLES:
            raise ValueError(f"{where}.role: must be one of " + ", ".join(ROLES))
        if row["id"] in ids:
            raise ValueError(f"{where}.id: duplicate baseline id {row['id']!r}")
        ids.add(row["id"])
        rows.append(row)
    present = {row["role"] for row in rows}
    for role in REQUIRED_ROLES:
        if role not in present:
            raise ValueError(f"baselines: at least one {role} entry is required")
    return dict(
        baseline_count=len(rows),
        ids=[row["id"] for row in rows],
        roles=[row["role"] for row in rows],
        role_counts={role: sum(row["role"] == role for row in rows) for role in ROLES},
        baselines=rows,
        checks={"form": "ok", "unique_ids": "ok", "required_roles": "ok"},
        limits=(
            "Read-only form validation. It does not verify that an implementation "
            "matches its source or that every arm really uses the same budget and "
            "parameters."
        ),
    )


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("registry", type=Path)
    args = cli.parse_args(argv)
    try:
        summary = validate(json.loads(args.registry.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"baseline_registry: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
