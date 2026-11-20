# Performance track (primary mode)

This is the primary research direction: combine complementary mechanisms into a new algorithm or optimization and test whether it beats strong baselines under a fixed budget. The audit track remains available for definition/theorem checks, but it is not the main line.

## When to use it

Use performance mode when the candidate claims that a new algorithm or a component recombination improves a metric under a fixed budget. The agent chooses the components after reading the paper cards; the user supplies constraints, not a combination direction. Do not use this mode for theorem/definition audits; those remain audit mode.

## Required brief fields

Set top-level `mode` to `performance`. Every candidate needs a `performance` object with:

- `base_methods`: at least two methods being combined or compared
- `components`: at least two mechanisms, not just module names
- `component_sources`: required object mapping every declared component to a non-empty source
- `rejected_pairs`: required list of at least two rejected combinations, each with a reason
- `anchors`: required list of at least two anchor objects, each with a source and why it supports the claim
- `refutation`: required object with a non-empty queries list and a non-empty coverage boundary
- `integration`: where and how the components interact
- `expected_gain`: a numeric target, not `better`
- `baselines`: at least two, including the stronger base and a naive concatenation
- `datasets`: at least two, with a fixed split and seed policy
- `metrics`: primary and secondary metrics
- `ablation`: at least one remove-one or random-component control
- `compute_budget_minutes`: full pilot budget
- `kill_if`: the condition that ends the candidate

The JSON example is [`performance-brief.json`](../skills/research-idea/examples/performance-brief.json). `shortlist.py` validates these fields when mode is `performance`; it does not certify that the gain is real.

### `component_sources` (required)

`component_sources` is an object, not a list. Each key is an exact component name from `components`; each value is a non-empty string naming the source card or paper and what was read from it.

- Every declared component must be covered exactly once; a missing component is an error.
- An undeclared key is rejected as a typo, not silently ignored.
- Blank keys and blank values are rejected.
- This records the audit trail. It does not prove the source exists or that the component is implemented faithfully.

### `rejected_pairs` (required)

`rejected_pairs` is a list with at least two objects. Each object needs a non-blank `pair` and a non-blank `reason`.

- A list, not an object.
- Fewer than two entries is an error.
- Duplicate pairs are rejected case-insensitively.
- A reason should name the blocking issue: same bottleneck, one component subsumes the other, unavailable interface, hidden hyperparameter, budget mismatch, or a result that would only be a definitional audit.

### `anchors` and `refutation` (required)

`anchors` is a list of at least two objects. Each object needs a non-blank `source` and a non-blank `why`; the source names the paper card or paper and the locator or section read, and `why` says what that source supports. This is the checklist evidence, not a replacement for the free-form `search_trace`.

`refutation` is an object with a non-empty `queries` list and a non-blank `coverage` string. `queries` records the mechanism keywords actually used with the refutation search; `coverage` states what corpus, cards, or indexes were searched and what was not. An empty object, empty query list, or blank coverage is an error.

Both fields record what was checked and its boundary. The validator does not run the search or prove that the cited sources exist. A `search_trace` string alone is not accepted as anchor or refutation evidence.

The two candidates in [`performance-brief.json`](../skills/research-idea/examples/performance-brief.json) each carry two component sources, three rejected pairs, two anchors, and a refutation record. Validate the example with:

    python -B skills/research-idea/scripts/shortlist.py skills/research-idea/examples/performance-brief.json

## Candidate pattern

Use two complementary components first, not a five-way stack:

    base method A + one mechanism from B
    -> integration point
    -> expected gain over A and B
    -> naive concatenation and remove-one ablations

Components must address different bottlenecks. `Both improve accuracy` is not a reason to combine them.

## Component library

Keep the extracted components in one JSON record and validate it before comparing pairs:

    python -B skills/research-idea/scripts/component_library.py skills/research-idea/examples/component-library.json

The top-level `components` list needs at least two objects. Each object records `id`, `paper`, `mechanism`, `input`, `output`, `bottleneck`, `assumption`, `cost`, `known_failure`, and `source`; every value must be a non-blank string and ids must be unique. `source` must name the component's card or paper and include a line/page locator such as `p. 4` or `lines 12-18`. Exit 0 prints a normalized summary; exit 2 means malformed input. This checks form only: it does not verify that the source exists or that the mechanism is implemented faithfully. See [`component-library.json`](../skills/research-idea/examples/component-library.json).

## Component compatibility score

Rank candidate pairs before writing the brief:

    python -B skills/research-idea/scripts/component_score.py skills/research-idea/examples/component-score.json

The top-level `pairs` list needs at least one object. Each pair has an `id`, exactly two `components`, a `baseline_strength` in [0, 1], and an `expected_gain` in [0, 1]. Each component has an `id`, a non-blank `bottleneck`, a non-negative `cost`, and a boolean `data_ready`. `cost` is a relative pilot cost, not minutes; lower is better.

Scores are `complementarity` (1 minus bottleneck word overlap), `feasibility` (ready fraction / (1 + total cost)), `expected_effect` (`expected_gain * baseline_strength`), and `total` (0.4/0.3/0.3). All are in [0, 1] and rounded to at most three decimals. Pairs sort by descending total, then ascending `id`, so ties are deterministic. Exit 0 prints the ranked summary; exit 2 means malformed input. This is a ranking aid, not evidence: it does not run a pilot, verify the declared numbers, or prove a gain. Use the brief and pilot gate for evidence. See [`component-score.json`](../skills/research-idea/examples/component-score.json).

## Baseline registry

Record every comparison arm in a read-only registry and validate it before running a pilot:

    python -B skills/research-idea/scripts/baseline_registry.py skills/research-idea/examples/baseline-registry.json

The top-level `baselines` list needs at least two objects. Each object records `id`, `source`, `implementation`, `budget`, `params`, and `role`; every value must be a non-blank string, ids must be unique, and `role` is `base`, `naive`, or `random`. At least one entry must be `naive` (the naive concatenation) and one must be `random` (the fixed-seed random control). `budget` and `params` are the fairness record: state them so a reviewer can check that every arm used the same split, budget, and tuning rule. Exit 0 prints a normalized summary; exit 2 means malformed input. This checks form only: it does not verify that an implementation matches its source or that run-time budgets were equal. See [`baseline-registry.json`](../skills/research-idea/examples/baseline-registry.json).

## Pilot gate

The brief describes what will be tested. The gate reads a separate pilot record that reports what happened:

    python -B skills/research-idea/scripts/performance_gate.py my-pilot.json

Top-level fields:

| field | rule |
| --- | --- |
| `metric` | non-blank string |
| `evidence_level` | required; one of `definitional`, `local-substitute`, `paper-worked-example`, `needs_data`; echoed in the gate output |
| `stage` | required; `pilot` or `full`; seed lists need at least 3 values for `pilot` and at least 5 for `full` |
| `threshold` | positive number, default `0.01` |
| `min_datasets` | integer >= 2, default `3` |
| `constraints` | optional object; only `min_coverage` (0 < n <= 1) and `max_runtime_s` (n > 0) are accepted |
| `datasets` | at least `min_datasets` dataset objects |

Per dataset:

| field | rule |
| --- | --- |
| `name` | unique, non-blank |
| `hybrid` | seed list |
| `baselines` | object with at least two seed lists; must include `naive_concat` and `random_control` |
| `ablations` | object with at least one seed list |
| `coverage` | number in [0, 1]; required in every dataset when `constraints.min_coverage` is set |
| `runtime_s` | positive seconds; required in every dataset when `constraints.max_runtime_s` is set |

All seed lists (hybrid, every baseline, every ablation) must share one length and meet the stage minimum. Each row reports `hybrid_sd` and `delta_ci95`, the two-sided 95% paired t-interval of hybrid minus the best baseline.

`evidence_level` is required even for a promising gate result: it declares what kind of evidence the numbers are, not how strong the verdict is. `definitional` and `paper-worked-example` records can pass the form gate but cannot support a performance claim; performance claims require `local-substitute` or stronger. A missing or unknown level is malformed input (exit 2), and the normalized output repeats the accepted level so the record and its result stay aligned.

The top-level random_control_spec is required: method, seed, and matched_on. random_control must be a data-independent shuffle or random-partition control with a fixed seed; a constant vector is rejected. The gate checks form and seed variation, not whether the control is scientifically meaningful.

Verdict:

- `promising`: at least ceil(2 * n_datasets / 3) datasets have mean delta >= threshold; every ablation drops the hybrid mean by at least threshold; every `random_control` margin is >= 0; every coverage/runtime constraint passes.
- `weak`: the dataset-win rule passes or any dataset has a positive delta, but at least one promising condition fails.
- `reject`: no dataset has a positive delta over its best baseline.

Exit 0 means promising, exit 3 means weak/reject, exit 2 means malformed input. `delta_ci95_excludes_zero` is reported for review and a crossed interval is weak, not promising. The gate is a filter, not a full benchmark: it does not validate the underlying numbers, a held-out test, or SOTA.

Pilot records written before this schema lack `stage`, `random_control`, or `evidence_level` and now exit 2. Add `stage`, a `random_control` baseline, `evidence_level`, and `coverage`/`runtime_s` when constraints are declared; [`performance-pilot.json`](../skills/research-idea/examples/performance-pilot.json) is the template.

## Pilot manifest

Before the pilot, bind the data files and split policy in a manifest. `performance_manifest.py` validates the record:

    python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json
    python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json --check-files

Fields (all required unless marked optional):

| field | rule |
| --- | --- |
| `manifest_version` | optional positive integer, default `1` |
| `data` | at least two objects |
| `data[].name` | unique, non-blank |
| `data[].path` | unique, non-blank, no `..` segments |
| `data[].sha256` | exactly 64 lowercase hex characters |
| `data[].rows` | positive integer |
| `data[].features` | positive integer |
| `data[].label` | non-blank |
| `data[].coverage` | optional, number in [0, 1] |
| `data[].runtime_s` | optional, positive seconds |
| `split.group_column` | non-blank |
| `split.folds` | integer >= 2 |
| `split.seeds` | at least three unique non-negative integers |
| `pilot.stage` | `pilot` or `full` |
| `pilot.threshold` | number in (0, 1] |
| `pilot.datasets` | at least two unique names that exist in `data` |
| `pilot.metric` | optional, non-blank |

Exit 0 means valid; 2 means malformed or incomplete. The command prints a normalized JSON summary with `checks.form`, `checks.files`, `warnings`, and `limits`.

- Without `--check-files`, only the declared hash format is checked; `file_present` is null and `sha256_verified` is false.
- With `--check-files`, every path must exist and its SHA-256 must match. Relative paths resolve against the manifest directory.
- A warning is emitted when `pilot.datasets` does not cover every `data` entry; this is legal.
- Validation does not prove that rows/features/label values are true or that the split is unbiased. It also does not check whether seed counts match the gate stage; the gate does that.

The example is [`performance-manifest.json`](../skills/research-idea/examples/performance-manifest.json): three datasets, five folds, seeds 13/37/61, stage pilot, threshold 0.01.

## 30-minute quickstart

Run from the repository root with Python 3.10+. The first ten minutes are record editing; a 3-dataset x 3-seed pilot fits in the remaining twenty.

1. Minutes 0-5, brief: copy the example, fill the two components and `component_sources` (one non-empty source per component), list at least two `rejected_pairs` with reasons, add at least two `anchors` and a `refutation` with queries and coverage, and keep naive concatenation among the baselines.

       cp skills/research-idea/examples/performance-brief.json my-brief.json
       python -B skills/research-idea/scripts/shortlist.py my-brief.json

   A malformed brief fails here and names the missing or blank field.

2. Minutes 5-10, manifest: copy the manifest example and bind the real data files, split group column, folds, and seeds.

       cp skills/research-idea/examples/performance-manifest.json my-manifest.json
       python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json
       python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json --check-files

   The `--check-files` run is the one that proves the bytes; it fails on a missing path or a hash mismatch.

3. Minutes 10-25, pilot: run three datasets x three seeds on the same split and budget. Record `hybrid`, both base methods, `naive_concat`, `random_control`, and at least one remove-one ablation. Declare `evidence_level` at the top level. Use [`performance-pilot.json`](../skills/research-idea/examples/performance-pilot.json) as the shape; every seed list must have the same length.

4. Minutes 25-30, gate:

       python -B skills/research-idea/scripts/performance_gate.py my-pilot.json

   Exit 0 is promising, 3 is weak/reject, 2 is malformed. Archive the command, the pilot record, and the manifest hash. If promising, repeat with `stage` set to `full` and at least five seeds; the full run is the real comparison.

Do not skip `random_control` or the manifest to save time. Reduce the number of candidates instead.

## Cloud handoff

Cloud workers may read cards and propose one hybrid, but the host Python runner executes the pilot. A cloud pilot is a filter, not a paper result. Only a passed pilot goes to the local full experiment.

## Anti-patterns

- stacking modules without an integration hypothesis
- comparing against a weak baseline or a different budget
- selecting the best dataset after seeing results
- claiming accuracy gain by lowering coverage
- treating a definitional identity as a performance result
- calling a naive concatenation a new algorithm
- citing a component source without saying what was read from it
- dropping rejected combinations without recording why

## Evidence levels

Label every number as definitional, local-substitute, paper-worked-example, or needs_data. Performance claims require local-substitute or stronger evidence plus a baseline and an ablation.
