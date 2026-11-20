#!/usr/bin/env python3
"""Gate a performance pilot or full record.

The gate joins mean gain over the best baseline with a declared effect size, a
remove-one ablation drop, a random-control baseline, paired uncertainty, and
optional coverage/runtime constraints. It is a filter, not a benchmark.

Top-level input:
  metric        non-blank string
  stage         "pilot" (every seed list needs at least 3 entries) or
                "full" (every seed list needs at least 5 entries)
  threshold     positive number, default 0.01
  min_datasets  integer >= 2, default 3
  constraints   optional object with min_coverage (0 < n <= 1) and/or
                max_runtime_s (n > 0)
  datasets      at least min_datasets objects, each with:
                  name       unique non-blank string
                  hybrid     seed list
                  baselines  object with at least two lists, including
                             naive_concat and random_control
                  ablations  object with at least one seed list
                  coverage   0..1, required when constraints.min_coverage is set
                  runtime_s  positive seconds, required when
                             constraints.max_runtime_s is set

Seed lists for hybrid, every baseline, and every ablation must share one length.
Each row reports hybrid_sd and delta_ci95, the paired 95% t-interval of
hybrid - best baseline. Exit 0 means promising, 3 means weak/reject, 2 means
malformed input.
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

STAGES = {"pilot": 3, "full": 5}
MANDATORY_BASELINES = ("naive_concat", "random_control")
CONSTRAINT_KEYS = ("min_coverage", "max_runtime_s")
T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
    14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
    20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def text(obj, key, label=None):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or blank {label or key}")
    return value.strip()


def real(obj, key, label=None):
    name = label or key
    value = obj.get(key)
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def optional_real(obj, key, label=None):
    if obj.get(key) is None:
        return None
    return real(obj, key, label)


def number_list(obj, key, minimum, stage):
    value = obj.get(key)
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(
            f"{key} must be a list of at least {minimum} numbers for stage={stage}"
        )
    out = []
    for item in value:
        if type(item) not in (int, float) or not math.isfinite(float(item)):
            raise ValueError(f"{key} must contain only finite numbers")
        out.append(float(item))
    return out


def seed_block(container, key, minimum, stage):
    block = container.get(key)
    if not isinstance(block, dict) or not block:
        raise ValueError(f"{key} must be a non-empty object of seed lists")
    return block


def parse_constraints(data):
    raw = data.get("constraints")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("constraints must be an object")
    unknown = sorted(set(raw) - set(CONSTRAINT_KEYS))
    if unknown:
        raise ValueError(f"constraints has unsupported keys: {', '.join(unknown)}")
    out = {}
    if "min_coverage" in raw:
        value = real(raw, "min_coverage", "constraints.min_coverage")
        if not 0.0 < value <= 1.0:
            raise ValueError("constraints.min_coverage must be in (0, 1]")
        out["min_coverage"] = value
    if "max_runtime_s" in raw:
        value = real(raw, "max_runtime_s", "constraints.max_runtime_s")
        if value <= 0.0:
            raise ValueError("constraints.max_runtime_s must be positive")
        out["max_runtime_s"] = value
    return out


def control_spec(data):
    raw = data.get("random_control_spec")
    if not isinstance(raw, dict):
        raise ValueError("random_control_spec must be an object")
    method = text(raw, "method", "random_control_spec.method")
    seed = raw.get("seed")
    if type(seed) is not int or seed < 0:
        raise ValueError("random_control_spec.seed must be a non-negative integer")
    matched = text(raw, "matched_on", "random_control_spec.matched_on")
    return {"method": method, "seed": seed, "matched_on": matched}


def paired_ci95(diffs):
    """Two-sided 95% t-interval of the mean paired difference."""
    mean = statistics.fmean(diffs)
    if len(diffs) < 2:
        return mean, mean
    half = T95.get(len(diffs) - 1, 1.96) * statistics.stdev(diffs) / math.sqrt(len(diffs))
    return mean - half, mean + half


def compare(data):
    if not isinstance(data, dict):
        raise ValueError("top-level input must be an object")
    metric = text(data, "metric")
    stage = text(data, "stage").lower()
    if stage not in STAGES:
        raise ValueError("stage must be pilot or full")
    minimum = STAGES[stage]
    threshold = data.get("threshold", 0.01)
    if type(threshold) not in (int, float) or not math.isfinite(float(threshold)) or threshold <= 0:
        raise ValueError("threshold must be a positive number")
    threshold = float(threshold)
    min_datasets = data.get("min_datasets", 3)
    if type(min_datasets) is not int or min_datasets < 2:
        raise ValueError("min_datasets must be an integer >= 2")
    control = control_spec(data)
    constraints = parse_constraints(data)
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
        hybrid = number_list(ds, "hybrid", minimum, stage)
        baselines = ds.get("baselines")
        if not isinstance(baselines, dict) or len(baselines) < 2:
            raise ValueError(f"{name}: baselines must contain at least two entries")
        for key in MANDATORY_BASELINES:
            if key not in baselines:
                raise ValueError(f"{name}: baselines must include {key}")
        baseline_values = {}
        for key, values in baselines.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{name}: baseline names must be non-empty")
            vals = number_list(baselines, key, minimum, stage)
            if len(vals) != len(hybrid):
                raise ValueError(f"{name}: baseline {key} length differs from hybrid")
            if key == "random_control" and len(set(vals)) < 2:
                raise ValueError(f"{name}: random_control must vary across seeds; a constant vector is not a control")
            baseline_values[key] = vals
        ablations = seed_block(ds, "ablations", 1, stage)
        ablation_values = {}
        for key, values in ablations.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{name}: ablation names must be non-empty")
            vals = number_list(ablations, key, minimum, stage)
            if len(vals) != len(hybrid):
                raise ValueError(f"{name}: ablation {key} length differs from hybrid")
            ablation_values[key] = vals

        coverage = optional_real(ds, "coverage", f"{name}.coverage")
        runtime_s = optional_real(ds, "runtime_s", f"{name}.runtime_s")
        if "min_coverage" in constraints and coverage is None:
            raise ValueError(f"{name}: coverage is required when constraints.min_coverage is set")
        if "max_runtime_s" in constraints and runtime_s is None:
            raise ValueError(f"{name}: runtime_s is required when constraints.max_runtime_s is set")
        if coverage is not None and not 0.0 <= coverage <= 1.0:
            raise ValueError(f"{name}: coverage must be in [0, 1]")
        if runtime_s is not None and runtime_s <= 0.0:
            raise ValueError(f"{name}: runtime_s must be positive")

        baseline_means = {key: statistics.fmean(vals) for key, vals in baseline_values.items()}
        ablation_means = {key: statistics.fmean(vals) for key, vals in ablation_values.items()}
        hybrid_mean = statistics.fmean(hybrid)
        hybrid_sd = statistics.stdev(hybrid)
        best_name = max(baseline_means, key=baseline_means.get)
        best_mean = baseline_means[best_name]
        delta = hybrid_mean - best_mean
        ci_low, ci_high = paired_ci95([h - b for h, b in zip(hybrid, baseline_values[best_name])])
        ablation_drop = max(hybrid_mean - value for value in ablation_means.values())
        random_margin = hybrid_mean - baseline_means["random_control"]
        constraint_pass = True
        if "min_coverage" in constraints and coverage < constraints["min_coverage"]:
            constraint_pass = False
        if "max_runtime_s" in constraints and runtime_s > constraints["max_runtime_s"]:
            constraint_pass = False
        rows.append(dict(
            dataset=name,
            hybrid_mean=round(hybrid_mean, 6),
            hybrid_sd=round(hybrid_sd, 6),
            best_baseline=best_name,
            best_baseline_mean=round(best_mean, 6),
            delta=round(delta, 6),
            delta_ci95=[round(ci_low, 6), round(ci_high, 6)],
            delta_ci95_excludes_zero=bool(ci_low > 0.0 or ci_high < 0.0),
            delta_pass=bool(delta >= threshold),
            random_control_mean=round(baseline_means["random_control"], 6),
            random_control_margin=round(random_margin, 6),
            random_control_pass=bool(random_margin >= 0.0),
            ablation_drop=round(ablation_drop, 6),
            ablation_pass=bool(ablation_drop >= threshold),
            ablation_means={key: round(value, 6) for key, value in ablation_means.items()},
            coverage=coverage,
            runtime_s=runtime_s,
            constraint_pass=bool(constraint_pass),
        ))
    pass_count = sum(1 for row in rows if row["delta_pass"])
    required = math.ceil(2 * len(rows) / 3)
    ablation_all = all(row["ablation_pass"] for row in rows)
    random_all = all(row["random_control_pass"] for row in rows)
    constraints_all = all(row["constraint_pass"] for row in rows)
    ci_positive = all(row["delta_ci95"][0] > 0.0 for row in rows)
    if pass_count >= required and ablation_all and random_all and constraints_all and ci_positive:
        verdict = "promising"
    elif pass_count >= required or any(row["delta"] > 0 for row in rows):
        verdict = "weak"
    else:
        verdict = "reject"
    return dict(
        metric=metric,
        stage=stage,
        min_samples=minimum,
        threshold=threshold,
        datasets=len(rows),
        required_dataset_wins=required,
        dataset_wins=pass_count,
        ablation_all_pass=ablation_all,
        random_control_all_pass=random_all,
        random_control_spec=control,
        delta_ci95_positive=ci_positive,
        constraints={
            "min_coverage": constraints.get("min_coverage"),
            "max_runtime_s": constraints.get("max_runtime_s"),
        },
        constraints_all_pass=constraints_all,
        verdict=verdict,
        rows=rows,
        limits="Pilot/full gate only; it does not replace a full benchmark, a held-out test, or a declared paired test.",
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
