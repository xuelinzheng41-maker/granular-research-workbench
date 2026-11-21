"""Unit tests for runner.py."""
import unittest, sys, json, tempfile, shutil
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from runner import run_one, append_result, write_failure, _runner_self_hash, _sha256_file


class TestRunnerBasics(unittest.TestCase):
    def test_self_hash(self):
        h = _runner_self_hash()
        self.assertTrue(h.startswith("sha256:"))

    def test_sha256_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test")
        self.addCleanup(lambda: Path(f.name).unlink())
        h = _sha256_file(Path(f.name))
        self.assertEqual(len(h), 71)

    def test_env_snapshot(self):
        from runner import _env_snapshot
        env = _env_snapshot()
        self.assertIn("python", env)


class TestRunOne(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.method = self.tmp / "method.py"
        self.method.write_text(
            "import numpy as np\n"
            "def fit_predict(x_train, y_train, x_test, *, seed, budget_s):\n"
            "    return {'predictions': [0]*len(x_test), 'coverage': None, 'artifacts': {}}\n"
        )
        self.X = np.random.rand(20, 3)
        self.y = np.array([0]*10 + [1]*10)
        self.X_test = np.random.rand(5, 3)
        self.y_test = np.array([0,1,0,1,0])

    def test_run_ok(self):
        row = run_one(
            arm_dir=self.tmp, dataset_id="T",
            X_train=self.X[:10], y_train=self.y[:10],
            X_test=self.X_test, y_test=self.y_test,
            seed=1, budget_s=5,
            protocol_sha256="sha256:x"*1,
        )
        self.assertEqual(row["status"], "ok")
        self.assertTrue(row["method_sha256"].startswith("sha256:"))
        self.assertTrue(row["runner_sha256"].startswith("sha256:"))

    def test_run_timeout(self):
        self.method.write_text(
            "import time\n"
            "def fit_predict(x_train, y_train, x_test, *, seed, budget_s):\n"
            "    time.sleep(budget_s * 3)\n"
            "    return {'predictions': [0]*len(x_test), 'coverage': None, 'artifacts': {}}\n"
        )
        row = run_one(
            arm_dir=self.tmp, dataset_id="T",
            X_train=self.X[:10], y_train=self.y[:10],
            X_test=self.X_test, y_test=self.y_test,
            seed=1, budget_s=1,
            protocol_sha256="sha256:x"*1,
        )
        self.assertEqual(row["status"], "timeout")

    def test_run_tamper_detected(self):
        """Method that rewrites itself -> invalid."""
        self.method.write_text(
            "import pathlib\n"
            "def fit_predict(x_train, y_train, x_test, *, seed, budget_s):\n"
            "    p = pathlib.Path(__file__)\n"
            "    p.write_text(p.read_text() + '# x\\n')\n"
            "    return {'predictions': [0]*len(x_test), 'coverage': None, 'artifacts': {}}\n"
        )
        row = run_one(
            arm_dir=self.tmp, dataset_id="T",
            X_train=self.X[:10], y_train=self.y[:10],
            X_test=self.X_test, y_test=self.y_test,
            seed=1, budget_s=5,
            protocol_sha256="sha256:x"*1,
        )
        self.assertEqual(row["status"], "invalid")


class TestIO(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_append_result(self):
        p = self.tmp / "out" / "results.jsonl"
        row = {"dataset": "D", "arm": "A", "seed": 1, "status": "ok"}
        append_result(p, row)
        lines = p.read_text().strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["dataset"], "D")

    def test_write_failure(self):
        d = self.tmp / "failures"
        row = {"dataset": "D", "arm": "A", "seed": 1, "status": "timeout"}
        write_failure(d, row)
        ff = list(d.glob("*.json"))
        self.assertEqual(len(ff), 1)


if __name__ == "__main__":
    unittest.main()
