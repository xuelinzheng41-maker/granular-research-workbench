import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = ("README.md", "LICENSE", "CHANGELOG.md", "STABILITY.md",
                "requirements-test.txt", ".github", "docs", "skills", "workbench", "tests")
SKIP_PARTS = {".git", "__pycache__", "runs"}


def source_files():
    for entry in SOURCE_PATHS:
        path = ROOT / entry
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not (set(child.parts) & SKIP_PARTS) and child.suffix != ".pyc":
                    yield child


class FreshClone(unittest.TestCase):
    def run_checked(self, command, cwd, env):
        result = subprocess.run(command, cwd=cwd, env=env, encoding="utf-8", errors="replace",
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_tree_runs_without_git_or_local_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            for source in source_files():
                target = repo / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                       LAB_KB=str(root / "empty-kb"), LAB_IDEAS=str(root / "ideas"))
            self.run_checked([sys.executable, "-B", "-S",
                              "skills/research-idea/scripts/selftest.py"], repo, env)
            self.run_checked([sys.executable, "-B", "-m", "unittest", "discover",
                              "-s", "skills/research-idea/tests", "-v"], repo, env)
            self.run_checked([sys.executable, "-B", "-m", "unittest", "discover",
                              "-s", "workbench/tests", "-v"], repo, env)


if __name__ == "__main__":
    unittest.main()
