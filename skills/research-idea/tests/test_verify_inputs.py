import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PLAN = dict(source_kind="transfer", source="Fixture", kind="theory",
            question="Does the fixture hold?", core_claim="The fixture hashes stay frozen.",
            rival="The files may have changed", setup="Write two local input files",
            control="Compare recomputed hashes with the lock", advance_if="Every hash matches",
            stop_if="A declared file is missing or changed", budget_minutes=10,
            implementation=dict(path="run.py", reproduce="python -B run.py",
                                inputs=["config.json"]))


def digest(record):
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class VerifyInputs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "candidate"
        self.folder.mkdir()
        self.env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        self.put_record("probe-plan.json", PLAN)
        self.put_text("run.py", "print('witness')\n")
        self.put_text("config.json", '{"seed": 1}\n')
        self.relock()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / "probe.py"), *map(str, args)],
                              env=self.env, encoding="utf-8", capture_output=True, check=False)

    def put_record(self, name, value):
        (self.folder / name).write_text(json.dumps(value), encoding="utf-8")

    def put_text(self, name, value):
        (self.folder / name).write_text(value, encoding="utf-8")

    def load(self, name):
        return json.loads((self.folder / name).read_text(encoding="utf-8"))

    def state(self):
        return {path.name: path.read_bytes() for path in sorted(self.folder.iterdir()) if path.is_file()}

    def relock(self):
        plan = self.load("probe-plan.json")
        entry = plan["implementation"]
        names = [entry["path"], *entry["inputs"]]
        files = {name: hashlib.sha256((self.folder / name).read_bytes()).hexdigest() for name in names}
        lock = dict(plan_sha256=digest(plan), files=files)
        lock["inputs_sha256"] = digest(lock)
        self.put_record("probe-input-lock.json", lock)
        self.lock = lock

    def verify(self, code):
        result = self.run_cli("verify-inputs", self.folder)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_matching_lock_reports_hashes_without_writing(self):
        self.put_text("notes.txt", "not a declared input\n")
        before = self.state()
        result = self.verify(0)
        payload = json.loads(result.stdout)
        self.assertEqual(set(payload), {"ok", "plan_sha256", "inputs_sha256", "files",
                                        "changed", "missing", "extra", "plan_changed",
                                        "lock_integrity"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["plan_sha256"], self.lock["plan_sha256"])
        self.assertEqual(payload["inputs_sha256"], self.lock["inputs_sha256"])
        self.assertEqual(payload["files"], self.lock["files"])
        self.assertNotIn("notes.txt", payload["files"])
        self.assertEqual(payload["changed"], [])
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["extra"], [])
        self.assertEqual(self.state(), before)

    def test_changed_declared_file_is_reported_without_repair(self):
        self.put_text("config.json", '{"seed": 2}\n')
        before = self.state()
        result = self.verify(3)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["changed"], ["config.json"])
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["extra"], [])
        self.assertEqual(payload["files"]["config.json"],
                         hashlib.sha256(b'{"seed": 2}\n').hexdigest())
        self.assertEqual(self.load("probe-input-lock.json"), self.lock)
        self.assertEqual(self.state(), before)

    def test_missing_declared_file_is_listed_and_not_recreated(self):
        (self.folder / "config.json").unlink()
        result = self.verify(3)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["changed"], [])
        self.assertEqual(payload["missing"], ["config.json"])
        self.assertEqual(payload["extra"], [])
        self.assertNotIn("config.json", payload["files"])
        self.assertFalse((self.folder / "config.json").exists())

    def test_absent_lock_exits_two_and_points_to_lock_inputs(self):
        (self.folder / "probe-input-lock.json").unlink()
        before = self.state()
        result = self.verify(2)
        self.assertIn("lock-inputs", result.stderr)
        self.assertFalse((self.folder / "probe-input-lock.json").exists())
        self.assertEqual(self.state(), before)

    def test_legacy_plan_without_inputs_exits_two_and_keeps_lock(self):
        plan = self.load("probe-plan.json")
        del plan["implementation"]["inputs"]
        self.put_record("probe-plan.json", plan)
        before = self.state()
        result = self.verify(2)
        self.assertIn("implementation.inputs", result.stderr)
        self.assertIn("lock-inputs", result.stderr)
        self.assertEqual(self.load("probe-input-lock.json"), self.lock)
        self.assertEqual(self.state(), before)

    def test_newly_declared_file_is_reported_as_extra(self):
        plan = self.load("probe-plan.json")
        plan["implementation"]["inputs"].append("extra.txt")
        self.put_record("probe-plan.json", plan)
        self.put_text("extra.txt", "added without relocking\n")
        before = self.state()
        result = self.verify(3)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["changed"], [])
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["extra"], ["extra.txt"])
        self.assertIn("extra.txt", payload["files"])
        self.assertEqual(self.load("probe-input-lock.json"), self.lock)
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
