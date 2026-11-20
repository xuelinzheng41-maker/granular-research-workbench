# Public contracts

This file describes the parts of the workbench that a stable release may not change silently.

## Probe CLI

`skills/research-idea/scripts/probe.py` modes:

| Mode | Purpose | Success |
|---|---|---|
| `plan` | validate a probe plan | exit 0 |
| `freeze` | bind the plan to a digest | exit 0 |
| `lock-inputs` | hash declared implementation inputs | exit 0 |
| `verify-inputs` | read-only check of plan, lock, and inputs | exit 0 |
| `seal` | bind the result and evidence files | exit 0 |
| `review-input` | emit the default first-round packet | exit 0 |
| `check` | apply the review gate | exit 0 only for `advance` |

Exit code 2 means the record is malformed, incomplete, changed, or unsafe to use. Exit code 3 means the record is valid but the review or verification result does not support promotion. `check` also prints the self-declared reviewer provenance; it does not verify identity.

`review-input` requires a sealed result; `seal` requires the frozen plan and a result that identifies the frozen inputs when inputs are declared.

## Selection and knowledge-base CLI

- `shortlist.py <brief>`: exit 0 for a valid comparison, exit 2 for an unreadable or invalid brief.
  - Optional top-level `mode: "performance"` enables the performance track. Each candidate must then include a `performance` object with at least two base methods, two components, component_sources for every component, at least two rejected_pairs with reasons, at least two anchors with a source and why, a refutation object with non-empty queries and coverage, two baselines, two datasets, one metric, one ablation, an integration point, an expected gain, a compute budget, and a kill condition.
  - A `performance` block is validated whenever present, even in audit mode; audit mode is the default and old briefs remain valid.
- `performance_gate.py <pilot>`: exit 0 for promising, exit 3 for weak/reject, exit 2 for malformed input. It requires a top-level `evidence_level` of `definitional`, `local-substitute`, `paper-worked-example`, or `needs_data`; stage pilot or full (3 or 5 seeds); naive_concat and random_control baselines; random_control_spec; a remove-one ablation drop; and optional coverage/runtime constraints. It echoes `evidence_level` in the result. promising also requires the paired 95% interval to stay above zero and random_control not to beat the hybrid.
- `performance_manifest.py <manifest>`: exit 0 for a valid data/split/pilot manifest, exit 2 for malformed input. With --check-files it also verifies declared paths against SHA-256.
- `kb.py doctor|stats|gaps|search|show|anchors|feasibility|falsified`: exit 0 on success, exit 2 for a missing/unreadable knowledge base or invalid arguments.
- `kb.py draft`: exit 0 on creation, exit 2 for an invalid slug, duplicate directory, or an ineligible/missing candidate.
- `kb.py scaffold`: exit 0 when the probe is `advance`, exit 3 when it is not, exit 2 for malformed records or existing formal files.

`review-input --full` is the explicit full-record view. The default view withholds the author's status, supported claim, observation, limitations, and next step.

## Record files

- `probe-plan.json`, `probe-plan-lock.json`
- `candidate-selection.json`
- `probe-input-lock.json`
- `probe-result.json`, `probe-evidence-lock.json`
- `probe-review.json`

The first-round packet binds the plan, result, and evidence file hashes. A change to any bound file invalidates an existing review.

## Workbench CLI

`workbench/workbench.py` supports `math`, `digits`, `verify`, `review-input`, and `check`. Its run manifest records environment metadata separately from scientific evidence; environment differences are warnings, scientific evidence differences are errors.

## Compatibility

- Adding optional fields is allowed.
- Removing a field, changing its meaning, changing an exit code, or changing the review gate requires a changelog entry and a compatibility test.
- Old records without reviewer provenance are reported as `unspecified`; they are not treated as blind reviews.
- Old records without `implementation.inputs` keep their previous `seal`/`check` behavior and cannot use `lock-inputs`/`verify-inputs` until the field is added.

## What the tools do not prove

A matching hash does not prove who ran a command, when it ran, or that the person was independent. A reproducible number does not prove the scientific claim. A review verdict is evidence-bound judgment, not authentication.
