#!/usr/bin/env python3
"""回归自测：负对照必须失败，真产出必须通过。改任何脚本后先跑这个。"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
FIX = os.path.join(SKILL, "tests", "fixtures")
IDEAS = os.environ.get("LAB_IDEAS", "/opt/lab/ideas")
KB = os.environ.get("LAB_KB", "/opt/lab/kb")
PY = sys.executable


def run(cmd, env=None):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    if env:
        e.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True, env=e)
    return r.returncode, (r.stdout + r.stderr).strip()


def last(out):
    return out.splitlines()[-1] if out else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-kb", action="store_true", help="同时检查实际知识库及已有提案")
    args = parser.parse_args()
    checks = []
    grade = os.path.join(HERE, "grade.py")
    refute = os.path.join(HERE, "refute.py")

    g = os.path.join(FIX, "gaming")
    if os.path.isdir(g):
        code, out = run([PY, grade, g])
        checks.append(("负对照：空洞稿应判不合格", code == 1 and "有待检查项" in last(out), last(out)))
    else:
        checks.append(("负对照 fixture 存在", False, "缺 " + g))

    ge = os.path.join(FIX, "gaming-external")
    if os.path.isdir(ge):
        code, out = run([PY, grade, "--external", ge])
        checks.append(("负对照：external 空洞稿应判不合格", code == 1 and "有待检查项" in last(out), last(out)))
    else:
        checks.append(("external fixture 存在", False, "缺 " + ge))

    cs = os.path.join(FIX, "corpus-split")
    if os.path.isdir(cs):
        code, out = run([PY, refute, "projection", "monotonicity"], {"LAB_KB": cs})
        ok = code == 0 and ("窗口" in out) and ("split.txt" in out)
        checks.append(("refute：跨行反例应命中", ok, out.splitlines()[0] if out else ""))
    else:
        checks.append(("corpus-split fixture 存在", False, "缺 " + cs))

    if args.with_kb:
        add_kb_checks(checks, grade, refute)
    else:
        print("模式：独立安装（仅包内用例，不使用项目知识库或既有提案）")

    code, out = run([PY, os.path.join(SKILL, "tests", "test_audit.py")])
    checks.append(("diagnostics: CLI and fixture regressions", code == 0, last(out) if code == 0 else out))
    code, out = run([PY, os.path.join(SKILL, "tests", "test_probe.py")])
    checks.append(("probe：工作流回归（含无库定理型）", code == 0, last(out) if code == 0 else out))
    code, out = run([PY, os.path.join(SKILL, "tests", "test_validation.py")])
    checks.append(("validation：候选比较、原始回放、旧复核拦截", code == 0, last(out) if code == 0 else out))

    code, out = run([PY, os.path.join(SKILL, "tests", "test_handoff.py")])
    checks.append(("handoff: candidate, implementation, stale review", code == 0, last(out) if code == 0 else out))

    print("=" * 68)
    bad = 0
    for name, ok, note in checks:
        print("  [%s] %-38s %s" % ("PASS" if ok else "FAIL", name, note))
        if not ok:
            bad += 1
    print("=" * 68)
    print("  %d 项检查，%d 项失败" % (len(checks), bad))
    return 0 if bad == 0 else 1


def add_kb_checks(checks, grade, refute):
    print("模式：有库（同时检查当前项目环境）")
    if os.path.isdir(os.path.join(KB, "86-全文语料")):
        code, out = run([PY, refute, "impossibility", "--limit=1"], {"LAB_KB": KB})
        checks.append(("refute：真实语料应命中", code == 0 and "命中" in out and "共" in out,
                       out.splitlines()[0] if out else ""))
    code, out = run([PY, os.path.join(HERE, "kb.py"), "doctor"], {"LAB_KB": KB})
    checks.append(("kb doctor", code == 0, last(out)))
    for d in sorted(glob.glob(os.path.join(IDEAS, "*"))):
        name = os.path.basename(d)
        if not os.path.isfile(os.path.join(d, "idea.md")) or name.startswith("val-"):
            continue
        code, out = run([PY, grade, d])
        checks.append(("现有草案格式检查：" + name[:26], code == 0, last(out)))


if __name__ == "__main__":
    sys.exit(main())