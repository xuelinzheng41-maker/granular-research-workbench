import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import shortlist


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PerformancePreregistrationTests(unittest.TestCase):
    def setUp(self):
        self.source = load(ROOT / "examples/performance-brief.json")

    def reject(self, key, value, message):
        broken = copy.deepcopy(self.source)
        broken["candidates"][0]["performance"]["pre_registration"][key] = value
        with self.assertRaisesRegex(ValueError, message):
            shortlist.compare(broken)

    def test_example_binds_preregistration_before_results(self):
        result = shortlist.compare(self.source)
        self.assertEqual(result["mode"], "performance")
        for row in result["candidates"]:
            block = row["performance"]["pre_registration"]
            self.assertGreaterEqual(len(block["datasets"]), 2, row["id"])
            self.assertTrue(all(name.strip() for name in block["datasets"]), row["id"])
            self.assertGreaterEqual(len(block["seeds"]), 3, row["id"])
            self.assertEqual(len(block["seeds"]), len(set(block["seeds"])), row["id"])
            self.assertTrue(all(type(seed) is int and seed >= 0 for seed in block["seeds"]), row["id"])
            self.assertEqual(block["seeds"], sorted(set(block["seeds"])), row["id"])
            self.assertGreater(block["threshold"], 0, row["id"])
            self.assertIn(block["stage"], {"pilot", "full"}, row["id"])
            self.assertTrue(block["split"].strip(), row["id"])

    def test_missing_preregistration_is_rejected(self):
        broken = copy.deepcopy(self.source)
        del broken["candidates"][0]["performance"]["pre_registration"]
        with self.assertRaisesRegex(ValueError, "pre_registration must be an object"):
            shortlist.compare(broken)

    def test_fewer_than_two_datasets_is_rejected(self):
        self.reject("datasets", ["Waveform"],
                    "at least two datasets")

    def test_fewer_than_three_unique_seeds_is_rejected(self):
        self.reject("seeds", [13, 37],
                    "at least three unique seeds")
        self.reject("seeds", [13, 13, 37],
                    "at least three unique seeds")
        self.reject("seeds", [13, 37, 61, 61],
                    "must not repeat a seed")

    def test_non_integer_or_negative_seeds_are_rejected(self):
        self.reject("seeds", [13, 37, -61],
                    "non-negative integers")
        self.reject("seeds", [13, 37, "61"],
                    "non-negative integers")

    def test_non_positive_threshold_is_rejected(self):
        for threshold in (0, -0.01):
            with self.subTest(threshold=threshold):
                self.reject("threshold", threshold,
                            "positive number")

    def test_blank_split_is_rejected(self):
        self.reject("split", "   ",
                    "missing or blank split")

    def test_unknown_stage_is_rejected(self):
        self.reject("stage", "screening",
                    "stage must be pilot or full")

    def test_audit_brief_without_preregistration_is_unchanged(self):
        result = shortlist.compare(load(ROOT / "examples/brief.json"))
        self.assertEqual(result["mode"], "audit")
        self.assertTrue(all(row["performance"] is None for row in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
