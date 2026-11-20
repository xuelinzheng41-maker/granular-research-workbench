import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import component_score

EXAMPLE = ROOT / "examples/component-score.json"
SCRIPT = ROOT / "scripts/component_score.py"


def example():
    return copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def ranking(summary):
    return {row["id"]: row for row in summary["ranking"]}


class ComponentScoreTests(unittest.TestCase):
    def test_complementary_pair_ranks_above_redundant_pair(self):
        summary = component_score.validate(example())
        self.assertEqual([row["id"] for row in summary["ranking"]],
                         ["cover-plus-evidence", "cover-plus-point-pruning"])
        complementary = ranking(summary)["cover-plus-evidence"]
        redundant = ranking(summary)["cover-plus-point-pruning"]
        self.assertGreater(complementary["scores"]["complementarity"],
                           redundant["scores"]["complementarity"])
        self.assertEqual(redundant["scores"]["complementarity"], 0.0)
        self.assertGreater(complementary["scores"]["total"],
                           redundant["scores"]["total"])
        self.assertIn("Ranking aid only", summary["limits"])
        self.assertIn("not evidence", summary["limits"])

    def test_scores_are_bounded_and_use_at_most_three_decimals(self):
        for row in component_score.validate(example())["ranking"]:
            for key, value in row["scores"].items():
                with self.subTest(pair=row["id"], score=key):
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 1.0)
                    self.assertEqual(round(value, 3), value)
                    decimals = len(f"{value:.10f}".split(".")[1].rstrip("0"))
                    self.assertLessEqual(decimals, 3)

    def test_missing_fields_are_rejected(self):
        component_fields = ("id", "bottleneck", "cost", "data_ready")
        pair_fields = ("id", "baseline_strength", "expected_gain")
        for field in component_fields:
            source = example()
            del source["pairs"][0]["components"][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                component_score.validate(source)
        for field in pair_fields:
            source = example()
            del source["pairs"][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                component_score.validate(source)

    def test_invalid_values_are_rejected(self):
        cases = (("cost", -0.1, "cost"),
                 ("baseline_strength", 1.2, "baseline_strength"),
                 ("expected_gain", -0.1, "expected_gain"),
                 ("data_ready", "yes", "data_ready"))
        for field, value, message in cases:
            source = example()
            target = source["pairs"][0]["components"][0] if field == "data_ready" else source["pairs"][0]
            target[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                component_score.validate(source)

    def test_ties_break_by_pair_id(self):
        source = example()
        first = copy.deepcopy(source["pairs"][0])
        second = copy.deepcopy(source["pairs"][0])
        first["id"], second["id"] = "beta-pair", "alpha-pair"
        source["pairs"] = [first, second]
        summary = component_score.validate(source)
        self.assertEqual([row["id"] for row in summary["ranking"]],
                         ["alpha-pair", "beta-pair"])

    def test_cli_exit_codes(self):
        ok = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(EXAMPLE)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["ranking"][0]["id"],
                         "cover-plus-evidence")
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            source = example()
            del source["pairs"][0]["components"][0]["cost"]
            bad.write_text(json.dumps(source), encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(bad)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            )
            self.assertEqual(broken.returncode, 2)
            self.assertIn("cost", broken.stderr)


if __name__ == "__main__":
    unittest.main()
