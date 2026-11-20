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


def load(path=EXAMPLE):
    return json.loads(path.read_text(encoding="utf-8"))


def stretch(values, count):
    out = list(values)
    while len(out) < count:
        out.append(values[len(out) % len(values)])
    return out


def reseed(source, count):
    out = copy.deepcopy(source)
    for dataset in out["datasets"]:
        dataset["hybrid"] = stretch(dataset["hybrid"], count)
        for key in list(dataset["baselines"]):
            dataset["baselines"][key] = stretch(dataset["baselines"][key], count)
        for key in list(dataset["ablations"]):
            dataset["ablations"][key] = stretch(dataset["ablations"][key], count)
    return out


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


class PerformanceGateTests(unittest.TestCase):
    def test_example_is_promising(self):
        result = performance_gate.compare(load())
        self.assertEqual(result["verdict"], "promising")
        self.assertEqual(result["stage"], "pilot")
        self.assertEqual(result["min_samples"], 3)
        self.assertEqual(result["dataset_wins"], 3)
        self.assertTrue(result["ablation_all_pass"])
        self.assertTrue(result["random_control_all_pass"])
        self.assertTrue(result["constraints_all_pass"])

    def test_example_reports_spread_and_paired_interval(self):
        result = performance_gate.compare(load())
        for row in result["rows"]:
            self.assertGreater(row["hybrid_sd"], 0.0)
            low, high = row["delta_ci95"]
            self.assertLessEqual(low, high)
            self.assertTrue(row["delta_ci95_excludes_zero"])
            self.assertGreater(row["random_control_margin"], 0.0)
            self.assertIsNotNone(row["coverage"])
            self.assertIsNotNone(row["runtime_s"])

    def test_missing_stage_is_malformed(self):
        source = load()
        del source["stage"]
        with self.assertRaisesRegex(ValueError, "stage"):
            performance_gate.compare(source)

    def test_unknown_stage_is_malformed(self):
        source = load()
        source["stage"] = "quick"
        with self.assertRaisesRegex(ValueError, "pilot or full"):
            performance_gate.compare(source)

    def test_pilot_stage_requires_three_seeds(self):
        source = load()
        source["datasets"][0]["hybrid"] = source["datasets"][0]["hybrid"][:2]
        with self.assertRaisesRegex(ValueError, "at least 3 numbers"):
            performance_gate.compare(source)

    def test_full_stage_requires_five_seeds(self):
        source = load()
        source["stage"] = "full"
        with self.assertRaisesRegex(ValueError, "at least 5 numbers"):
            performance_gate.compare(source)

    def test_full_stage_with_five_seeds_is_promising(self):
        source = reseed(load(), 5)
        source["stage"] = "full"
        result = performance_gate.compare(source)
        self.assertEqual(result["stage"], "full")
        self.assertEqual(result["min_samples"], 5)
        self.assertEqual(result["verdict"], "promising")

    def test_missing_ablation_is_rejected_as_malformed(self):
        source = load()
        del source["datasets"][0]["ablations"]
        with self.assertRaisesRegex(ValueError, "ablation"):
            performance_gate.compare(source)

    def test_no_baseline_gain_is_weak_or_reject(self):
        source = load()
        source["datasets"][0]["hybrid"] = [0.870, 0.875, 0.865]
        result = performance_gate.compare(source)
        self.assertIn(result["verdict"], {"weak", "reject"})
        self.assertFalse(result["rows"][0]["delta_pass"])
        self.assertLessEqual(result["rows"][0]["delta_ci95"][1], 0.0)

    def test_baselines_must_include_naive_concat(self):
        source = load()
        del source["datasets"][0]["baselines"]["naive_concat"]
        with self.assertRaisesRegex(ValueError, "naive_concat"):
            performance_gate.compare(source)

    def test_baselines_must_include_random_control(self):
        source = load()
        del source["datasets"][0]["baselines"]["random_control"]
        with self.assertRaisesRegex(ValueError, "random_control"):
            performance_gate.compare(source)

    def test_single_baseline_is_malformed(self):
        source = load()
        source["datasets"][0]["baselines"] = {"random_control": [0.86, 0.865, 0.855]}
        with self.assertRaisesRegex(ValueError, "at least two entries"):
            performance_gate.compare(source)

    def test_baseline_length_mismatch_is_malformed(self):
        source = load()
        source["datasets"][0]["baselines"]["base_a"] = [0.878, 0.887, 0.875, 0.88]
        with self.assertRaisesRegex(ValueError, "length differs from hybrid"):
            performance_gate.compare(source)

    def test_coverage_constraint_blocks_promising(self):
        source = load()
        source["datasets"][1]["coverage"] = 0.5
        result = performance_gate.compare(source)
        self.assertNotEqual(result["verdict"], "promising")
        self.assertEqual(result["verdict"], "weak")
        self.assertFalse(result["constraints_all_pass"])
        self.assertTrue(result["rows"][1]["delta_pass"])
        self.assertFalse(result["rows"][1]["constraint_pass"])

    def test_runtime_constraint_blocks_promising(self):
        source = load()
        source["datasets"][2]["runtime_s"] = 900
        result = performance_gate.compare(source)
        self.assertEqual(result["verdict"], "weak")
        self.assertFalse(result["constraints_all_pass"])
        self.assertFalse(result["rows"][2]["constraint_pass"])

    def test_constraints_are_optional(self):
        source = load()
        del source["constraints"]
        result = performance_gate.compare(source)
        self.assertEqual(result["verdict"], "promising")
        self.assertIsNone(result["constraints"]["min_coverage"])
        self.assertIsNone(result["constraints"]["max_runtime_s"])
        self.assertTrue(result["constraints_all_pass"])

    def test_missing_coverage_is_malformed(self):
        source = load()
        del source["datasets"][0]["coverage"]
        with self.assertRaisesRegex(ValueError, "coverage is required"):
            performance_gate.compare(source)

    def test_missing_runtime_is_malformed(self):
        source = load()
        del source["datasets"][0]["runtime_s"]
        with self.assertRaisesRegex(ValueError, "runtime_s is required"):
            performance_gate.compare(source)

    def test_unsupported_constraint_is_malformed(self):
        source = load()
        source["constraints"]["min_recall"] = 0.9
        with self.assertRaisesRegex(ValueError, "unsupported"):
            performance_gate.compare(source)

    def test_bad_constraints_type_is_malformed(self):
        source = load()
        source["constraints"] = []
        with self.assertRaisesRegex(ValueError, "constraints must be an object"):
            performance_gate.compare(source)

    def test_random_control_must_not_beat_hybrid(self):
        source = load()
        source["datasets"][0]["baselines"]["random_control"] = [0.95, 0.955, 0.945]
        source["datasets"][0]["baselines"]["base_a"] = [0.878, 0.887, 0.875]
        result = performance_gate.compare(source)
        self.assertNotEqual(result["verdict"], "promising")
        self.assertFalse(result["random_control_all_pass"])
        self.assertFalse(result["rows"][0]["random_control_pass"])

    def test_non_finite_metric_is_malformed(self):
        source = load()
        source["datasets"][0]["hybrid"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            performance_gate.compare(source)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            promising = run_cli(load(), tmp)
            self.assertEqual(promising.returncode, 0, promising.stderr)
            self.assertEqual(json.loads(promising.stdout)["verdict"], "promising")

            weak_source = load()
            weak_source["datasets"][1]["coverage"] = 0.5
            weak = run_cli(weak_source, tmp)
            self.assertEqual(weak.returncode, 3, weak.stderr)
            self.assertEqual(json.loads(weak.stdout)["verdict"], "weak")

            malformed_source = load()
            del malformed_source["stage"]
            malformed = run_cli(malformed_source, tmp)
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("performance_gate:", malformed.stderr)


if __name__ == "__main__":
    unittest.main()
