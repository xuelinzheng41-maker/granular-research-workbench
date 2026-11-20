#!/usr/bin/env python3
"""Gate a performance pilot: mean gain over the best baseline plus an ablation drop."""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path


def text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or blank {key}")
    return value.strip()


def number_list(obj, key, minimum=3):
    value = obj.get(key)
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{key} must be a list of at least {minimum} numbers")
    if any(type(x) not in (int, float) for x in value):
        raise ValueError(f"{key} must contain only numbers")
    return [float(x) for x in value]


def compare(data):
    if not isinstance(data, dict):
        raise ValueError("top-level input must be an object")
    metric = text(data, "metric")
    threshold = data.get("threshold", 0.01)
    if type(threshold) not in (int, float) or threshold <= 0:
        raise ValueError("threshold must be a positive number")
    min_datasets = data.get("min_datasets", 3)
    if type(min_datasets) is not int or min_datasets < 2:
        raise ValueError("min_datasets must be an integer >= 2")
    entries = data.get("datasets")
    if not isinstance(entries, list) or len(entries) < min_datasets:
        raise ValueError(f"provide at least {min_datasets} datasets")
    rows = []
    names = set()
    for ds in entries:
        if not isinstance(ds, dict):
            raise ValueError("each dataset must be an object")
        name = text(ds, "name")
        if name in names:
            raise ValueError(f"duplicate dataset: {name}")
        names.add(name)
        hybrid = number_list(ds, "hybrid")
        baselines = ds.get("baselines")
        if not isinstance(baselines, dict) or len(baselines) < 2:
            raise ValueError(f"{name}: baselines must contain at least two entries")
        if "naive_concat" not in baselines:
            raise ValueError(f"{name}: baselines must include naive_concat")
        baseline_means = {}
        for key, values in baselines.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{name}: baseline names must be non-empty")
            vals = number_list(baselines, key)
            if len(vals) != len(hybrid):
                raise ValueError(f"{name}: {key} length differs from hybrid")
            baseline_means[key] = statistics.fmean(vals)
        ablations = ds.get("ablations")
        if not isinstance(ablations, dict) or not ablations:
            raise ValueError(f"{name}: provide at least one ablation")
        ablation_means = {}
        for key, values in ablations.items():
            vals = number_list(ablations, key)
            if len(vals) != len(hybrid):
                raise ValueError(f"{name}: ablation {key} length differs from hybrid")
            ablation_means[key] = statistics.fmean(vals)
        hybrid_mean = statistics.fmean(hybrid)
        best_name = max(baseline_means, key=baseline_means.get)
        best_mean = baseline_means[best_name]
        delta = hybrid_mean - best_mean
        ablation_drop = max(hybrid_mean - value for value in ablation_means.values())
        rows.append(dict(
            dataset=name,
            hybrid_mean=round(hybrid_mean, 6),
            best_baseline=best_name,
            best_baseline_mean=round(best_mean, 6),
            delta=round(delta, 6),
            delta_pass=delta >= float(threshold),
            ablation_drop=round(ablation_drop, 6),
            ablation_pass=ablation_drop >= float(threshold),
            ablation_means={key: round(value, 6) for key, value in ablation_means.items()},
        ))
    pass_count = sum(1 for row in rows if row["delta_pass"])
    required = math.ceil(2 * len(rows) / 3)
    ablation_all = all(row["ablation_pass"] for row in rows)
    if pass_count >= required and ablation_all:
        verdict = "promising"
    elif pass_count >= required:
        verdict = "weak"
    elif any(row["delta"] > 0 for row in rows):
        verdict = "weak"
    else:
        verdict = "reject"
    return dict(
        metric=metric,
        threshold=float(threshold),
        datasets=len(rows),
        required_dataset_wins=required,
        dataset_wins=pass_count,
        ablation_all_pass=ablation_all,
        verdict=verdict,
        rows=rows,
        limits="Pilot gate only; it does not replace a full benchmark or a held-out test.",
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pilot", type=Path)
    args = cli.parse_args()
    try:
        result = compare(json.loads(args.pilot.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"performance_gate: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "promising" else 3


if __name__ == "__main__":
    sys.exit(main())
