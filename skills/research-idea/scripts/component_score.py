#!/usr/bin/env python3
"""Rank component pairs with a read-only compatibility score.

A record is a JSON object with a ``pairs`` list. Each pair has ``id``, exactly
two ``components``, ``baseline_strength``, and ``expected_gain``; each component
has ``id``, ``bottleneck``, ``cost``, and ``data_ready``. Scores are
complementarity, feasibility, expected_effect, and total (0.4/0.3/0.3), rounded
to three decimals and sorted by total then id. A ranking aid, not evidence.
Exit codes: 0 for a valid record, 2 for a malformed one.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

WEIGHTS = {"complementarity": 0.4, "feasibility": 0.3, "expected_effect": 0.3}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _text(entry, key, where):
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}.{key}: missing or blank")
    return value.strip()


def _number(entry, key, where, low=None, high=None):
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}.{key}: must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{where}.{key}: must be finite")
    if low is not None and value < low:
        raise ValueError(f"{where}.{key}: must be >= {low}")
    if high is not None and value > high:
        raise ValueError(f"{where}.{key}: must be <= {high}")
    return value


def _tokens(value):
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in STOPWORDS}


def _complementarity(left, right):
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens and not right_tokens:
        return 0.0 if left.lower().split() == right.lower().split() else 1.0
    union = left_tokens | right_tokens
    return 1.0 - len(left_tokens & right_tokens) / len(union)


def _component(entry, where):
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: must be an object")
    extra = sorted(set(entry) - {"id", "bottleneck", "cost", "data_ready"})
    if extra:
        raise ValueError(f"{where}.{extra[0]}: unknown field")
    data_ready = entry.get("data_ready")
    if not isinstance(data_ready, bool):
        raise ValueError(f"{where}.data_ready: must be true or false")
    return {"id": _text(entry, "id", where),
            "bottleneck": _text(entry, "bottleneck", where),
            "cost": _number(entry, "cost", where, low=0),
            "data_ready": data_ready}


def score_pair(pair, where="pair"):
    """Return one normalized pair row or raise ValueError for malformed input."""
    if not isinstance(pair, dict):
        raise ValueError(f"{where}: must be an object")
    extra = sorted(set(pair) - {"id", "components", "baseline_strength", "expected_gain"})
    if extra:
        raise ValueError(f"{where}.{extra[0]}: unknown field")
    pair_id = _text(pair, "id", where)
    components = pair.get("components")
    if not isinstance(components, list) or len(components) != 2:
        raise ValueError(f"{where}.components: must list exactly two components")
    left, right = (_component(components[0], f"{where}.components[0]"),
                   _component(components[1], f"{where}.components[1]"))
    baseline_strength = _number(pair, "baseline_strength", where, low=0, high=1)
    expected_gain = _number(pair, "expected_gain", where, low=0, high=1)
    ready_fraction = sum(c["data_ready"] for c in (left, right)) / 2
    scores = {
        "complementarity": _complementarity(left["bottleneck"], right["bottleneck"]),
        "feasibility": ready_fraction / (1.0 + left["cost"] + right["cost"]),
        "expected_effect": expected_gain * baseline_strength,
    }
    scores["total"] = sum(WEIGHTS[key] * scores[key] for key in WEIGHTS)
    return {
        "id": pair_id,
        "component_ids": [left["id"], right["id"]],
        "scores": {key: round(value, 3) for key, value in scores.items()},
    }


def validate(record):
    """Return a ranked summary or raise ValueError for a malformed record."""
    if not isinstance(record, dict):
        raise ValueError("top-level input must be an object")
    pairs = record.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("pairs: must list at least one pair")
    rows, ids = [], set()
    for index, pair in enumerate(pairs):
        row = score_pair(pair, f"pairs[{index}]")
        if row["id"] in ids:
            raise ValueError(f"pairs[{index}].id: duplicate pair id {row['id']!r}")
        ids.add(row["id"])
        rows.append(row)
    rows.sort(key=lambda row: (-row["scores"]["total"], row["id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {
        "pair_count": len(rows),
        "weights": WEIGHTS,
        "ranking": rows,
        "checks": {"form": "ok", "ordering": "total_desc_id_asc"},
        "limits": (
            "Ranking aid only, not evidence: it checks declared form, not that "
            "the pair works or that the numbers are real. It is not a pilot or a performance claim."
        ),
    }


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("record", type=Path)
    args = cli.parse_args(argv)
    try:
        summary = validate(json.loads(args.record.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"component_score: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
