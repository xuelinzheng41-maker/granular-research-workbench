#!/usr/bin/env python3
"""Validate a read-only component library for agent-led recombination.

A library is a JSON object with a ``components`` list. Each component names one
mechanism that can be combined with another, and records the evidence needed to
judge the combination before a pilot. Validation checks form only: it does not
prove that a cited card/paper exists, that the line/page is accurate, or that a
mechanism is implemented faithfully.

Exit codes: 0 for a valid library, 2 for a malformed or incomplete one.
"""
import argparse
import json
import re
import sys
from pathlib import Path

FIELDS = (
    "id",
    "paper",
    "mechanism",
    "input",
    "output",
    "bottleneck",
    "assumption",
    "cost",
    "known_failure",
    "source",
)
MIN_COMPONENTS = 2
SOURCE_ID_RE = re.compile(r"\b(?:card|paper)\b", re.IGNORECASE)
SOURCE_LOCATOR_RE = re.compile(
    r"\b(?:line|lines|p|pp|page|pages)\.?\s*\d+(?:\s*[-\u2013]\s*\d+)?",
    re.IGNORECASE,
)


def _text(component, key, where):
    value = component.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key}: missing or blank")
    return value.strip()


def _source(value, paper, where):
    if not SOURCE_ID_RE.search(value) and paper.lower() not in value.lower():
        raise ValueError(f"{where}.source: must name a card or paper")
    if not SOURCE_LOCATOR_RE.search(value):
        raise ValueError(f"{where}.source: must include a line or page locator")
    return value


def validate(library):
    """Return a normalized summary or raise ValueError for a malformed library."""
    if not isinstance(library, dict):
        raise ValueError("top-level input must be an object")
    entries = library.get("components")
    if not isinstance(entries, list) or len(entries) < MIN_COMPONENTS:
        raise ValueError(f"components: must list at least {MIN_COMPONENTS} components")
    rows = []
    ids = set()
    for index, entry in enumerate(entries):
        where = f"components[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: must be an object")
        row = {field: _text(entry, field, where) for field in FIELDS}
        row["source"] = _source(row["source"], row["paper"], where)
        if row["id"] in ids:
            raise ValueError(f"{where}.id: duplicate component id {row['id']!r}")
        ids.add(row["id"])
        rows.append(row)
    return dict(
        component_count=len(rows),
        ids=[row["id"] for row in rows],
        components=rows,
        checks={"form": "ok", "unique_ids": "ok", "sources": "ok"},
        limits=(
            "Read-only form validation. It does not verify that the cited card or "
            "paper exists, that the line/page is accurate, or that the mechanism is "
            "implemented faithfully."
        ),
    )


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("library", type=Path)
    args = cli.parse_args(argv)
    try:
        summary = validate(json.loads(args.library.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"component_library: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
