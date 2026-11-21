import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import savemat


CLI = Path(__file__).resolve().parents[1] / "cli.py"


class PaperDatasetsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "x.txt").write_text("1 2\n3 4\n", encoding="utf-8")
        (self.data / "y.txt").write_text("0\n1\n", encoding="utf-8")
        self.entry = dict(id="Digits", aliases=["Demo Digits"], status="ready",
                          loader="txt_pair", data="x.txt", labels="y.txt")
        self.registry = self.root / "registry.json"

    def execute(self, body, entries, *options, suffix=".md"):
        paper = self.root / ("paper" + suffix)
        paper.write_text(body, encoding="utf-8")
        self.registry.write_text(json.dumps({"root": "data", "datasets": entries}), encoding="utf-8")
        initial = (paper.read_bytes(), self.registry.read_bytes())
        result = subprocess.run(
            [sys.executable, "-B", str(CLI), "datasets", "for-paper", str(paper),
             "--registry", str(self.registry), "--json", *options],
            cwd=CLI.parent, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(initial, (paper.read_bytes(), self.registry.read_bytes()))
        return result, json.loads(result.stdout) if result.stdout else None

    def test_declared_requirements_distinguish_missing_and_invalid(self):
        result, report = self.execute(
            '---\ndatasets: ["Demo Digits", "Absent", "MAT73", "WrongHash", "NewSet", "Malformed"]\n---\n',
            [self.entry, dict(self.entry, id="Absent", aliases=[], labels="not-there.txt"),
             dict(id="MAT73", status="needs_loader", loader="mat_v73"),
             dict(self.entry, id="WrongHash", aliases=[], sha256={"data": "sha256:bad"}),
             dict(self.entry, id="Malformed", aliases=[], data="y.txt", labels="x.txt")],
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report["source"], "card")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual([row["status"] for row in report["datasets"]],
                         ["ready", "needs_data", "needs_loader", "integrity_failed", "unregistered", "invalid_data"])
        self.assertEqual(report["datasets"][0]["integrity"], "unverified")
        self.assertEqual(report["datasets"][0]["dataset_id"], "Digits")

    def test_text_mentions_are_never_a_complete_requirement_list(self):
        text = "XDigits and NotDigits\nWe use Demo Digits and AnotherSet.\n\u4f7f\u7528Digits\u6570\u636e\u96c6"
        result, report = self.execute(text, [self.entry], suffix=".txt")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report["status"], "needs_confirmation")
        self.assertEqual([row["lines"] for row in report["datasets"]], [[2], [3]])
        result, report = self.execute(text, [self.entry], "--dataset", "Digits", "--dataset", "AnotherSet", suffix=".txt")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(report["source"], "confirmed")
        self.assertEqual(report["datasets"][1]["status"], "unregistered")
        result, report = self.execute("Nothing matched", [self.entry], suffix=".txt")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(report["datasets"], [])

    def test_ready_confirmed_data_can_be_fully_verified(self):
        import hashlib

        hashes = {key: "sha256:" + hashlib.sha256((self.data / filename).read_bytes()).hexdigest()
                  for key, filename in (("data", "x.txt"), ("labels", "y.txt"))}
        result, report = self.execute("Paper text", [dict(self.entry, sha256=hashes)], "--dataset", "digits")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["datasets"][0]["integrity"], "verified")
        self.assertTrue(report["datasets"][0]["has_ground_truth"])

    def test_task_distinguishes_unlabeled_clustering_data(self):
        savemat(self.data / "points.mat", {"points": np.arange(6).reshape(3, 2)})
        entry = dict(id="Points", loader="mat_v5", status="ready_with_scipy", usage="clustering",
                     data="points.mat", label_source={"kind": "none"})
        card = '---\ndatasets: ["Points"]\n---\n'
        result, report = self.execute(card, [entry])
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report["datasets"][0]["detail"], "clustering_only")
        result, report = self.execute(card, [entry], "--task", "clustering")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(report["datasets"][0]["has_ground_truth"])

    def test_alias_conflicts_and_malformed_card_are_not_ready(self):
        other = dict(self.entry, id="Fashion", aliases=["Demo Digits"])
        result, report = self.execute('---\ndatasets: ["Demo Digits"]\n---\n', [self.entry, other])
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(report["datasets"][0]["status"], "ambiguous")
        self.assertEqual(report["datasets"][0]["candidates"], ["Digits", "Fashion"])
        result, report = self.execute("---\ndatasets: Digits\n---\n", [self.entry])
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(report)
        self.assertIn("datasets must be a list", result.stderr)
