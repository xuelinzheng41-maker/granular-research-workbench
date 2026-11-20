# Performance track (primary mode)

This track is for candidates whose goal is a better measured result, not for finding a definitional defect. The existing audit track stays unchanged.

## When to use it

Use performance mode when the candidate claims that a new algorithm or a component recombination improves a metric under a fixed budget. Do not use it for theorem/definition audits; those remain audit mode.

## Required brief fields

Set top-level `mode` to `performance`. Every candidate needs a `performance` object with:

- `base_methods`: at least two methods being combined or compared
- `components`: at least two mechanisms, not just module names
- `component_sources`: required object, one non-empty source per declared component (see below)
- `rejected_pairs`: required list of at least two rejected combinations with reasons (see below)
- `anchors`: required list of at least two anchor objects, each with `source` and `why` (see below)
- `refutation`: required object with a non-empty `queries` list and non-empty `coverage` (see below)
- `integration`: where and how the components interact
- `expected_gain`: a numeric target, not `better`
- `baselines`: at least two, including the stronger base and a naive concatenation
- `datasets`: at least two, with a fixed split and seed policy
- `metrics`: primary and secondary metrics
- `ablation`: at least one remove-one or random-component control
- `compute_budget_minutes`: full pilot budget
- `kill_if`: the condition that ends the candidate

`shortlist.py` validates these fields when mode is `performance`; it does not certify that the gain is real. The JSON example is [`examples/performance-brief.json`](../examples/performance-brief.json).

### `component_sources` (required)

`component_sources` is an object, not a list. Each key is a component name that already appears in `components`; each value is a non-empty string naming the source card or paper and what was read from it.

- Every declared component must have exactly one entry. A missing component is an error.
- A key that is not a declared component is rejected as a typo, so use the exact component string.
- Blank keys and blank values are rejected.
- The field is an audit trail, not evidence: `shortlist.py` checks presence and form, not that the cited source exists.

The example maps each component to the paper and the specific mechanism that was read:

- `granular-ball cover` -> GBCRS (IJAR 2025): granular-ball cover construction, read from the local paper snapshot.
- `ball-level evidence accumulation` -> EAC paper: ball-level evidence accumulation layer, read from the local paper snapshot.

### `rejected_pairs` (required)

`rejected_pairs` is a list with at least two objects. Each object has a non-blank `pair` and a non-blank `reason`.

- A list, not an object.
- Fewer than two entries is an error.
- Duplicate pairs are rejected case-insensitively.
- The reason must say why the combination is not worth testing: same bottleneck, subsumption, unavailable interface, hidden hyperparameter, budget mismatch, or a result that would only be a definitional audit.

### `anchors` and `refutation` (required)

`anchors` is a list of at least two objects. Each object has a non-blank `source` and `why`. The source names the paper card or paper plus the locator or section read; `why` says what that source supports in this candidate. This carries the checklist evidence, so a `search_trace` string alone is not enough.

`refutation` is an object with a non-empty `queries` list and a non-blank `coverage` string. `queries` records the mechanism keywords used with the refutation search, and `coverage` states which corpus, cards, or indexes were searched and what was not. A missing object, empty query list, or blank coverage is an error. Presence and form are checked; the search itself is not run, and the cited sources are not verified.

Both example candidates in [`examples/performance-brief.json`](../examples/performance-brief.json) carry two component sources, three rejected pairs, two anchors, and a refutation record. Validate the example with:

    python -B skills/research-idea/scripts/shortlist.py skills/research-idea/examples/performance-brief.json

## Candidate pattern

Use two complementary components first, not a five-way stack:

    base method A + one mechanism from B
    -> integration point
    -> expected gain over A and B
    -> naive concatenation and remove-one ablations

Components must address different bottlenecks. `Both improve accuracy` is not a reason to combine them.

## Component library

Keep the extracted components in one read-only record and validate it:

    python -B skills/research-idea/scripts/component_library.py skills/research-idea/examples/component-library.json

Top-level `components` lists at least two objects. Each needs non-blank `id`, `paper`, `mechanism`, `input`, `output`, `bottleneck`, `assumption`, `cost`, `known_failure`, and `source`; ids must be unique, and `source` must name the component's card/paper plus a line/page locator. Exit 0 is valid, 2 is malformed. The validator checks form, not the cited evidence. Example: [`component-library.json`](../examples/component-library.json).

## Component compatibility score

Rank candidate pairs before writing the brief:

    python -B skills/research-idea/scripts/component_score.py skills/research-idea/examples/component-score.json

Top-level `pairs` lists at least one object. Each pair needs `id`, exactly two `components`, `baseline_strength` in [0, 1], and `expected_gain` in [0, 1]. Each component needs `id`, non-blank `bottleneck`, non-negative `cost`, and boolean `data_ready`; `cost` is relative pilot cost, not minutes. Scores are in [0, 1] and rounded to at most three decimals: `complementarity` (1 minus bottleneck word overlap), `feasibility` (ready fraction / (1 + total cost)), `expected_effect` (`expected_gain * baseline_strength`), and `total` (0.4/0.3/0.3). Pairs sort by descending total then ascending `id`; exit 0 is valid, 2 is malformed. The score is a ranking aid, not evidence: it checks form only and proves no gain. Example: [`component-score.json`](../examples/component-score.json).

## Baseline registry

Keep the comparison arms in one read-only record and validate it before the pilot:

    python -B skills/research-idea/scripts/baseline_registry.py skills/research-idea/examples/baseline-registry.json

Top-level `baselines` lists at least two objects. Each needs non-blank `id`, `source`, `implementation`, `budget`, `params`, and `role`; ids must be unique, and `role` must be `base`, `naive`, or `random`. At least one `naive` entry (the naive concatenation) and one `random` entry (the fixed-seed random control) are required. `budget` and `params` record fairness: every arm should use the same split, budget, and tuning rule. Exit 0 is valid, 2 is malformed. The validator checks form, not the cited implementation or the actual run-time budgets. Example: [`baseline-registry.json`](../examples/baseline-registry.json).

## Pilot gate

The gate reads a separate pilot record. The brief says what will be tested; the pilot record reports what happened. Run:

    python -B skills/research-idea/scripts/performance_gate.py my-pilot.json

Top-level fields:

| field | rule |
| --- | --- |
| `metric` | non-blank string |
| `evidence_level` | required; one of `definitional`, `local-substitute`, `paper-worked-example`, `needs_data`; echoed in the gate output |
| `stage` | required; `pilot` or `full`; every seed list needs at least 3 values for `pilot` and at least 5 for `full` |
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

All seed lists (hybrid, every baseline, every ablation) must share one length and meet the stage minimum. The gate reports `hybrid_sd` and `delta_ci95` per dataset; `delta_ci95` is the two-sided 95% paired t-interval of hybrid minus the best baseline.

The top-level `evidence_level` is required: `definitional`, `local-substitute`, `paper-worked-example`, or `needs_data`. It declares the kind of evidence behind the numbers and is echoed in the gate output. Missing, blank, or unknown values exit 2. Passing the gate does not upgrade the evidence level; performance claims still require `local-substitute` or stronger.

Verdict:

- `promising`: at least ceil(2 * n_datasets / 3) datasets have mean delta >= threshold; every ablation drops the hybrid mean by at least threshold; every `random_control` margin is >= 0; every coverage/runtime constraint passes.
- `weak`: the dataset-win rule passes or any dataset has a positive delta, but at least one promising condition fails.
- `reject`: no dataset has a positive delta over its best baseline.

Exit codes are 0 for `promising`, 3 for `weak`/`reject`, and 2 for malformed input. `delta_ci95_excludes_zero` is reported for review but is not a pass condition. The gate checks record consistency, not held-out performance, and it is not SOTA evidence.

Pilot records written before this schema lack `stage`, `random_control`, or `evidence_level` and now exit 2; add them together with `coverage`/`runtime_s` if constraints are declared. Use [`examples/performance-pilot.json`](../examples/performance-pilot.json) as the template.

## Pilot manifest

`performance_manifest.py` validates the input record before the pilot runs: data files, split policy, and pilot contract. Run:

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

- Without `--check-files`, the command checks only the declared hash format; `file_present` is null and `sha256_verified` is false.
- With `--check-files`, every path must exist and its SHA-256 must match. Relative paths resolve against the manifest directory.
- A warning is emitted when `pilot.datasets` does not cover every `data` entry; this is legal.
- Validation does not prove that rows/features/label values are true or that the split is unbiased. It also does not check that seed counts match the gate stage; the gate does that.

The example is [`examples/performance-manifest.json`](../examples/performance-manifest.json): three datasets, five folds, seeds 13/37/61, stage pilot, threshold 0.01.

## 30-minute quickstart

Run from the repository root with Python 3.10+. The early steps are editing, not training, so a 3-dataset x 3-seed pilot fits in the remaining 20 minutes.

1. Minutes 0-5, brief: copy the example and fill the components, `component_sources` (one per component), `rejected_pairs` (at least two with reasons), `anchors` (at least two with source and why), `refutation` (queries plus coverage), and baselines including naive concatenation.

       cp skills/research-idea/examples/performance-brief.json my-brief.json
       python -B skills/research-idea/scripts/shortlist.py my-brief.json

   A malformed brief fails here with the missing or blank field name.

2. Minutes 5-10, manifest: copy the manifest example and bind the real data files, split group column, folds, and seeds.

       cp skills/research-idea/examples/performance-manifest.json my-manifest.json
       python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json
       python -B skills/research-idea/scripts/performance_manifest.py my-manifest.json --check-files

   The second manifest command is the one that proves the bytes; it fails if a path is missing or the hash differs.

3. Minutes 10-25, pilot: run three datasets x three seeds on the same split and budget. Record `hybrid`, both base methods, `naive_concat`, `random_control`, and at least one remove-one ablation, and declare `evidence_level` at the top level. Use [`examples/performance-pilot.json`](../examples/performance-pilot.json) as the shape; every seed list must have the same length.

4. Minutes 25-30, gate:

       python -B skills/research-idea/scripts/performance_gate.py my-pilot.json

   Exit 0 is promising, 3 is weak/reject, 2 is malformed. Archive the command, the record, and the manifest hash. If the pilot is promising, repeat with `stage` set to `full` and at least five seeds; the full run is the real comparison, not a larger pilot.

Do not skip `random_control` or the manifest to save time. Shorten the candidate list instead.

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
- hiding rejected combinations instead of recording why they were dropped

## Evidence levels

Label every number as definitional, local-substitute, paper-worked-example, or needs_data. Performance claims require local-substitute or stronger evidence plus a baseline and an ablation.
