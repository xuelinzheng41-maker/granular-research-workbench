"""
Unit tests for research-os/lib/datasets.py

Tests dataset registry, loaders, and verification.
"""

import unittest
import tempfile
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from datasets import (
    DatasetRegistry,
    DatasetStatus,
    load_dataset,
    load_text_pair,
    compute_file_sha256,
    get_label_distribution,
    verify_dataset,
)


class TestDatasetRegistry(unittest.TestCase):
    """Test dataset registry operations."""
    
    def test_create_empty_registry(self):
        """Test creating empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_path = Path(tmpdir) / "test.json"
            registry = DatasetRegistry(reg_path)
            
            self.assertEqual(registry.registry["schema_version"], 1)
            self.assertEqual(len(registry.registry["datasets"]), 0)
    
    def test_save_and_load_registry(self):
        """Test saving and loading registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_path = Path(tmpdir) / "test.json"
            
            # Create and save
            registry = DatasetRegistry(reg_path)
            registry.registry["root"] = "/test/path"
            registry.registry["datasets"].append({
                "id": "test_dataset",
                "data": "test.txt",
                "status": "ready"
            })
            registry.save()
            
            # Load
            registry2 = DatasetRegistry(reg_path)
            self.assertEqual(registry2.registry["root"], "/test/path")
            self.assertEqual(len(registry2.registry["datasets"]), 1)
            self.assertEqual(registry2.registry["datasets"][0]["id"], "test_dataset")
    
    def test_get_dataset(self):
        """Test getting dataset by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_path = Path(tmpdir) / "test.json"
            registry = DatasetRegistry(reg_path)
            
            registry.registry["datasets"].extend([
                {"id": "ds1", "data": "d1.txt"},
                {"id": "ds2", "data": "d2.txt"}
            ])
            
            ds = registry.get_dataset("ds1")
            self.assertIsNotNone(ds)
            self.assertEqual(ds["id"], "ds1")
            
            ds = registry.get_dataset("nonexistent")
            self.assertIsNone(ds)


class TestFileHashing(unittest.TestCase):
    """Test file hashing."""
    
    def test_compute_file_sha256(self):
        """Test computing file hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content", encoding='utf-8')
            
            hash_value = compute_file_sha256(test_file)
            
            self.assertTrue(hash_value.startswith("sha256:"))
            self.assertEqual(len(hash_value), 71)  # "sha256:" + 64 hex chars
    
    def test_file_not_found(self):
        """Test hashing non-existent file."""
        with self.assertRaises(FileNotFoundError):
            compute_file_sha256(Path("/nonexistent/file.txt"))


class TestTextLoader(unittest.TestCase):
    """Test text file loading."""
    
    def test_load_whitespace_delimited(self):
        """Test loading space-delimited files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "data.txt"
            labels_file = Path(tmpdir) / "labels.txt"
            
            # Create sample data
            data_file.write_text("1.0 2.0 3.0\n4.0 5.0 6.0\n")
            labels_file.write_text("0\n1\n")
            
            X, y = load_text_pair(data_file, labels_file)
            
            self.assertEqual(X.shape, (2, 3))
            self.assertEqual(y.shape, (2,))
            self.assertEqual(X[0, 0], 1.0)
            self.assertEqual(y[0], 0)
    
    def test_load_comma_delimited(self):
        """Test loading comma-delimited files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "data.txt"
            labels_file = Path(tmpdir) / "labels.txt"
            
            data_file.write_text("1.0,2.0,3.0\n4.0,5.0,6.0\n")
            labels_file.write_text("0\n1\n")
            
            X, y = load_text_pair(data_file, labels_file, delimiter="comma")
            
            self.assertEqual(X.shape, (2, 3))
            self.assertEqual(y.shape, (2,))
    
    def test_missing_data_file(self):
        """Test error on missing data file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            labels_file = Path(tmpdir) / "labels.txt"
            labels_file.write_text("0\n1\n")
            
            with self.assertRaises(FileNotFoundError):
                load_text_pair(Path(tmpdir) / "nonexistent.txt", labels_file)
    
    def test_length_mismatch(self):
        """Test error on data/labels length mismatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "data.txt"
            labels_file = Path(tmpdir) / "labels.txt"
            
            data_file.write_text("1.0 2.0\n3.0 4.0\n")
            labels_file.write_text("0\n")  # Only 1 label for 2 rows
            
            with self.assertRaises(ValueError):
                load_text_pair(data_file, labels_file)


class TestLabelDistribution(unittest.TestCase):
    """Test label distribution calculation."""
    
    def test_label_distribution(self):
        """Test getting label distribution."""
        y = np.array([1, 1, 2, 2, 2, 3])
        dist = get_label_distribution(y)
        
        self.assertEqual(dist["1"], 2)
        self.assertEqual(dist["2"], 3)
        self.assertEqual(dist["3"], 1)
    
    def test_label_distribution_floats(self):
        """Test distribution with float labels."""
        y = np.array([1.0, 1.0, 2.0, 3.0])
        dist = get_label_distribution(y)
        
        self.assertEqual(dist["1.0"], 2)
        self.assertEqual(dist["2.0"], 1)
        self.assertEqual(dist["3.0"], 1)


class TestDatasetsCheckDiagnostics(unittest.TestCase):
    """Synthetic regression tests for classification-readiness diagnostics."""

    def _run(self, tmp, entries, with_hash=()):
        import io, json, contextlib
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import cli
        root = Path(tmp)
        for e in entries:
            if e["id"] in with_hash:
                e["sha256"] = {"data": compute_file_sha256(root / e["data"]),
                               "labels": compute_file_sha256(root / e["labels"])}
        reg = root / "reg.json"
        reg.write_text(json.dumps({"schema_version": 1, "root": str(root), "datasets": entries}))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_datasets_check(reg)
        return code, out.getvalue()

    def _pair(self, root, name, labels):
        (root / f"{name}.txt").write_text("\n".join(f"{i} {i}" for i in range(len(labels))))
        (root / f"{name}_y.txt").write_text("\n".join(str(v) for v in labels))
        return {"id": name, "data": f"{name}.txt", "labels": f"{name}_y.txt",
                "loader": "txt_pair", "status": "ready"}

    def test_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [
                self._pair(root, "good", [0, 0, 1, 1]),
                self._pair(root, "nohash", [0, 1, 0, 1]),
                self._pair(root, "single", [0, 0, 0, 0]),
                {"id": "pending", "data": "x.mat", "loader": "mat_v73", "status": "needs_loader", "notes": "v7.3"},
            ]
            code, out = self._run(tmp, entries, with_hash=("good", "single"))
            self.assertEqual(code, 0)
            self.assertIn("Classification ready: 2 (good, nohash)", out)
            self.assertIn("single: not_ready:single_class", out)
            self.assertIn("nohash", out.split("Integrity unverified")[1].splitlines()[0])
            self.assertIn("pending: blocked:needs_loader", out)
            self.assertIn("MATLAB v7.3/h5py", out)
            self.assertNotIn("all verified", out.lower())

    def test_s1_unverified_still_classification_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._pair(Path(tmp), "nohash", [0, 1, 2, 1])
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 0)
            self.assertIn("Integrity: unverified:hash_not_declared", out)
            self.assertIn("Classification: ready", out)
            self.assertIn("Classification ready: 1 (nohash)", out)
            self.assertNotIn("all verified", out.lower())

    def test_s2_single_class_all_ones_and_zeros(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            code, out = self._run(tmp, [self._pair(r, "ones", [1, 1, 1]), self._pair(r, "zeros", [0, 0, 0])])
            self.assertEqual(code, 0)
            self.assertIn("ones: not_ready:single_class", out)
            self.assertIn("zeros: not_ready:single_class", out)
            self.assertNotIn("no_labels", out)
            self.assertIn("Classification ready: 0", out)

    def test_s4_mat_two_classes_ready(self):
        from scipy.io import savemat
        with tempfile.TemporaryDirectory() as tmp:
            savemat(str(Path(tmp) / "m.mat"), {"data": np.random.rand(4, 2), "label": np.array([0, 1, 0, 1])})
            e = {"id": "m", "data": "m.mat", "loader": "mat_v5", "status": "ready_with_scipy"}
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 0)
            self.assertIn("Classification ready: 1 (m)", out)

    def test_legacy_nonfinite_labels_fail_load_and_check(self):
        from scipy.io import savemat

        for loader in ("txt_pair", "mat_v5"):
            for value in (np.nan, np.inf, -np.inf):
                with self.subTest(loader=loader, value=value), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    labels = [0, value, -3, 7]
                    if loader == "txt_pair":
                        entry = self._pair(root, "legacy", labels)
                    else:
                        savemat(root / "legacy.mat", {"data": np.arange(8).reshape(4, 2), "label": labels})
                        entry = {"id": "legacy", "data": "legacy.mat", "loader": loader,
                                 "status": "ready_with_scipy"}
                    with self.assertRaisesRegex(ValueError, "Non-finite label"):
                        load_dataset(entry, root)
                    code, out = self._run(tmp, [entry])
                    self.assertEqual(code, 2)
                    self.assertIn("Non-finite label", out)
                    self.assertIn("Integrity: load_error", out)
                    self.assertIn("legacy: not_ready:load_failed", out)
                    self.assertIn("Classification ready: 0", out)

    def test_legacy_finite_labels_keep_values_and_hashes(self):
        from scipy.io import savemat

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = [0, -3, 7, 0]
            txt = self._pair(root, "txt", expected)
            savemat(root / "legacy.mat", {"data": np.arange(8).reshape(4, 2), "label": expected})
            mat = {"id": "mat", "data": "legacy.mat", "loader": "mat_v5", "status": "ready_with_scipy"}
            for entry in (txt, mat):
                _, y, hashes = load_dataset(entry, root)
                np.testing.assert_array_equal(y, expected)
                self.assertEqual(hashes, {key: compute_file_sha256(root / entry[key])
                                          for key in ("data", "labels") if key in entry})
            code, out = self._run(tmp, [txt, mat])
            self.assertEqual(code, 0)
            self.assertIn("Classification ready: 2 (txt, mat)", out)

    def test_s5_needs_loader_file_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = {"id": "v73", "data": "none.mat", "loader": "mat_v73", "status": "needs_loader"}
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 0)
            self.assertIn("MATLAB v7.3/h5py", out)
            self.assertIn("Classification ready: 0", out)

    def test_s8_hash_match_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._pair(Path(tmp), "h", [0, 1])
            code, out = self._run(tmp, [e], with_hash=("h",))
            self.assertEqual(code, 0)
            self.assertIn("Integrity: verified", out)
            self.assertIn("Integrity verified: 1", out)

    def test_s10_rows_mismatch_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._pair(Path(tmp), "r", [0, 1])
            e["rows"] = 99
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 2)
            self.assertIn("Row count mismatch", out)
            self.assertIn("Classification ready: 0", out)

    def test_s11_corrupt_text_load_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._pair(Path(tmp), "c", [0, 1])
            (Path(tmp) / "c.txt").write_text("a b\nc d")
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 2)
            self.assertIn("Load error", out)
            self.assertIn("c: not_ready:load_failed", out)

    def test_empty_dataset_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            (r / "e.txt").write_text("")
            (r / "e_y.txt").write_text("")
            e = {"id": "e", "data": "e.txt", "labels": "e_y.txt", "loader": "txt_pair", "status": "ready"}
            code, out = self._run(tmp, [e])
            self.assertIn("Classification ready: 0", out)
            self.assertNotIn("Classification: ready", out)

    def test_s13_missing_registry_exit_2(self):
        import io, contextlib
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import cli
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.cmd_datasets_check(Path(tmp) / "nope.json"), 2)

    def test_placeholder_labels_not_ready(self):
        from scipy.io import savemat
        with tempfile.TemporaryDirectory() as tmp:
            savemat(str(Path(tmp) / "p.mat"), {"points": np.random.rand(5, 3)})
            e = {"id": "ph", "data": "p.mat", "loader": "mat_v5", "status": "ready_with_scipy"}
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 0)
            self.assertIn("ph: not_ready:no_labels", out)
            self.assertIn("Classification ready: 0", out)

    def test_missing_file_and_needs_data_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            miss = {"id": "gone", "data": "a.txt", "labels": "b.txt", "loader": "txt_pair", "status": "ready"}
            code, out = self._run(tmp, [miss])
            self.assertEqual(code, 2)
            self.assertIn("File not found", out)
            self.assertIn("Classification ready: 0", out)
            nd = {"id": "nd", "data": "a", "loader": "txt_pair", "status": "needs_data"}
            code, out = self._run(tmp, [nd])
            self.assertEqual(code, 2)
            self.assertIn("nd: blocked:needs_data", out)

    def test_hash_mismatch_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = self._pair(Path(tmp), "bad", [0, 1])
            e["sha256"] = {"data": "sha256:00", "labels": "sha256:00"}
            code, out = self._run(tmp, [e])
            self.assertEqual(code, 2)
            self.assertIn("bad:mismatch", out)
            self.assertIn("Classification ready: 0", out)


    def _mat_external(self, root):
        from scipy.io import savemat
        X = np.arange(6).reshape(3, 2)
        savemat(root / "m.mat", {"data": X, "label": [np.nan, np.inf, -np.inf]})
        labels = root / "sources" / "labels.txt"
        labels.parent.mkdir()
        labels.write_bytes(b"2\r\n0\r\n1\r\n")
        entry = {"id": "external", "data": "m.mat", "loader": "mat_v5",
                 "status": "ready_with_scipy", "usage": "classification",
                 "label_source": {"kind": "separate_file", "path": "sources/labels.txt"}}
        return entry, labels, X

    def test_mat_external_labels_keep_order_and_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry, labels, expected_X = self._mat_external(root)
            X, y, hashes = load_dataset(entry, root)
            np.testing.assert_array_equal(X, expected_X)
            np.testing.assert_array_equal(y, [2, 0, 1])
            self.assertEqual(hashes["labels"], compute_file_sha256(labels))
            code, out = self._run(tmp, [entry])
            self.assertEqual(code, 0)
            self.assertIn("Integrity: unverified:hash_not_declared", out)
            self.assertIn("Classification ready: 1 (external)", out)

    def test_mat_external_single_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry, labels, _ = self._mat_external(Path(tmp))
            labels.write_bytes(b"0\n0\n0\n")
            code, out = self._run(tmp, [entry])
            self.assertEqual(code, 0)
            self.assertIn("external: not_ready:single_class", out)
            self.assertIn("Classification ready: 0", out)

    def test_mat_external_labels_invalid_never_fall_back(self):
        cases = (
            (None, FileNotFoundError, "Labels file not found", "missing"),
            (b"0\ninvalid\n1\n", ValueError, "Invalid label format", "load_error"),
            (b"0 1 2\n", ValueError, "Invalid label format", "load_error"),
            (b"0\nNaN\n1\n", ValueError, "Non-finite label", "load_error"),
            (b"0\nInfinity\n1\n", ValueError, "Non-finite label", "load_error"),
            (b"0\n1\n", ValueError, "length mismatch", "load_error"),
        )
        for content, exc, message, integrity in cases:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                entry, labels, _ = self._mat_external(root)
                if content is None:
                    labels.unlink()
                else:
                    labels.write_bytes(content)
                with self.assertRaisesRegex(exc, message):
                    load_dataset(entry, root)
                code, out = self._run(tmp, [entry])
                self.assertEqual(code, 2)
                self.assertIn(message, out)
                self.assertIn(f"Integrity: {integrity}", out)
                self.assertIn("external: not_ready:load_failed", out)
                self.assertIn("Classification ready: 0", out)

    def test_mat_external_label_hash_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry, labels, _ = self._mat_external(root)
            entry["sha256"] = {"data": compute_file_sha256(root / entry["data"]),
                               "labels": compute_file_sha256(labels)}
            self.assertEqual(verify_dataset(entry, root), (True, None))
            code, out = self._run(tmp, [entry])
            self.assertEqual(code, 0)
            self.assertIn("Integrity: verified", out)
            self.assertIn("Classification ready: 1 (external)", out)

            labels.write_bytes(b"1\n2\n0\n")
            ok, error = verify_dataset(entry, root)
            self.assertFalse(ok)
            self.assertIn("SHA256 mismatch for labels", error)
            code, out = self._run(tmp, [entry])
            self.assertEqual(code, 2)
            self.assertIn("SHA256 mismatch for labels", out)
            self.assertIn("external:mismatch", out)
            self.assertIn("Classification ready: 0", out)

    def test_mat_explicit_clustering_only_ignores_embedded_labels(self):
        from scipy.io import savemat
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            X = np.arange(6).reshape(3, 2)
            savemat(root / "points.mat", {"points": X, "label": [np.nan, np.inf, -np.inf]})
            entry = {"id": "cluster", "data": "points.mat", "loader": "mat_v5",
                     "status": "ready_with_scipy", "usage": "clustering",
                     "label_source": {"kind": "none"}}
            points, y, hashes = load_dataset(entry, root)
            np.testing.assert_array_equal(points, X)
            np.testing.assert_array_equal(y, np.zeros(3))
            self.assertNotIn("labels", hashes)
            code, out = self._run(tmp, [entry])
            self.assertEqual(code, 0)
            self.assertIn("cluster: not_ready:clustering_only", out)
            self.assertNotIn("Distribution:", out)
            self.assertIn("Classification ready: 0", out)


if __name__ == '__main__':
    unittest.main()
