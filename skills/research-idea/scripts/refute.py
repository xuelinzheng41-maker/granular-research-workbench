#!/usr/bin/env python3
"""在全文语料里查「已知否定结果」：否定线索锚定 + ±3 行窗口

v1.7：从「同行同现」改为「否定线索锚定」——先找否定句，再看关键词是否在其 ±3 行内。
原因：真实论文很少把关键词和否定词写在同一行（审计用例 split.txt 即证明原策略会漏）。

用法: refute.py "kw1" ["kw2"] [--limit=5]
环境变量: LAB_KB（默认 /opt/lab/kb）
"""
import argparse
import glob
import os
import re
import sys

KB = os.environ.get("LAB_KB", "/opt/lab/kb")
CORPUS = os.path.join(KB, "86-全文语料")
WINDOW = 3
NEG_CUES = (
    "impossibility", "impossible", "cannot", "can not", "no consistent",
    "counterexample", "counter-example", "negative result", "fails to",
    "does not imply", "not a valid", "no free lunch",
    "不可能", "无法保证", "反例", "不成立", "失效", "不兼容",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("keywords", nargs="+")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if any(not keyword.strip() for keyword in args.keywords):
        parser.error("keywords must not be empty")
    if not os.path.isdir(CORPUS):
        print("没有 %s；先同步全文语料到 kb/86-全文语料/" % CORPUS)
        return 1
    kws = [k.strip().lower() for k in args.keywords]
    total = 0
    for p in sorted(glob.glob(os.path.join(CORPUS, "*.txt"))):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        low = txt.lower()
        if not all(k in low for k in kws):
            continue
        lines = txt.splitlines()
        hits = []
        for i, ln in enumerate(lines):
            l = ln.lower()
            if not any(n in l for n in NEG_CUES):
                continue
            lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
            window = " ".join(lines[lo:hi]).lower()
            if not all(k in window for k in kws):
                continue
            same = all(k in l for k in kws)
            kind = "同行" if same else "窗口±%d行" % WINDOW
            hits.append((i + 1, kind, re.sub(r"\s+", " ", ln.strip())[:200]))
        if hits:
            print("### %s   命中 %d 处" % (os.path.basename(p), len(hits)))
            for no, kind, text in hits[:args.limit]:
                print("  L%d [%s]: %s" % (no, kind, text))
            total += len(hits)
    if total == 0:
        print("未发现明显否定结果；这只说明语料内没有，不等于领域内没有")
    else:
        print("")
        print("共 %d 处。逐条判断：直接反例（作废）/ 领域限制（改表述）/ 相关工作（边界条件）" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())