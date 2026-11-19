import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RUNNER = Path(__file__).resolve().parents[1] / "workbench.py"
SPEC = importlib.util.spec_from_file_location("workbench_runner", RUNNER)
wb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wb)


class WorkbenchRegressions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "run"

    def cli(self, mode):
        return subprocess.run([sys.executable, "-B", str(RUNNER), mode, str(self.folder)],
                              env=dict(os.environ, PYTHONUTF8="1"), encoding="utf-8",
                              capture_output=True, check=False)

    def load(self, name):
        return json.loads((self.folder / name).read_text(encoding="utf-8"))

    def save(self, name, record):
        (self.folder / name).write_text(json.dumps(record), encoding="utf-8")

    def test_math_refutation_can_be_reviewed_but_not_promoted(self):
        for mode in ("math", "verify"):
            result = self.cli(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.load("evidence.json")["partition_checks"], 96)
        self.assertEqual(self.load("probe-result.json")["status"], "refuted")
        packet = self.cli("review-input")
        self.assertEqual(packet.returncode, 0, packet.stderr)
        self.assertEqual(self.cli("check").returncode, 2)
        review = dict(reviewer="test-reviewer", verdict="contradicted", reason="Point 1 disappears",
                      evidence_artifact="evidence.json", evidence_location="coarse_lower and fine_lower",
                      rival_check="Same target and crisp covering operator",
                      review_input_sha256=json.loads(packet.stdout)["review_input_sha256"])
        self.save("probe-review.json", review)
        self.assertEqual(self.cli("check").returncode, 3)
        review["verdict"] = "direct"
        self.save("probe-review.json", review)
        self.assertEqual(self.cli("check").returncode, 2)
        self.assertEqual(self.cli("math").returncode, 2)

    def test_result_changed_before_review_is_rejected(self):
        self.assertEqual(self.cli("math").returncode, 0)
        result = self.load("probe-result.json")
        result["supported_claim"] = "changed before review"
        self.save("probe-result.json", result)
        for mode in ("verify", "review-input"):
            check = self.cli(mode)
            self.assertEqual(check.returncode, 2)
            self.assertIn("frozen file changed: probe-result.json", check.stderr)

    def test_failed_run_can_retry_same_path(self):
        plan, _ = wb.study("digits")
        with patch.object(wb, "study", return_value=(plan, unavailable)):
            with self.assertRaises(ImportError):
                wb.run_study("digits", self.folder)
        self.assertFalse(self.folder.exists())
        self.assertEqual(list(self.folder.parent.iterdir()), [])
        self.assertEqual(self.cli("math").returncode, 0)

    def test_digits_environment_warning_and_strict_predictions(self):
        try:
            import sklearn
        except ImportError:
            self.skipTest("scikit-learn is required for the Digits regression")
        result = self.cli("digits")
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = self.load("evidence.json")
        self.assertEqual([(r["point_correct"], r["grain_correct"]) for r in evidence["runs"]],
                         [(413, 411), (402, 387), (417, 380)])
        self.assertFalse(evidence["bound_met_on_all_splits"])
        self.assertEqual(self.load("probe-result.json")["status"], "refuted")
        with patch.object(sklearn, "__version__", "different-version-label"):
            wb.verify(self.folder)
        # Even rehashing a changed file cannot hide a changed scientific value.
        evidence["runs"][0]["point_predictions"][0] ^= 1
        self.save("evidence.json", evidence)
        manifest = self.load("run-manifest.json")
        manifest["files"]["evidence.json"] = hashlib.sha256((self.folder / "evidence.json").read_bytes()).hexdigest()
        self.save("run-manifest.json", manifest)
        check = self.cli("verify")
        self.assertEqual(check.returncode, 2)
        self.assertIn("differs in scientific evidence", check.stderr)


def unavailable():
    raise ImportError("simulated missing numerical dependency")


if __name__ == "__main__":
    unittest.main()
