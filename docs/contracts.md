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
