import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[1] / "cli.py"


class LaunchTests(unittest.TestCase):
    def test_fallback_parser_and_failed_coverage(self):
        from unittest.mock import patch

        sys.path.insert(0, str(CLI.parent / "lib"))
        from scoop import AXES, collect
        import card_parser as kb

        with tempfile.TemporaryDirectory() as tmp, patch.object(kb, "yaml", None):
            root = Path(tmp)
            good = root / "good.md"
            good.write_text('---\ntier: 1\ndatasets: ["example"]\n---\nmechanism\n', encoding="utf-8")
            bad = root / "bad.md"
            bad.write_text('---\ntier:\n  - nested\n---\n', encoding="utf-8")
            queries = {axis: [axis] for axis in AXES}
            self.assertEqual(kb.read_card(good)[0]["datasets"], ["example"])
            result = collect(root, queries)
            self.assertEqual(result["axes"]["data"]["status"], "partial_coverage")
            self.assertEqual(result["failures"][0]["card"], "bad.md")
            good.unlink()
            self.assertEqual(collect(root, queries)["axes"]["data"]["status"], "failed")

    def test_pilot_confirmation_freeze_and_single_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            reg = root / "registry.json"
            arm_dir = root / "plugin"
            arm_dir.mkdir()
            method = arm_dir / "method.py"
            method.write_text("def fit_predict(X, y, test, **kw):\n    return {\"predictions\": [0] * len(test)}\n", encoding="utf-8")
            (root / "x.txt").write_text("0\n1\n2\n3\n4\n5\n6\n7\n", encoding="utf-8")
            (root / "y.txt").write_text("0\n0\n0\n0\n1\n1\n1\n1\n", encoding="utf-8")
            reg.write_text(json.dumps({"root": str(root), "datasets": [dict(id="synthetic", status="ready",
                loader="txt_pair", data="x.txt", labels="y.txt")]}), encoding="utf-8")
            card = root / "anchor.md"
            card.write_text("---\ntier: 1\n---\nmechanism reference\n", encoding="utf-8")
            p = root / "proposal.json"
            p.write_text(json.dumps(dict(idea="Synthetic test only", registry=str(reg), scoop={"cards": str(root), "queries": {axis: [axis] for axis in ("mechanism", "data", "metric", "setting")}}, prereg=dict(
                hypothesis_claims=[], metric="ACC", datasets=["synthetic"], seeds=[11], stage="pilot",
                split={"test_size": .5, "stratify": True}, arms={"constant": {"directory": str(arm_dir), "budget_s": 5}},
                threshold=.01, compute_budget_minutes=1))), encoding="utf-8")

            def cli(command, *args, expect=0):
                result = subprocess.run([sys.executable, "-B", str(CLI), command, str(run), *map(str, args)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
                return result.stdout

            self.configure_plugin(method, root)
            self.configure_proposal(p, card)
            cli("init", p)
            scoop = json.loads(cli("scoop"))
            self.assertEqual(scoop["axes"]["data"]["status"], "zero_hits")
            self.assertEqual(scoop, json.loads(cli("scoop-replay")))
            sha = json.loads(cli("proposal"))["proposal_sha256"]
            original_card = card.read_bytes()
            card.write_bytes(original_card + b"changed")
            cli("scoop-replay", expect=2)
            card.write_bytes(original_card)
            cli("run", expect=2)
            cli("approve", "H1", "wrong", expect=2)
            cli("approve", "H1", sha)
            cli("run", expect=2)
            cli("freeze")
            cli("freeze", expect=2)
            self.check_frozen_plugin(cli, run, method)
            original = method.read_bytes()
            method.write_bytes(original + b"# changed\n")
            cli("run", expect=2)
            self.assertFalse((run / "launch.jsonl").exists())
            method.write_bytes(original)
            cli("run")
            self.assertEqual(json.loads(cli("verify"))["state"], "complete")
            rows = (run / "results.jsonl").read_bytes()
            row = json.loads(rows)
            self.assertEqual(row["row_key"], ["synthetic", "constant", 11, 1])
            self.assertEqual(row["status"], "ok")
            cli("run", expect=2)
            self.assertEqual((run / "results.jsonl").read_bytes(), rows)
            result_path = run / "results.jsonl"
            result_path.write_bytes(b"")
            cli("review-package", expect=2)
            result_path.write_text(json.dumps(dict(row, split_sha256="changed")), encoding="utf-8")
            cli("review-package", expect=2)
            result_path.write_bytes(rows)
            cli("review-package", "--max-bytes", 1, expect=2)
            cli("review-package")
            packet = run / "review-package.json"
            original = packet.read_bytes()
            self.assertNotIn(b"synthetic", original)
            self.assertNotIn(b"constant", original)
            self.assertNotIn(b"anchor.md", original)
            cli("review-package", expect=2)
            self.assertEqual(packet.read_bytes(), original)
            self.after_package(cli, run)

    def configure_plugin(self, method, root):
        pass

    def check_frozen_plugin(self, cli, run, method):
        pass

    def configure_proposal(self, path, card):
        pass

    def after_package(self, cli, run):
        pass


class ClassificationGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "run"
        self.reg = self.root / "registry.json"
        arm = self.root / "plugin"
        arm.mkdir()
        (arm / "method.py").write_text(
            'def fit_predict(X, y, test, **kw):\n    return {"predictions": [0] * len(test)}\n',
            encoding="utf-8",
        )
        (self.root / "x.txt").write_text("0\n1\n2\n3\n", encoding="utf-8")
        (self.root / "y.txt").write_text("0\n1\n0\n1\n", encoding="utf-8")
        self.good = dict(id="synthetic", status="ready", loader="txt_pair", data="x.txt", labels="y.txt")
        self.write_registry([self.good])
        proposal = self.root / "proposal.json"
        proposal.write_text(json.dumps(dict(idea="Synthetic gate test", registry=str(self.reg), prereg=dict(
            hypothesis_claims=[], metric="ACC", datasets=["synthetic"], seeds=[11], stage="pilot",
            split={"test_size": .5, "stratify": False}, arms={"constant": {"directory": str(arm), "budget_s": 5}},
            threshold=.01, compute_budget_minutes=1))), encoding="utf-8")
        out, _ = self.cli("init", proposal)
        self.cli("approve", "H1", json.loads(out)["proposal_sha256"])

    def cli(self, command, *args, expect=0):
        sys.path.insert(0, str(CLI.parent))
        try:
            import cli
        finally:
            sys.path.pop(0)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", [str(CLI), command, str(self.run), *map(str, args)]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = cli.main()
        self.assertEqual(status, expect, out.getvalue() + err.getvalue())
        return out.getvalue(), err.getvalue()

    def write_registry(self, entries):
        self.reg.write_text(json.dumps({"root": str(self.root), "datasets": entries}), encoding="utf-8")

    def test_refusals_precede_split_and_leave_no_artifacts(self):
        import numpy as np
        from scipy.io import savemat

        savemat(self.root / "points.mat", {"points": np.arange(8).reshape(4, 2)})
        savemat(self.root / "empty.mat", {"data": np.empty((0, 2)), "label": np.empty((0,))})
        (self.root / "single.txt").write_text("0\n0\n0\n0\n", encoding="utf-8")
        (self.root / "bad.mat").write_bytes(b"not a MAT file")
        (self.root / "bad-labels.txt").write_text("0\n1\nnope\n1\n", encoding="utf-8")
        mat = dict(id="synthetic", status="ready_with_scipy", loader="mat_v5", data="points.mat")
        cases = (
            (None, "blocked:needs_data", "unregistered dataset"),
            (dict(self.good, status="needs_data", data="unavailable.txt"), "blocked:needs_data", "unavailable.txt"),
            (dict(mat, status="needs_loader", loader="mat_v73"), "blocked:needs_data", "h5py"),
            (dict(mat, status="needs_loader", loader="custom"), "blocked:needs_data", "custom"),
            (dict(self.good, status="unknown"), "invalid registry status", "unknown"),
            (dict(self.good, data="missing.txt"), "blocked:needs_data", "Data file not found"),
            (dict(mat, label_source={"kind": "separate_file", "path": "missing-labels.txt"}),
             "blocked:needs_data", "Labels file not found"),
            (dict(self.good, sha256={"data": "sha256:bad"}), "invalid_data", "SHA256 mismatch for data"),
            (dict(self.good, rows=10), "invalid_data", "Row count mismatch"),
            (dict(self.good, features=10), "invalid_data", "Feature count mismatch"),
            (dict(mat, data="bad.mat"), "invalid_data", "Failed to load MATLAB file"),
            (dict(mat, label_source={"kind": "separate_file", "path": "bad-labels.txt"}),
             "invalid_data", "Invalid label format"),
            (dict(mat, usage="clustering", label_source={"kind": "none"}), "not_ready:clustering_only", ""),
            (mat, "not_ready:no_labels", ""),
            (dict(mat, data="empty.mat"), "not_ready:empty", ""),
            (dict(self.good, labels="single.txt"), "not_ready:single_class", ""),
        )
        nonfinite_cases = []
        for i, value in enumerate((np.nan, np.inf, -np.inf)):
            label_path = self.root / f"nonfinite-{i}.txt"
            label_path.write_text(f"0\n1\n{value}\n1\n", encoding="utf-8")
            mat_path = self.root / f"nonfinite-{i}.mat"
            savemat(mat_path, {"data": np.arange(8).reshape(4, 2), "label": [0, 1, value, 1]})
            nonfinite_cases.extend((
                (dict(self.good, labels=label_path.name), "invalid_data", f"Non-finite label in {label_path}"),
                (dict(mat, data=mat_path.name), "invalid_data", f"Non-finite label in {mat_path}"),
            ))
        cases += tuple(nonfinite_cases)
        freeze = self.run / "freeze.json"
        for command in ("freeze", "run"):
            if command == "run":
                self.write_registry([self.good])
                self.cli("freeze")
                baseline = freeze.read_bytes()
            for entry, reason, detail in cases:
                with self.subTest(command=command, reason=reason, detail=detail):
                    self.write_registry([] if entry is None else [entry])
                    with patch("sklearn.model_selection.train_test_split") as split:
                        _, err = self.cli(command, expect=2)
                    split.assert_not_called()
                    self.assertIn(f"Dataset synthetic: {reason}", err)
                    if detail:
                        self.assertIn(detail, err)
                    if reason == "invalid_data":
                        self.assertNotIn("blocked:needs_data", err)
                    if command == "freeze":
                        self.assertFalse(freeze.exists())
                    else:
                        self.assertEqual(freeze.read_bytes(), baseline)
                    for artifact in ("launch.jsonl", "results.jsonl", "completion.json"):
                        self.assertFalse((self.run / artifact).exists())

    def test_external_labels_loaded_once_and_bound_by_raw_bytes(self):
        import numpy as np
        from scipy.io import savemat
        import launch

        savemat(self.root / "features.mat", {"data": np.arange(8).reshape(4, 2)})
        labels = self.root / "labels.txt"
        original = b"0\n1\n0\n1\n"
        labels.write_bytes(original)
        entry = dict(id="synthetic", status="ready_with_scipy", loader="mat_v5", data="features.mat",
                     usage="classification", label_source={"kind": "separate_file", "path": labels.name})
        self.write_registry([entry])
        with patch.object(launch, "load_dataset_with_label_info", wraps=launch.load_dataset_with_label_info) as load:
            self.cli("freeze")
        load.assert_called_once()
        frozen = json.loads((self.run / "freeze.json").read_bytes())
        self.assertEqual(frozen["data"]["synthetic"]["source"]["labels"],
                         "sha256:" + hashlib.sha256(original).hexdigest())

        labels.write_bytes(original.replace(b"\n", b"\r\n"))
        _, err = self.cli("run", expect=2)
        self.assertIn("frozen inputs changed", err)
        for artifact in ("launch.jsonl", "results.jsonl", "completion.json"):
            self.assertFalse((self.run / artifact).exists())

        labels.write_bytes(original)
        with patch.object(launch, "load_dataset_with_label_info", wraps=launch.load_dataset_with_label_info) as load:
            self.cli("run")
        load.assert_called_once()
        self.assertEqual(json.loads((self.run / "results.jsonl").read_bytes())["status"], "ok")
