# Changelog

## 1.1.0 — 2026-11-20

- Made the performance track the primary research direction in README, SKILL.md, and docs/performance-track.md; audit mode remains available for definition and theorem checks.
- Added an optional top-level mode "performance" brief schema for hybrid/optimization candidates: two base methods, two components, integration point, expected gain, two baselines, two datasets, metrics, ablation, compute budget, and kill condition.
- Added performance_gate.py: exit 0 for promising, exit 3 for weak/reject, exit 2 for malformed input; it checks best-baseline gain, naive concatenation, threshold, and ablation drop.
- Added performance brief/pilot examples and regression tests.
- Removed the upper bound on candidate comparisons: at least two candidates, no maximum. Audit mode remains the default for old briefs; performance briefs opt in with mode "performance". The audit review gate is unchanged.

## 1.0.1 — 2026-11-20

- Fixed `selftest.py` losing child output when the parent runs under a non-UTF Windows console; it now decodes UTF-8 explicitly and pins child IO encoding.
- Added a Windows-only CI step that runs the self-test with `PYTHONUTF8=0` and `PYTHONIOENCODING=cp936`.
- The fresh-clone test no longer requires `.git`; it copies the documented source paths, so a release archive can run it.
- Documented `shortlist.py` and `kb.py` exit codes and the `seal` requirement for `review-input`.

## 1.0.0 — 2026-11-20

First stable release. The CI matrix passed on `main` for Ubuntu and Windows on Python 3.10–3.12.

- Added a CI matrix for Ubuntu and Windows on Python 3.10–3.12.
- Added a clean-clone regression test that copies only tracked files and runs the suites without local knowledge bases or prior `ideas/`.
- Added `requirements-test.txt`, `STABILITY.md`, and `docs/contracts.md`.
- Selected the MIT license for the workbench code. No GBSK-derived source is included; GBSK-derived code must remain a separate GPL-compatible distribution.
- No research semantics changed in this entry.

## 0.4.2 — 2026-11-20 (staging from `auto/integration`)

- `verify-inputs` now detects extra top-level fields in `probe-input-lock.json` and checks the complete lock record.
- Added regression coverage for legacy three-field locks and tampered lock records.

## 0.4.1 — 2026-11-20 (staging from `auto/integration`)

- `verify-inputs` now checks the current plan hash and the lock's own digest.
- Added `plan_changed`, `lock_integrity`, and `current_plan_sha256` to the report.
- Authorized a single existing-test key-set assertion update; the change was reviewed independently.

## 0.4.0 — 2026-11-19 (staging from `auto/integration`)

- Added a reviewer-facing `verify-inputs` command for recomputing frozen input hashes.
- Added candidate-to-probe handoff: candidate ID, claim, budget, and stop condition are inherited from the comparison record.

## 0.3.0 — 2026-11-19

- Separated the first-round review packet from the author's conclusions.
- Added explicit `--full` access, reviewer provenance fields, and stricter old-record handling.
