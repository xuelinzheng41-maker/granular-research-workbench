# Research OS v2 pilot quick start

This guide covers the local pilot workflow. Synthetic regression results do not certify a real research run.
Use a new run directory. Use status and verify for both new and legacy runs; the CLI selects the appropriate validator.

1. Prepare a proposal JSON with `idea`, an absolute `registry` path, and `prereg`. See the template below.
2. Run `python research-os/cli.py init RUN PROPOSAL_JSON`. Inspect the exact proposal and its hash with `python research-os/cli.py proposal RUN`.
3. After a human confirms the exact proposal, run `python research-os/cli.py approve RUN H1 HASH`. Do not reuse approval across proposals.
4. Run `python research-os/cli.py freeze RUN`. It checks the declared matrix, then records the protocol, input, split, method, and runner digests in the freeze artifact.
5. For an authorized pilot, run `python research-os/cli.py run RUN`. A successful reservation writes one launch event before any method is invoked. Review the JSONL results, including each row's status. A non-ok row is not a successful experiment. Restart or retry in the same run is not supported. Use `python research-os/cli.py retry NEW_RUN OLD_RUN failed` for a completed run containing failures, or use `interrupted` for an incomplete run after confirming the original process has stopped. This registers a fresh attempt only; replay scoop if applicable, inspect the new proposal hash, obtain fresh H1, freeze, and start explicitly. Changes to the experimental inputs require a separate experiment. No results or approvals are copied, and budgets are per attempt, not pooled.

For the new format, both `status` and `verify` return 2 on corrupt bindings; `verify` returns 3 for a started but incomplete run (`status` returns 0 to report that state). Exit 0 means the reported state is internally consistent, including pending approval, not started, completed with failures, or archived; it does not imply scientific success. Newly launched runs seal the completed result bytes; earlier runs lack that seal. Local files and the operator declaration of interruption remain trusted.


Official launch respects only the local trust boundary: anyone with write access to the run directory can forge or replace approvals, inputs, and launch records. Plugins execute trusted Python with local user permissions; this is not a sandbox. Put each portable plugin in a dedicated directory. The freeze binds the relative paths and bytes of every regular file (up to 4,096 files and 32 MB); links, reparse points, bytecode, native plugin binaries, and path injection files are unsupported. Local imports and relative resource reads resolve from a temporary snapshot. The freeze also binds the Python executable digest, Python/platform identity, and installed distribution names and versions. This does not hash installed dependency binaries, OS libraries, environment variables, or external resources; plugins that depend on those inputs are outside the supported reproducibility contract. Old frozen launches are not upgraded in place. The row timeout includes a fixed two-second grace; the aggregate check sums those row limits, not overall elapsed wall time. Full additionally requires a local H2 confirmation tied to the freeze hash; Full was not exercised.


A minimal configuration shape (replace placeholders before use):


```json
{
  "idea": "Describe the hypothesis and expected outcome.",
  "registry": "C:/path/to/datasets.json",
  "prereg": {
    "hypothesis_claims": ["C1"],
    "stage": "pilot",
    "metric": "ACC",
    "threshold": 0.01,
    "seeds": [11, 29, 47],
    "datasets": ["dataset_id"],
    "split": {"test_size": 0.25, "stratify": true},
    "arms": {
      "candidate": {"directory": "C:/path/to/candidate", "budget_s": 5},
      "control": {"directory": "C:/path/to/control", "budget_s": 5}
    },
    "compute_budget_minutes": 2
  }
}
```

Each method directory supplies `method.py` with `fit_predict(X_train, y_train, X_test, seed, budget_s)` and a return mapping containing `predictions`. The minimal template is exploratory. For a formal candidate, use the source and claim declarations below.

After a complete pilot, run `python research-os/cli.py review-package RUN --max-bytes 1000000`. The command checks the launch and frozen matrix bindings and writes `review-package.json` once. Missing or duplicate rows, binding mismatches, and oversize packets are errors. The packet uses numeric dataset and arm aliases and excludes local paths, proposal text, card content, and author verdicts. It is not a claim ledger or a signed proof of execution; the run directory remains trusted.

For local four-axis scoop replay, add `"scoop": {"cards": "C:/path/to/cards", "queries": {"mechanism": ["term"], "data": ["term"], "metric": ["term"], "setting": ["term"]}}` to the proposal. After `init`, run `python research-os/cli.py scoop RUN`, then use `proposal RUN` to inspect the updated H1 hash and exact scoop record. `scoop-replay RUN` checks the current cards against that record. An empty or unreadable corpus is not a zero-hit result. The legacy v1 KB CLI still requires PyYAML for front matter. Without PyYAML the v2 supported front matter is a flat mapping with unsigned integers, simple plain strings, JSON strings, or JSON arrays of strings; other forms are reported as malformed. Search is literal and local, not a novelty determination.

Focused test: `python -m unittest discover -s research-os/tests -p test_launch.py`. It uses synthetic data and does not authorize a research run. The legacy M1 acceptance wrapper is not the launch verification command.

### Paired ACC claim (formal pilot)

In `prereg.paired_claims`, declare the claim before H1. The component ID must identify a verified anchor, and the dataset, seeds, and both arms must already appear in the preregistered matrix.

```json
[{"id":"C1","component":"anchor_1","datasets":["dataset_id"],"seeds":[11,29,47],"candidate":"candidate","control":"control","support_min":0.02,"refute_max":0.0}]
```

The statistic is the unweighted mean of candidate ACC minus control ACC over the complete declared dataset/seed product. Each pair must share the frozen split and have two successful rows. The lower threshold refutes and the upper threshold qualifies for support, both inclusive. Missing evidence does not trigger either. In the explicit review input, `"accepted_claims":["C1"]` names a claim accepted on the exact review target; an engineering pass alone does not support it.

Human reviewer records are unchanged. For a model review, use `"type":"independent_model"` with `id`, `independent`, `model_route`, `team_task` and `team_attempt`. These are explicit local provenance declarations, not identity authentication or proof of context isolation. Neither reviewer type substitutes for H1/H2. Outcomes apply only to the declared pilot and do not establish Full or general validity.

### Formal source and review

Set `"mode":"formal"` and supply `components` and the four scoop judgment lists before H1:

```json
{"components":[{"id":"anchor_1","card":"reference.md","body_line":1,"span_sha256":"sha256:REPLACE"}],"judgments":{"mechanism":[],"data":[],"metric":[],"setting":[]}}
```

Put `judgments` inside `scoop`, beside `cards` and `queries`. Mark source card front matter with `card_status: handmade`. Count body lines from one, excluding front matter; hash the UTF-8 line without its newline. For each retrieved line, record `card`, `body_line`, `span_sha256`, `overlap` and `reason`. Supported combinations are `none` with `different_scope`, `different_method` or `irrelevant_match`; `partial` with `shared_element`; and `blocking` with `same_claim`. Blocking overlap or incomplete coverage prevents a formal start.

After exporting the packet, run `review-target RUN` and give its exact output to the reviewer with the packet. The reviewer supplies a JSON object with `binding` (that output), `reviewer`, `verdict` (`pass`, `needs_revision` or `reject`), `rationale` and optionally `accepted_claims`. Human reviewer fields are `id`, `type: human` and `independent: true`. Run the following commands with the same CLI prefix:

```text
review RUN REVIEW_JSON
decide RUN
passport RUN
verify RUN
```

A negative review can be archived. A successful verification checks local artifact consistency, not scientific validity.
