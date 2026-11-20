import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import performance_gate

EXAMPLE = ROOT / "examples/performance-pilot.json"
LEVELS = ("definitional", "local-substitute", "paper-worked-example", "needs_data")


def load(path=EXAMPLE):
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(payload, tmp):
    path = Path(tmp) / "pilot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    script = ROOT / "scripts" / "performance_gate.py"
    return subprocess.run(
        [sys.executable, "-B", str(script), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class PerformanceGateEvidenceLevelTests(unittest.TestCase):
    def test_example_declares_and_echoes_evidence_level(self):
        source = load()
        self.assertEqual(source["evidence_level"], "local-substitute")
        result = performance_gate.compare(source)
        self.assertEqual(result["evidence_level"], "local-substitute")
        self.assertEqual(result["verdict"], "promising")

    def test_missing_evidence_level_is_malformed(self):
        source = load()
        del source["evidence_level"]
        with self.assertRaisesRegex(ValueError, "missing or blank evidence_level"):
            performance_gate.compare(source)

    def test_blank_evidence_level_is_malformed(self):
        source = load()
        source["evidence_level"] = "  "
        with self.assertRaisesRegex(ValueError, "missing or blank evidence_level"):
            performance_gate.compare(source)

    def test_non_string_evidence_level_is_malformed(self):
        source = load()
        source["evidence_level"] = ["local-substitute"]
        with self.assertRaisesRegex(ValueError, "missing or blank evidence_level"):
            performance_gate.compare(source)

    def test_unknown_evidence_level_is_malformed(self):
        source = load()
        source["evidence_level"] = "anecdotal"
        with self.assertRaisesRegex(ValueError, "evidence_level must be one of"):
            performance_gate.compare(source)

    def test_every_declared_level_is_accepted(self):
        source = load()
        for level in LEVELS:
            changed = copy.deepcopy(source)
            changed["evidence_level"] = level
            self.assertEqual(performance_gate.compare(changed)["evidence_level"], level)

    def test_evidence_level_does_not_change_gate_result(self):
        source = load()
        baseline = performance_gate.compare(source)
        baseline.pop("evidence_level")
        for level in LEVELS:
            changed = copy.deepcopy(source)
            changed["evidence_level"] = level
            result = performance_gate.compare(changed)
            result.pop("evidence_level")
            self.assertEqual(result, baseline)

    def test_cli_rejects_missing_and_unknown_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = run_cli(load(), tmp)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(json.loads(valid.stdout)["evidence_level"], "local-substitute")

            missing_source = load()
            del missing_source["evidence_level"]
            missing = run_cli(missing_source, tmp)
            self.assertEqual(missing.returncode, 2)
            self.assertIn("evidence_level", missing.stderr)

            unknown_source = load()
            unknown_source["evidence_level"] = "strong"
            unknown = run_cli(unknown_source, tmp)
            self.assertEqual(unknown.returncode, 2)
            self.assertIn("evidence_level must be one of", unknown.stderr)


if __name__ == "__main__":
    unittest.main()
