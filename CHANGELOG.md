# Changelog

## 1.4.0 (2026-11-21)

- Research OS records scoped successes, negative results, inconclusive results and blocked studies in a private local SQLite memory.
- Search by Idea ID or keyword, distinguish candidate/validated/integrated components, and verify evidence links by file digest.
- Proposal initialization can report prior records without changing any H1, freeze, or independent review contract.

## 1.2.0 — 2026-11-21

- Cloud 8h optimization added component-library, anchors/refutation, baseline-registry, evidence-level, component-score, and pre-registration validators with tests.

- Documented that the performance track's agent reads paper cards and chooses component pairs itself; the user supplies constraints, not a combination direction.
- Added the component-recombination reference with extraction fields, compatibility filters, hybrid format, and human veto role.
- Performance briefs now require `component_sources` (one non-empty source per declared component; undeclared names are rejected as typos) and `rejected_pairs` (at least two pairs, each with a reason; duplicate pairs are rejected). Both example candidates carry two sources and three rejected pairs.
- Strengthened `performance_gate.py`: top-level `stage` is required (`pilot` needs at least 3 seeds per list, `full` at least 5), `naive_concat` and `random_control` baselines are mandatory, optional `constraints` enforce dataset coverage and runtime, and each row reports `hybrid_sd` and a paired 95% `delta_ci95`. A promising verdict also requires the random control not to beat the hybrid and every constraint to pass; exit codes remain 0/3/2.
- Added `performance_manifest.py`: validates data provenance (`path`/`sha256`/`rows`/`features`/`label`), split policy (`group_column`/`folds`/`seeds`), and the pilot contract (`stage`/`threshold`/`datasets`). Exit 0 for valid, 2 for malformed; `--check-files` binds declared paths to real SHA-256 values. Added an example manifest and 17 tests.
- Documented the strengthened brief schema, gate rules, and manifest commands in README, `docs/performance-track.md`, `skills/research-idea/references/performance-track.md`, and the component-recombination reference, including a 30-minute quickstart.

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
