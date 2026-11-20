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
                              env=dict(os.environ, PYTHONUTF8="1"), encoding="utf-8", errors="replace",
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


PROBE = RUNNER.parents[1] / "skills" / "research-idea" / "scripts" / "probe.py"
AUTHOR_FIELDS = ("status", "supported_claim", "observation", "limitations", "next_step")


class WorkbenchReviewPacket(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "run"
        result = self.cli("math")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.author = self.load("probe-result.json")

    def cli(self, mode, *args):
        return subprocess.run([sys.executable, "-B", str(RUNNER), mode, str(self.folder), *map(str, args)],
                              env=dict(os.environ, PYTHONUTF8="1"), encoding="utf-8", errors="replace",
                              capture_output=True, check=False)

    def full(self):
        return subprocess.run([sys.executable, "-B", str(PROBE), "review-input", str(self.folder), "--full"],
                              env=dict(os.environ, PYTHONUTF8="1"), encoding="utf-8", errors="replace",
                              capture_output=True, check=False)

    def load(self, name):
        return json.loads((self.folder / name).read_text(encoding="utf-8"))

    def save(self, name, record):
        (self.folder / name).write_text(json.dumps(record), encoding="utf-8")

    def test_default_view_withholds_author_result_and_full_view_is_explicit(self):
        packet = self.cli("review-input")
        self.assertEqual(packet.returncode, 0, packet.stderr)
        brief = json.loads(packet.stdout)
        for key in AUTHOR_FIELDS + ("author_result",):
            self.assertNotIn(key, brief)
            self.assertNotIn(f'"{key}"', packet.stdout)
        for value in self.author.values():
            if isinstance(value, str):
                self.assertNotIn(value, packet.stdout)
        self.assertEqual(brief["core_claim"], self.load("probe-plan.json")["core_claim"])
        for key in ("setup", "control", "advance_if", "stop_if", "source", "question", "rival"):
            self.assertEqual(brief["plan"][key], self.load("probe-plan.json")[key])
        manifest = self.load("run-manifest.json")
        self.assertEqual(brief["artifacts"], ["evidence.json"])
        self.assertEqual(brief["artifact_sha256"]["evidence.json"], manifest["files"]["evidence.json"])
        self.assertEqual(brief["review_summary"]["view"], "first_round")
        self.assertEqual(self.cli("verify").returncode, 0)
        complete = self.full()
        self.assertEqual(complete.returncode, 0, complete.stderr)
        full = json.loads(complete.stdout)
        self.assertEqual(full["review_input_sha256"], brief["review_input_sha256"])
        self.assertEqual(full["supported_claim"], self.author["supported_claim"])
        self.assertEqual(full["author_result"], self.author)

    def test_review_provenance_is_recorded_but_never_verified(self):
        brief = json.loads(self.cli("review-input").stdout)
        review = dict(reviewer="test-reviewer", verdict="contradicted", reason="Point 1 disappears",
                      evidence_artifact="evidence.json", evidence_location="coarse_lower and fine_lower",
                      rival_check="Same target and crisp covering operator",
                      review_input_sha256=brief["review_input_sha256"])
        self.save("probe-review.json", dict(review, reviewer_type="ai_agent", author_result_exposure="none"))
        result = self.cli("check")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("reviewer_type=ai_agent", result.stdout)
        self.assertIn("author_result_exposure=none", result.stdout)
        self.save("probe-review.json", review)
        result = self.cli("check")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("reviewer_type=unspecified", result.stdout)
        self.assertIn("not treated as a blind review", result.stdout)
        self.save("probe-review.json", dict(review, author_result_exposure="before"))
        result = self.cli("check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("author_result_exposure must be one of", result.stderr)


def unavailable():
    raise ImportError("simulated missing numerical dependency")


if __name__ == "__main__":
    unittest.main()
