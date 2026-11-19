#!/usr/bin/env python3
"""Compare candidate probes against declared resources; never certifies novelty."""
import argparse
import json
import sys
from pathlib import Path

SOURCES = {"literature", "anomaly", "transfer"}
REVIEW_STATES = {"unsearched", "no_overlap_retrieved", "overlap", "counterexample"}


def text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or blank {key}")
    return value.strip()


def integer(obj, key, *, minimum=1):
    value = obj.get(key)
    if type(value) is not int or value < minimum:
        raise ValueError(f"{key} must be an integer >= {minimum}")
    return value


def names(obj, key):
    value = obj.get(key)
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return {x.strip() for x in value}


def object_field(obj, key):
    value = obj.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def compare(data):
    if not isinstance(data, dict):
        raise ValueError("top-level input must be an object")
    profile = object_field(data, "profile")
    topic = text(profile, "topic")
    available = min(integer(profile, "minutes_this_week"), integer(profile, "probe_limit_minutes"))
    skills = names(profile, "skills")
    resources = names(profile, "resources")
    entries = data.get("candidates")
    if not isinstance(entries, list) or not 2 <= len(entries) <= 3:
        raise ValueError("provide two or three candidates")
    ids, sources, rows = set(), set(), []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("each candidate must be an object")
        key = text(item, "id")
        if key in ids:
            raise ValueError(f"duplicate ID: {key}")
        ids.add(key)
        source = text(item, "source_kind")
        if source not in SOURCES:
            raise ValueError(f"{key}: unknown source_kind: {source}")
        sources.add(source)
        finding = text(item, "prior_status")
        if finding not in REVIEW_STATES:
            raise ValueError(f"{key}: unknown prior_status: {finding}")
        trace = text(item, "search_trace")  # Include search and closest source, or explain why unavailable.
        differences = text(item, "difference")
        yes, no = text(item, "advance_if"), text(item, "stop_if")
        if yes == no:
            raise ValueError(f"{key}: advance_if must differ from stop_if")
        minutes = integer(item, "probe_minutes")
        missing_skills = sorted(names(item, "required_skills") - skills)
        missing_resources = sorted(names(item, "required_resources") - resources)
        reasons = []
        if finding in {"overlap", "counterexample"}:
            reasons.append(f"reported {finding} in the stated scope")
        elif finding == "unsearched":
            reasons.append("prior work is unverified")
        if minutes > available:
            reasons.append(f"probe needs {minutes} min, cap is {available} min")
        if missing_skills:
            reasons.append("missing skills: " + ", ".join(missing_skills))
        if missing_resources:
            reasons.append("missing resources: " + ", ".join(missing_resources))
        rows.append(dict(id=key, source_kind=source, source=text(item, "source"), claim=text(item, "claim"),
                         prior_status=finding, search_trace=trace, difference=differences,
                         risk=text(item, "risk"), first_probe=text(item, "first_probe"),
                         probe_minutes=minutes, advance_if=yes, stop_if=no,
                         decision="hold" if reasons else "eligible_for_probe", reasons=reasons))
    if len(sources) < 2:
        raise ValueError("use at least two source kinds; do not invent one to pass the check")
    return dict(topic=topic, time_cap_minutes=available, candidates=rows,
                eligible_ids=[r["id"] for r in rows if r["decision"] == "eligible_for_probe"],
                limits="Declared constraints only; reported retrieval is not novelty or approval to scaffold.")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("brief", type=Path)
    args = cli.parse_args()
    try:
        result = compare(json.loads(args.brief.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"shortlist: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
