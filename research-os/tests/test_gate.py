"""Gate adapter compatibility without historical run files."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from gates import run_gate


class GateCompatibility(unittest.TestCase):
    def evaluate(self, status):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            rows = [dict(dataset=ds, arm=arm, seed=seed, status=status,
                         metric=metric + seed / 10000 if status == "ok" else None)
                    for ds in ("DS1", "DS2") for seed in (11, 29, 47)
                    for arm, metric in (("hybrid", .80), ("naive_concat", .75),
                                        ("random_control", .60), ("ablate_x", .74))]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            return run_gate(path, min_datasets=2, stage="pilot", random_control_spec={
                "method": "synthetic fixture", "seed": 11, "matched_on": "dataset and seed"
            })[0]

    def test_complete_result_is_valid(self):
        self.assertIn(self.evaluate("ok"), (0, 3))

    def test_timeout_only_cannot_pass(self):
        self.assertIn(self.evaluate("timeout"), (2, 3))
