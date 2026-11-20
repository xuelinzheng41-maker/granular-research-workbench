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


class VerifyInputsIntegrity(unittest.TestCase):
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
        with (self.folder / name).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value))

    def put_text(self, name, value):
        with (self.folder / name).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)

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
        return json.loads(result.stdout)

    def test_matching_record_confirms_plan_and_lock(self):
        before = self.state()
        payload = self.verify(0)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["plan_changed"])
        self.assertTrue(payload["lock_integrity"])
        self.assertNotIn("current_plan_sha256", payload)
        self.assertEqual(self.state(), before)

    def test_changed_plan_reports_current_digest_without_rewriting(self):
        plan = self.load("probe-plan.json")
        plan["setup"] = "Write three local input files"
        self.put_record("probe-plan.json", plan)
        before = self.state()
        payload = self.verify(3)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["plan_changed"])
        self.assertTrue(payload["lock_integrity"])
        self.assertEqual(payload["plan_sha256"], self.lock["plan_sha256"])
        self.assertEqual(payload["current_plan_sha256"], digest(plan))
        self.assertEqual(payload["changed"], [])
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["extra"], [])
        self.assertEqual(self.load("probe-input-lock.json"), self.lock)
        self.assertEqual(self.state(), before)

    def test_tampered_inputs_digest_fails_lock_integrity(self):
        lock = self.load("probe-input-lock.json")
        lock["inputs_sha256"] = "0" * 64
        self.put_record("probe-input-lock.json", lock)
        before = self.state()
        payload = self.verify(3)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["plan_changed"])
        self.assertFalse(payload["lock_integrity"])
        self.assertNotIn("current_plan_sha256", payload)
        self.assertEqual(payload["changed"], [])
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["extra"], [])
        self.assertEqual(self.state(), before)

    def test_tampered_files_mapping_fails_lock_integrity(self):
        lock = self.load("probe-input-lock.json")
        lock["files"]["config.json"] = "0" * 64
        self.put_record("probe-input-lock.json", lock)
        before = self.state()
        payload = self.verify(3)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["plan_changed"])
        self.assertFalse(payload["lock_integrity"])
        self.assertEqual(payload["changed"], ["config.json"])
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
