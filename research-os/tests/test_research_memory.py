import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "cli.py"


class MemoryCLI(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = self.root / "memory.sqlite3"
        self.evidence = self.root / "private-evidence.txt"
        self.evidence.write_text("synthetic evidence", encoding="utf-8")
        self.manifest = self.root / "record.json"
        self.payload = {
            "id": "fixture-positive", "idea_id": "local-vote", "outcome": "supported_in_scope",
            "summary": "Synthetic proof on one scope", "scope": "synthetic only",
            "next_step": "Check a second dataset", "tags": ["粒球", "5NN"], "evidence": [str(self.evidence)],
            "components": [{"name": "local vote", "status": "validated", "basis": "test fixture only",
                            "artifact": str(self.evidence)}],
        }

    def call(self, *args, code=0):
        run = subprocess.run([sys.executable, "-B", str(CLI), *map(str, args)],
                             capture_output=True, encoding="utf-8", check=False,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(run.returncode, code, run.stdout + run.stderr)
        return run

    def memory(self, *args, **kw):
        out = self.call("memory", "--store", self.store, *args, **kw)
        return json.loads(out.stdout) if out.stdout else out.stderr

    def add(self, *args, **kw):
        self.manifest.write_text(json.dumps(self.payload), encoding="utf-8")
        return self.memory("record", self.manifest, *args, **kw)

    def test_search_idempotence_and_private_file_integrity(self):
        self.assertEqual(self.memory("search"), [])
        self.assertFalse(self.store.exists())
        self.assertTrue(self.add()["inserted"])
        self.assertFalse(self.add()["inserted"])
        found, = self.memory("search", "粒球 5nn", "--idea-id", "local-vote")
        self.assertNotIn(str(self.evidence), json.dumps(found))
        self.assertEqual(found["components"][0]["status"], "validated")
        self.assertEqual(self.memory("show", "fixture-positive")["evidence"][0]["path"], str(self.evidence.resolve()))
        self.assertTrue(self.memory("verify", "fixture-positive")["verified"])
        self.payload["summary"] = "different"
        self.assertIn("already exists", self.add(code=2))
        self.evidence.write_text("changed", encoding="utf-8")
        self.assertFalse(self.memory("verify", "fixture-positive", code=2)["verified"])

    def test_blocked_and_negative_are_distinct_and_init_does_not_bind_memory(self):
        self.assertTrue(self.add()["inserted"])
        self.payload.update(id="fixture-blocked", outcome="blocked", components=[])
        self.assertTrue(self.add()["inserted"])
        self.assertEqual(len(self.memory("search", "--outcome", "blocked")), 1)
        self.assertEqual(self.memory("search", "--outcome", "negative"), [])
        self.payload.update(id="fixture-negative", outcome="negative")
        self.assertTrue(self.add()["inserted"])
        self.assertEqual(len(self.memory("search", "--outcome", "negative")), 1)
        config = self.root / "proposal.json"
        config.write_text('{"idea":"synthetic"}', encoding="utf-8")
        baseline = self.call("init", self.root / "first", config)
        assisted = self.call("init", self.root / "second", config, "--memory-idea-id", "local-vote", "--memory-store", self.store)
        self.assertEqual(json.loads(baseline.stdout), json.loads(assisted.stdout))
        memo = json.loads(assisted.stderr)
        self.assertFalse(memo["authorizes_run"])
        self.assertEqual(len(memo["memory_advisory"]), 3)
        self.assertEqual({p.name for p in (self.root / "second").iterdir()}, {"proposal.json"})
        self.assertIn("complete run", self.add("--run", self.root / "second", code=2))

    def test_checkout_store_and_invalid_promotions_are_refused(self):
        self.payload["outcome"] = "blocked"
        self.assertIn("supported record", self.add(code=2))
        pretend_repo = self.root / "checkout"
        (pretend_repo / ".git").mkdir(parents=True)
        result = self.call("memory", "--store", pretend_repo / "private.sqlite3", "search", code=2)
        self.assertIn("outside Git", result.stderr)
        self.assertFalse((pretend_repo / "private.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
