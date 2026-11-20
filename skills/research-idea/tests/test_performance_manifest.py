import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import performance_manifest

EXAMPLE = ROOT / "examples/performance-manifest.json"
SCRIPT = ROOT / "scripts/performance_manifest.py"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def example():
    return copy.deepcopy(load(EXAMPLE))


class PerformanceManifestTests(unittest.TestCase):
    def test_example_is_valid(self):
        summary = performance_manifest.validate(example())
        self.assertEqual(summary["datasets"], 3)
        self.assertEqual(summary["checks"]["form"], "ok")
        self.assertEqual(summary["checks"]["files"], "not_checked")
        self.assertEqual(summary["split"]["group_column"], "subject_id")
        self.assertEqual(summary["split"]["folds"], 5)
        self.assertEqual(summary["split"]["seeds"], [13, 37, 61])
        self.assertEqual(summary["pilot"]["stage"], "pilot")
        self.assertEqual(summary["pilot"]["threshold"], 0.01)
        self.assertEqual(summary["pilot"]["dataset_count"], 3)
        self.assertEqual(summary["warnings"], [])

    def test_missing_sha256_is_rejected(self):
        source = example()
        del source["data"][0]["sha256"]
        with self.assertRaisesRegex(ValueError, "sha256"):
            performance_manifest.validate(source)

    def test_sha256_must_be_64_lowercase_hex(self):
        for bad in ("abc", "Z" * 64, "a" * 63, "a" * 65):
            source = example()
            source["data"][0]["sha256"] = bad
            with self.assertRaisesRegex(ValueError, "sha256"):
                performance_manifest.validate(source)

    def test_missing_seeds_is_rejected(self):
        source = example()
        del source["split"]["seeds"]
        with self.assertRaisesRegex(ValueError, "seeds"):
            performance_manifest.validate(source)

    def test_two_seeds_are_not_enough(self):
        source = example()
        source["split"]["seeds"] = [13, 37]
        with self.assertRaisesRegex(ValueError, "seeds"):
            performance_manifest.validate(source)

    def test_duplicate_seeds_are_rejected(self):
        source = example()
        source["split"]["seeds"] = [13, 13, 61]
        with self.assertRaisesRegex(ValueError, "duplicate seed"):
            performance_manifest.validate(source)

    def test_folds_below_two_are_rejected(self):
        source = example()
        source["split"]["folds"] = 1
        with self.assertRaisesRegex(ValueError, "folds"):
            performance_manifest.validate(source)

    def test_missing_group_column_is_rejected(self):
        source = example()
        del source["split"]["group_column"]
        with self.assertRaisesRegex(ValueError, "group_column"):
            performance_manifest.validate(source)

    def test_rows_and_features_must_be_positive(self):
        source = example()
        source["data"][0]["rows"] = 0
        with self.assertRaisesRegex(ValueError, "rows"):
            performance_manifest.validate(source)
        source = example()
        source["data"][0]["features"] = -3
        with self.assertRaisesRegex(ValueError, "features"):
            performance_manifest.validate(source)

    def test_one_dataset_is_not_enough(self):
        source = example()
        source["data"] = source["data"][:1]
        source["pilot"]["datasets"] = ["DatasetA"]
        with self.assertRaisesRegex(ValueError, "at least 2 datasets"):
            performance_manifest.validate(source)

    def test_duplicate_dataset_name_is_rejected(self):
        source = example()
        source["data"][1]["name"] = "DatasetA"
        with self.assertRaisesRegex(ValueError, "duplicate dataset name"):
            performance_manifest.validate(source)

    def test_pilot_datasets_must_exist_in_data(self):
        source = example()
        source["pilot"]["datasets"] = ["DatasetA", "DatasetZ"]
        with self.assertRaisesRegex(ValueError, "unknown dataset"):
            performance_manifest.validate(source)

    def test_pilot_requires_two_datasets(self):
        source = example()
        source["pilot"]["datasets"] = ["DatasetA"]
        with self.assertRaisesRegex(ValueError, "at least 2"):
            performance_manifest.validate(source)

    def test_pilot_stage_and_threshold_are_checked(self):
        source = example()
        source["pilot"]["stage"] = "quick"
        with self.assertRaisesRegex(ValueError, "stage"):
            performance_manifest.validate(source)
        source = example()
        source["pilot"]["threshold"] = 0
        with self.assertRaisesRegex(ValueError, "threshold"):
            performance_manifest.validate(source)

    def test_pilot_covering_fewer_datasets_warns(self):
        source = example()
        source["pilot"]["datasets"] = ["DatasetA", "DatasetB"]
        summary = performance_manifest.validate(source)
        self.assertEqual(len(summary["warnings"]), 1)
        self.assertIn("DatasetC", summary["warnings"][0])

    def test_check_files_binds_path_to_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "dataset_a.csv"
            data.write_bytes(b"name,label\nrow1,1\n")
            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            source = example()
            source["data"] = [
                dict(name="DatasetA", path="dataset_a.csv", sha256=digest,
                     rows=1, features=2, label="label"),
                dict(name="DatasetB", path="dataset_b.csv", sha256="b" * 64,
                     rows=2, features=2, label="label"),
            ]
            source["pilot"]["datasets"] = ["DatasetA", "DatasetB"]
            Path(tmp, "dataset_b.csv").write_bytes(b"x\n")
            # Wrong hash for a present file must fail.
            with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
                performance_manifest.validate(source, base_dir=tmp, check_files=True)
            source["data"][1]["sha256"] = hashlib.sha256(b"x\n").hexdigest()
            summary = performance_manifest.validate(source, base_dir=tmp, check_files=True)
            self.assertEqual(summary["checks"]["files"], "ok")
            self.assertTrue(all(row["sha256_verified"] for row in summary["data"]))
            # A declared file that is absent must fail.
            source["data"][1]["path"] = "missing.csv"
            with self.assertRaisesRegex(ValueError, "not found"):
                performance_manifest.validate(source, base_dir=tmp, check_files=True)

    def test_cli_exit_codes(self):
        ok = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(EXAMPLE)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        summary = json.loads(ok.stdout)
        self.assertEqual(summary["datasets"], 3)

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            source = example()
            del source["split"]["seeds"]
            bad.write_text(json.dumps(source), encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(bad)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            )
            self.assertEqual(broken.returncode, 2)
            self.assertIn("seeds", broken.stderr)

            missing = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(Path(tmp) / "nope.json")],
                capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            )
            self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
