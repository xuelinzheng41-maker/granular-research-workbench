# Stability status

## What is stable now

The repository is usable for a narrow local research workflow: compare two or three candidates, bind one to a probe, freeze a plan, lock inputs, run a minimal experiment or proof, seal evidence, produce a first-round review packet, and let another researcher check it.

It is not yet a general-purpose or fully unattended research product.

## Supported environment

- Python 3.10–3.12.
- Windows and Linux.
- The selection, probe, and review paths use the standard library.
- The Digits workbench example needs NumPy and scikit-learn; install `requirements-test.txt`.
- A local knowledge base and MATLAB/GBSK data are optional and are not distributed here.

## Stable-version gates

A release is called stable only when all of these hold:

1. The CI matrix passes on the supported systems.
2. A clean clone passes the independent self-test, skill tests, workbench tests, and the fresh-clone test.
3. The public CLI, exit codes, and record schemas are documented in `docs/contracts.md`, and changes include a compatibility note.
4. The release is on `main`, has a changelog entry, and does not move an existing tag.
5. A real user can follow the quickstart from a clean checkout without editing local paths or private data.
6. No known critical defect is open.

## Current gaps

- The v0.4.x versions live on the `auto/integration` staging line; `main` is still v0.3.0.
- The workbench code is MIT-licensed. This repository does not include GBSK source code; GBSK-derived code must be distributed separately under GPL-compatible terms.
- The review process is evidence-oriented but does not authenticate reviewer identity, prove when a command ran, or replace human scientific judgment.
- The workbench has been exercised on a small number of real questions. That is not evidence that it will consistently produce publishable results.

## Non-goals

- Writing papers automatically.
- Running arbitrary commands on the user's behalf.
- Proving a scientific claim from a record alone.
- Guaranteeing that a candidate is novel.
