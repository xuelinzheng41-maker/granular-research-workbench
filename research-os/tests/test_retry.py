import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_launch import CLI


class RetryTests(unittest.TestCase):
    def test_failed_attempt_and_linked_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            arm = root / "arm"
            arm.mkdir()
            (arm / "method.py").write_text("def fit_predict(*args, **kw): raise RuntimeError('fixture')", encoding="utf-8")
            for name in ("x", "y"):
                (root / (name + ".txt")).write_text("0\n0\n0\n0\n1\n1\n1\n1\n", encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"root": str(root), "datasets": [dict(id="synthetic", status="ready",
                loader="txt_pair", data="x.txt", labels="y.txt")]}), encoding="utf-8")
            source = root / "proposal.json"
            source.write_text(json.dumps(dict(idea="Retry fixture", registry=str(registry), prereg=dict(
                hypothesis_claims=[], metric="ACC", datasets=["synthetic"], seeds=[11], stage="pilot",
                split={"test_size": .5, "stratify": True}, arms={"bad": {"directory": str(arm), "budget_s": 5}},
                threshold=.01, compute_budget_minutes=1))), encoding="utf-8")

            def cli(cmd, run, *args, rc=0):
                proc = subprocess.run([sys.executable, "-B", str(CLI), cmd, str(run), *map(str, args)],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, rc, proc.stdout + proc.stderr)
                return proc.stdout

            parent, child = root / "parent", root / "child"
            sha = json.loads(cli("init", parent, source))["proposal_sha256"]
            self.assertEqual(json.loads(cli("status", parent))["state"], "awaiting_H1")
            cli("approve", parent, "H1", sha)
            cli("freeze", parent)
            self.assertEqual(json.loads(cli("verify", parent))["state"], "frozen_not_started")
            cli("run", parent)
            cli("run", parent, rc=2)
            self.assertEqual(json.loads(cli("verify", parent))["state"], "complete_with_failures")
            result = parent / "results.jsonl"
            original = result.read_bytes()
            result.write_bytes(original.replace(b'"error"', b'"timeout"'))
            self.assertEqual(json.loads(cli("verify", parent, rc=2))["state"], "corrupt")
            result.write_bytes(original)
            old = {f.name: f.read_bytes() for f in parent.iterdir()}
            child_sha = cli("retry", child, parent, "failed").strip()
            cli("run", child, rc=2)
            cli("approve", child, "H1", sha, rc=2)
            cli("approve", child, "H1", child_sha)
            cli("freeze", child)
            cli("run", child)
            cli("review-package", child)
            packet = json.loads((child / "review-package.json").read_bytes())["packet"]
            self.assertEqual(packet["retry"]["reason"], "failed")
            self.assertNotIn(str(parent), json.dumps(packet))
            self.assertEqual(old, {f.name: f.read_bytes() for f in parent.iterdir()})
            interrupted = root / "interrupted"
            interrupted.mkdir()
            for name in ("proposal.json", "H1.json", "freeze.json", "launch.jsonl"):
                (interrupted / name).write_bytes(old[name])
            self.assertEqual(json.loads(cli("verify", interrupted, rc=3))["state"], "started_incomplete")
            cli("retry", root / "interruption-retry", interrupted, "interrupted")
            legacy = root / "legacy"
            legacy.mkdir()
            self.assertNotIn('"state"', cli("status", legacy))
