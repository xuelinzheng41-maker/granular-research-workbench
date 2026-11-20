import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import performance_gate


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PerformanceGateTests(unittest.TestCase):
    def test_example_is_promising(self):
        result = performance_gate.compare(load(ROOT / "examples/performance-pilot.json"))
        self.assertEqual(result["verdict"], "promising")
        self.assertEqual(result["dataset_wins"], 3)
        self.assertTrue(result["ablation_all_pass"])

    def test_missing_ablation_is_rejected_as_malformed(self):
        source = load(ROOT / "examples/performance-pilot.json")
        del source["datasets"][0]["ablations"]
        with self.assertRaisesRegex(ValueError, "ablation"):
            performance_gate.compare(source)

    def test_no_baseline_gain_is_weak_or_reject(self):
        source = load(ROOT / "examples/performance-pilot.json")
        source["datasets"][0]["hybrid"] = [0.870, 0.875, 0.865]
        result = performance_gate.compare(source)
        self.assertIn(result["verdict"], {"weak", "reject"})
        self.assertFalse(result["rows"][0]["delta_pass"])

    def test_baselines_must_include_naive_concat(self):
        source = load(ROOT / "examples/performance-pilot.json")
        del source["datasets"][0]["baselines"]["naive_concat"]
        with self.assertRaisesRegex(ValueError, "naive_concat"):
            performance_gate.compare(source)


if __name__ == "__main__":
    unittest.main()
