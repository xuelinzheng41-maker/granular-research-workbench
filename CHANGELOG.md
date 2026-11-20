# Changelog

## Unreleased — 1.0.0-rc1 stability work

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
