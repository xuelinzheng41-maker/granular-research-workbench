import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FreshClone(unittest.TestCase):
    def run_checked(self, command, cwd, env):
        result = subprocess.run(command, cwd=cwd, env=env, encoding="utf-8",
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tracked_tree_runs_without_local_state(self):
        listing = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            for raw in listing.split(b"\0"):
                if not raw:
                    continue
                relative = raw.decode("utf-8")
                source = ROOT / relative
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            env = dict(os.environ, PYTHONUTF8="1",
                       LAB_KB=str(root / "empty-kb"), LAB_IDEAS=str(root / "ideas"))
            self.run_checked([sys.executable, "-B", "-S",
                              "skills/research-idea/scripts/selftest.py"], repo, env)
            self.run_checked([sys.executable, "-B", "-m", "unittest", "discover",
                              "-s", "skills/research-idea/tests", "-v"], repo, env)
            self.run_checked([sys.executable, "-B", "-m", "unittest", "discover",
                              "-s", "workbench/tests", "-v"], repo, env)


if __name__ == "__main__":
    unittest.main()
