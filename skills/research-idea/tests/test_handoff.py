import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

CLAIM = "Adding the singleton {1} makes object 1 enter the lower approximation of {1,3} in the stated covering."
IMPLEMENTATION = """import json


def lower(blocks, target):
    return sorted(set().union(*(block for block in blocks if block <= target)))


base = [{0, 1}, {1, 2}, {2, 3}]
print(json.dumps(dict(before=lower(base, {1, 3}), after=lower(base + [{1}], {1, 3}))))
"""


def brief(claim):
    selected = dict(id="singleton-witness", source_kind="anomaly", source="Synthetic four-point example",
                    claim=claim, prior_status="no_overlap_retrieved",
                    search_trace="Synthetic test of record wiring; no novelty claim or actual literature search.",
                    difference="Not a research contribution", risk="Alternative lowering operators",
                    first_probe="Enumerate blocks before and after adding a singleton", probe_minutes=12,
                    advance_if="Object 1 is absent before and present afterward", stop_if="No such change",
                    required_skills=["python"], required_resources=["local"])
    held = dict(selected, id="held", source_kind="transfer", prior_status="unsearched")
    return dict(profile=dict(topic="Synthetic covering fixture", minutes_this_week=40, probe_limit_minutes=15,
                             skills=["python"], resources=["local"]), candidates=[selected, held])


class CandidateHandoff(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ideas = self.root / "ideas"
        self.brief = self.root / "brief.json"
        self.put(self.brief, brief(CLAIM))
        self.env = dict(os.environ, PYTHONUTF8="1", LAB_IDEAS=str(self.ideas))

    def cli(self, script, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *map(str, args)],
                              env=self.env, encoding="utf-8", errors="replace", capture_output=True, check=False)

    def expect(self, code, script, *args):
        result = self.cli(script, *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    @staticmethod
    def put(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    @staticmethod
    def get(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def draft(self, slug):
        self.expect(0, "kb.py", "draft", slug, "--brief", self.brief, "--candidate", "singleton-witness")
        folder, = self.ideas.glob(f"*-{slug}")
        plan = self.get(folder / "probe-plan.json")
        plan.update(question="What changes under this addition?", rival="A base block is already contained in the target",
                    setup="U={0,1,2,3}; standard union-of-contained-blocks lower operator",
                    control="Same target and original blocks, before adding {1}", kind="theory",
                    implementation=dict(path="witness.py", reproduce="python -B witness.py"))
        self.put(folder / "probe-plan.json", plan)
        return folder, plan

    def implement(self, folder, digest):
        path = folder / "witness.py"
        path.write_text(IMPLEMENTATION, encoding="utf-8")
        raw = subprocess.check_output([sys.executable, "-B", path], cwd=folder, encoding="utf-8")
        self.assertEqual(json.loads(raw), {"before": [], "after": [1]})
        (folder / "raw.json").write_text(raw, encoding="utf-8")
        result = dict(status="advance", submitted_for_review=True, frozen_plan_sha256=digest,
                      observation="The lower approximation changes from empty to {1}",
                      supported_claim="The specified singleton witnesses the change in this one example.",
                      limitations="Not a universal claim or evidence of novelty.", next_step="Recompute from the block list.",
                      artifacts=["witness.py", "raw.json"])
        self.put(folder / "probe-result.json", result)
        return result

    def test_end_to_end_and_changed_claim_invalidates_result_and_review(self):
        try_draft = self.expect(2, "kb.py", "draft", "hold", "--brief", self.brief, "--candidate", "held")
        self.assertIn("not eligible", try_draft.stderr)
        self.assertFalse(self.ideas.exists())
        folder, plan = self.draft("first")
        self.assertEqual((plan["candidate_id"], plan["core_claim"], plan["budget_minutes"], plan["stop_if"]),
                         ("singleton-witness", CLAIM, 12, "No such change"))
        # A linked plan cannot silently change the candidate's decision contract.
        self.put(folder / "probe-plan.json", dict(plan, budget_minutes=13))
        self.assertIn("differs from selected candidate", self.expect(2, "probe.py", "freeze", folder).stderr)
        self.put(folder / "probe-plan.json", plan)
        freeze = json.loads(self.expect(0, "probe.py", "freeze", folder).stdout)
        self.expect(2, "probe.py", "freeze", folder)
        old_result = self.implement(folder, freeze["plan_sha256"])
        self.expect(2, "probe.py", "review-input", folder)
        self.expect(0, "probe.py", "seal", folder)
        packet = json.loads(self.expect(0, "probe.py", "review-input", folder).stdout)
        self.expect(2, "kb.py", "scaffold", folder.name)
        old_review = dict(reviewer="fixture-reviewer", verdict="direct", evidence_artifact="raw.json",
                          reason="Direct calculation", evidence_location="before and after", rival_check="same blocks",
                          review_input_sha256=packet["review_input_sha256"])
        self.put(folder / "probe-review.json", old_review)
        self.expect(0, "probe.py", "check", folder)
        self.expect(0, "kb.py", "scaffold", folder.name)

        self.put(folder / "probe-plan.json", dict(plan, control="A changed control"))
        self.assertIn("differs from the frozen plan", self.expect(2, "probe.py", "check", folder).stderr)
        self.put(folder / "probe-plan.json", plan)
        (folder / "witness.py").write_text(IMPLEMENTATION + "# Modified after sealing\n", encoding="utf-8")
        self.assertIn("sealed result or artifact changed", self.expect(2, "probe.py", "check", folder).stderr)
        self.expect(2, "probe.py", "seal", folder)

        self.put(self.brief, brief(CLAIM + " Object 3 remains outside."))
        newer, _ = self.draft("revised")
        new_lock = json.loads(self.expect(0, "probe.py", "freeze", newer).stdout)
        new_result = self.implement(newer, new_lock["plan_sha256"])
        self.put(newer / "probe-result.json", old_result)
        self.assertIn("do not reuse", self.expect(2, "probe.py", "seal", newer).stderr)
        self.put(newer / "probe-result.json", new_result)
        self.expect(0, "probe.py", "seal", newer)
        self.put(newer / "probe-review.json", old_review)
        self.assertIn("review again", self.expect(2, "kb.py", "scaffold", newer.name).stderr)
        self.assertFalse((newer / "idea.md").exists())

    def test_formal_inputs_are_bound_before_evidence(self):
        folder, plan = self.draft("locked-inputs")
        plan["implementation"]["inputs"] = ["config.json"]
        self.put(folder / "probe-plan.json", plan)
        digest = json.loads(self.expect(0, "probe.py", "freeze", folder).stdout)["plan_sha256"]
        missing = self.expect(2, "probe.py", "lock-inputs", folder)
        self.assertIn("witness.py", missing.stderr)
        self.assertFalse((folder / "probe-input-lock.json").exists())
        (folder / "witness.py").write_text(IMPLEMENTATION, encoding="utf-8")
        self.put(folder / "config.json", {"seed": 1})
        lock = json.loads(self.expect(0, "probe.py", "lock-inputs", folder).stdout)
        self.assertEqual(set(lock["files"]), {"witness.py", "config.json"})
        self.assertEqual(lock["plan_sha256"], digest)
        self.expect(2, "probe.py", "lock-inputs", folder)
        result = self.implement(folder, digest)
        self.assertIn("does not identify these frozen inputs", self.expect(2, "probe.py", "seal", folder).stderr)
        result["frozen_inputs_sha256"] = lock["inputs_sha256"]
        self.put(folder / "probe-result.json", dict(result, artifacts=["witness.py", "config.json"]))
        self.assertIn("evidence separate from the frozen inputs", self.expect(2, "probe.py", "seal", folder).stderr)
        self.put(folder / "probe-result.json", result)
        (folder / "witness.py").write_text(IMPLEMENTATION + "# Changed before seal\n", encoding="utf-8")
        self.assertIn("frozen implementation or input changed", self.expect(2, "probe.py", "seal", folder).stderr)
        (folder / "witness.py").write_text(IMPLEMENTATION, encoding="utf-8")
        self.expect(0, "probe.py", "seal", folder)
        self.expect(0, "probe.py", "review-input", folder)
        self.put(folder / "config.json", {"seed": 2})
        self.assertIn("frozen implementation or input changed",
                      self.expect(2, "probe.py", "review-input", folder).stderr)


if __name__ == "__main__":
    unittest.main()
