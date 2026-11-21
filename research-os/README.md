# Research OS v2 Preview

This preview adds a local, file-based research workflow: paper dataset checks, pre-registration, hash-bound approval and freezing, execution, results verification, and independent review. It does not require DSH or a cloud account.

## Run the example

Start at the repository root with Python 3.12 or newer. A virtual environment is recommended. Activate it before running the commands below.

~~~bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-research-os.txt
python -B research-os/cli.py datasets check
python -B research-os/cli.py datasets for-paper research-os/examples/paper.md --registry research-os/datasets.json
~~~

The bundled data and paper card are **synthetic**. The example reports one locally ready dataset. To see an unregistered requirement, append `--dataset MissingStudyData` to the last command; the report should exit 3 and does not download anything.

## Check your paper against your own data

Create a local registry following the shape of [the example registry](datasets.json), using your own dataset paths and statuses. Relative data roots resolve from the registry's directory. Keep private paths and research inputs out of Git. Use `local-registry.json` in the repository root or a path outside the checkout.

Put the intended datasets in the front matter of your Markdown paper card:

~~~yaml
---
datasets: ["MNIST", "Fashion-MNIST"]
---
~~~

~~~bash
python -B research-os/cli.py datasets for-paper paper.md --registry local-registry.json
python -B research-os/cli.py datasets for-paper paper.txt --registry local-registry.json --dataset MNIST --dataset Fashion-MNIST --json
~~~

With a UTF-8 text export or Markdown without an explicit list, the command reports known name/alias mentions and line numbers for confirmation. It may miss unregistered names. Confirm requirements from the paper's methods section using repeated `--dataset` flags. A name match does not prove version, preprocessing or split equivalence. PDF is not read directly.

The report distinguishes unregistered requirements, missing files, missing loaders, invalid data, integrity mismatches and datasets that do not meet the task's needs. Classification is the default; `--task clustering` allows unlabeled feature data, but does not make label-based scores available. Files without committed hash declarations remain unverified. Exit 0 means all explicit requirements are locally ready, 3 means blocked or awaiting confirmation, and 2 means invalid/unreadable input.

## Pilot and tests

See the [local pilot guide](../docs/research-os-v2/QUICKSTART-LAUNCH.md) for approvals, environment and trusted plugin constraints. This preview does not distribute real data, private cards or past runs. It makes no scientific claim and does not authorize a run.

~~~bash
python -B -m unittest discover -s research-os/tests -v
~~~
