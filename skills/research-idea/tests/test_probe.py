import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PLAN = dict(source_kind="transfer", source="Source mechanism, section 2",
            question="Can two distinct partitions of three points share a block-size profile?",
            core_claim="Two distinct partitions of three points can have block sizes 2 and 1.",
            rival="The profiles may differ or the partitions may be identical",
            kind="theory", setup="Construct two partitions of the same three labeled points",
            control="Compare actual blocks and sorted block sizes",
            advance_if="Exhibit two unequal partitions with size profile (1,2)",
            stop_if="Exhaust all partitions without finding a witness",
            budget_minutes=30)


class ProbeWorkflow(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = dict(os.environ, LAB_IDEAS=tmp.name, LAB_KB=tmp.name,
                        LAB_DATA=tmp.name, PYTHONDONTWRITEBYTECODE="1")
        output = self.run_cli("kb.py", "draft", "theory-demo")
        self.assertEqual(output.returncode, 0, output.stderr)
        self.folder, = self.root.iterdir()

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              env=self.env, text=True, capture_output=True, check=False)

    def record(self, name, value):
        (self.folder / name).write_text(json.dumps(value), encoding="utf-8")

    def result(self, status="advance", path="calculation.txt"):
        self.record("probe-plan.json", PLAN)
        (self.folder / "calculation.txt").write_text("{{a,b},{c}} vs {{a,c},{b}}; sizes (1,2) in both.\n",
                                                    encoding="utf-8")
        self.record("probe-result.json", dict(status=status, observation="Unequal partitions, equal sizes",
                    supported_claim=PLAN["core_claim"], limitations="Only an existence witness",
                    next_step="Check whether the ambiguity matters for a selector", artifacts=[path]))

    def review(self, verdict, reason, evidence_artifact="calculation.txt"):
        packet = self.run_cli("probe.py", "review-input", self.folder)
        self.assertEqual(packet.returncode, 0, packet.stderr)
        self.record("probe-review.json", dict(reviewer="test-reviewer", verdict=verdict,
                    reason=reason, evidence_artifact=evidence_artifact,
                    evidence_location="First line: both explicit partitions",
                    rival_check="Their actual blocks differ even though their sorted sizes agree.",
                    review_input_sha256=json.loads(packet.stdout)["review_input_sha256"]))

    def scaffold(self):
        return self.run_cli("kb.py", "scaffold", self.folder.name)

    def test_unfilled_draft_cannot_scaffold(self):
        self.assertEqual(self.scaffold().returncode, 2)
        self.assertFalse((self.folder / "idea.md").exists())

    def test_closed_outcomes_keep_the_record_without_writing_formal_docs(self):
        for status in ("refuted", "inconclusive"):
            with self.subTest(status=status):
                self.result(status)
                legacy = dict(PLAN)
                del legacy["core_claim"]
                self.record("probe-plan.json", legacy)
                self.assertEqual(self.scaffold().returncode, 3)
                self.assertEqual(self.run_cli("probe.py", "check", self.folder).returncode, 3)
                self.assertFalse((self.folder / "idea.md").exists())

    def test_invalid_evidence_is_rejected(self):
        (self.root / "outside.txt").write_text("Outside file", encoding="utf-8")
        for path in ("missing.txt", "probe-plan.json", "../outside.txt"):
            with self.subTest(path=path):
                self.result(path=path)
                self.assertEqual(self.scaffold().returncode, 2)
                self.assertFalse((self.folder / "idea.md").exists())

    def test_author_advance_alone_cannot_scaffold(self):
        self.result()
        self.assertEqual(self.scaffold().returncode, 2)
        self.assertFalse((self.folder / "idea.md").exists())

    def test_c2_proxy_evidence_cannot_advance_target_recovery_claim(self):
        self.record("probe-plan.json", dict(PLAN, source_kind="literature",
                    source="2026-11-19 paired blind evaluation, C2", kind="empirical",
                    question="Does the rule recover a planted target layer?",
                    core_claim="Pair-count discontinuity recovers a preset target layer more often than cluster counts.",
                    rival="Distinguishing equal count sequences may not improve target recovery.",
                    setup="Paired chains with targets and a fixed generation distribution",
                    control="Optimal count-only selector under the same distribution",
                    advance_if="Target hit rate exceeds the control on the specified paired chains",
                    stop_if="Target hit rate is no higher than the control"))
        (self.folder / "calculation.txt").write_text(
            "Cluster counts: 6,5,4,3 in both chains. Deltas 1,9,4 -> scores 1,4; "
            "deltas 4,9,1 -> scores 4,1. Neither chain has a specified target.\n", encoding="utf-8")
        self.record("probe-result.json", dict(status="advance", observation="Different layers selected",
                    supported_claim="The rule distinguishes two chains with identical cluster counts.",
                    limitations="No target was assigned and no hit rate was measured.",
                    next_step="Fix targets and compare hit rates", artifacts=["calculation.txt"]))
        self.review("proxy_only", "The hand calculation tests discrimination, not recovery of a known target.")
        result = self.scaffold()
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("inconclusive", result.stderr)
        self.assertEqual(self.run_cli("probe.py", "check", self.folder).returncode, 3)
        self.assertFalse(any((self.folder / f).exists() for f in ("idea.md", "anchors.md", "review.md")))

    def test_updated_inputs_invalidate_prior_direct_review(self):
        for filename in ("probe-plan.json", "probe-result.json", "calculation.txt"):
            with self.subTest(filename=filename):
                self.result()
                self.review("direct", "The two listed partitions witness the existence claim.")
                target = self.folder / filename
                if filename.endswith(".json"):
                    record = json.loads(target.read_text(encoding="utf-8"))
                    record["setup" if filename == "probe-plan.json" else "observation"] = "Changed"
                    self.record(filename, record)
                else:
                    target.write_text("Changed artifact.\n", encoding="utf-8")
                result = self.scaffold()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("review again", result.stderr)
                self.assertFalse((self.folder / "idea.md").exists())

    def test_theory_advance_works_without_kb_or_data_and_never_overwrites(self):
        self.result()
        self.review("direct", "Both concrete partitions have profile (1,2) and unequal blocks.")
        self.assertEqual(self.run_cli("probe.py", "plan", self.folder).returncode, 0)
        self.assertEqual(self.run_cli("probe.py", "check", self.folder).returncode, 0)
        result = self.scaffold()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("idea.md", "anchors.md", "review.md"):
            self.assertTrue((self.folder / name).is_file())
        old = (self.folder / "idea.md").read_bytes()
        self.assertEqual(self.scaffold().returncode, 2)
        self.assertEqual((self.folder / "idea.md").read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
