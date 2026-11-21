import json
import shutil

import test_launch


class ReviewDecisionTests(test_launch.LaunchTests):
    def after_package(self, cli, run):
        cli("decide", expect=2)
        cli("passport", expect=2)
        binding = json.loads(cli("review-target"))
        review = dict(binding=binding, reviewer={"id": "fixture-reviewer", "type": "human",
                      "independent": True}, verdict="reject", rationale="Synthetic negative review")
        source = run.parent / "review-input.json"

        def submit(value, expect=2):
            source.write_text(json.dumps(value), encoding="utf-8")
            cli("review", source, expect=expect)

        submit(dict(review, binding=dict(binding, packet_sha256="wrong")))
        foreign = run.parent / "other-run"
        shutil.copytree(run, foreign)
        source.write_text(json.dumps(review), encoding="utf-8")
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(test_launch.CLI), "review", str(foreign), str(source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((foreign / "review.json").exists())
        submit(dict(review, claims=[{"id": "C1", "status": "supported"}]))
        submit(dict(review, claims=[{"id": "C1", "status": "refuted"}]))
        submit(review, expect=0)
        submit(review)
        path = run / "results.jsonl"
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"metric": 0.5', b'"metric": 0.6'))
        self.assertNotEqual(path.read_bytes(), original)
        cli("decide", expect=2)
        path.write_bytes(original)
        cli("decide")
        cli("decide", expect=2)
        cli("passport")
        cli("passport", expect=2)
        self.assertEqual(json.loads(cli("verify"))["state"], "archived")
        record = json.loads((run / "passport.json").read_bytes())
        self.assertEqual(record["decision"]["decision"], "do_not_advance")
        self.assertEqual(record["decision"]["scientific_claims"], "unknown")
        self.assertEqual(record["decision"]["binding"], binding)
