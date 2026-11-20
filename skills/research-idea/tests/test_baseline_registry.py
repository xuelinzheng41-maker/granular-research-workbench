import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import baseline_registry

EXAMPLE = ROOT / "examples/baseline-registry.json"
SCRIPT = ROOT / "scripts/baseline_registry.py"


def example():
    return copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))


class BaselineRegistryTests(unittest.TestCase):
    def test_example_is_valid(self):
        summary = baseline_registry.validate(example())
        self.assertEqual(summary["baseline_count"], 3)
        self.assertEqual(
            summary["ids"],
            ["gbcrs-base", "naive-concat", "random-control"],
        )
        self.assertEqual(summary["roles"], ["base", "naive", "random"])
        self.assertEqual(summary["role_counts"], {"base": 1, "naive": 1, "random": 1})
        self.assertEqual(summary["checks"]["form"], "ok")
        self.assertEqual(summary["checks"]["required_roles"], "ok")

    def test_missing_role_is_rejected(self):
        source = example()
        del source["baselines"][0]["role"]
        with self.assertRaisesRegex(ValueError, "role"):
            baseline_registry.validate(source)

    def test_invalid_role_is_rejected(self):
        source = example()
        source["baselines"][0]["role"] = "strong"
        with self.assertRaisesRegex(ValueError, "role"):
            baseline_registry.validate(source)

    def test_no_naive_entry_is_rejected(self):
        source = example()
        source["baselines"][1]["role"] = "base"
        with self.assertRaisesRegex(ValueError, "naive"):
            baseline_registry.validate(source)

    def test_no_random_entry_is_rejected(self):
        source = example()
        source["baselines"][2]["role"] = "base"
        with self.assertRaisesRegex(ValueError, "random"):
            baseline_registry.validate(source)

    def test_duplicate_id_is_rejected(self):
        source = example()
        source["baselines"][2]["id"] = source["baselines"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate baseline id"):
            baseline_registry.validate(source)

    def test_blank_field_is_rejected(self):
        source = example()
        source["baselines"][0]["budget"] = "   "
        with self.assertRaisesRegex(ValueError, "budget: missing or blank"):
            baseline_registry.validate(source)

    def test_two_entries_are_required(self):
        source = example()
        source["baselines"] = source["baselines"][:1]
        with self.assertRaisesRegex(ValueError, "at least 2 entries"):
            baseline_registry.validate(source)

    def test_cli_exit_codes(self):
        ok = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(EXAMPLE)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["baseline_count"], 3)

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            source = example()
            del source["baselines"][1]["role"]
            bad.write_text(json.dumps(source), encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(bad)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            )
            self.assertEqual(broken.returncode, 2)
            self.assertIn("role", broken.stderr)


if __name__ == "__main__":
    unittest.main()
