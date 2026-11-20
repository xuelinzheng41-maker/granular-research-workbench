import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def cli(script, *args, **env):
    return subprocess.run([sys.executable, "-B", "-S", str(SCRIPTS / script), *map(str, args)],
                          env=dict(os.environ, PYTHONUTF8="1") | env, text=True,
                          encoding="utf-8", errors="replace", capture_output=True, check=False)


class AuditRegressions(unittest.TestCase):
    def test_format_diagnostics_positive_and_never_a_scientific_pass(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            # Plausible structure, deliberately no scientific evidence.
            (folder / "idea.md").write_text(
                "为什么是空：待验证。UCI MNIST 对照。1 2 3 4 5\n" +
                "\n".join(title + "：" + "用来检查格式的文字" * 5 for title in
                          ("问题成因", "解决动机", "创新机制", "预期证据")) +
                "\n反例检索：仅记录检索措辞；适用的边界条件另记。", encoding="utf-8")
            (folder / "anchors.md").write_text(
                "arXiv:1706.03762 p. 3; arXiv:1810.04805 § 4; arXiv:2005.14165 Table 2", encoding="utf-8")
            (folder / "review.md").write_text("blocker\n" + "\n".join(
                f"拒稿理由 {i}\n如何预防：" + "只测试格式诊断的合成说明" * 4 for i in range(1, 4)), encoding="utf-8")
            run = cli("grade.py", "--external", root)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("格式分 14/14", run.stdout)
            self.assertIn("未核验执行", run.stdout)
            self.assertIn("科研结论仍须人工复核", run.stdout)
            self.assertNotIn("判定: 通过", run.stdout)

    def test_refute_flags_do_not_become_keywords(self):
        env = {"LAB_KB": str(FIXTURES / "corpus-split")}
        for flags in (("--limit=1",), ("--limit", "1")):
            run = cli("refute.py", "projection", "monotonicity", *flags, **env)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("split.txt", run.stdout)
        for flags in (("--limit", "abc"), ("--limit", "0"), ("--unknown",)):
            run = cli("refute.py", "projection", *flags, **env)
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertNotIn("Traceback", run.stderr)

    def test_kb_missing_yaml_reports_dependency_not_empty_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            cards = Path(root) / "92-论文卡"
            cards.mkdir()
            (cards / "card.md").write_text("---\ntier: 1\n---\nBody\n", encoding="utf-8")
            for command in ("doctor", "stats"):
                run = cli("kb.py", command, LAB_KB=root)
                self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
                self.assertIn("PyYAML", run.stderr)
                self.assertNotIn("状态: OK", run.stdout)

    def test_gaps_invalid_section_is_a_usage_error(self):
        run = cli("kb.py", "gaps", "--section", "(")
        self.assertEqual(run.returncode, 2)
        self.assertIn("invalid choice", run.stderr)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
