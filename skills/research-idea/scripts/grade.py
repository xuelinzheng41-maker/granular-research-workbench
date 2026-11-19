#!/usr/bin/env python3
"""按 rubric.md 给 ideas/<dir>/ 打分（14 分制）。

v1.9：新增「自我声明空洞」检测、数字密度要求；修正 --external 模式的两处误判；
      新增 --verify-refs 联网核验 arXiv 号是否存在。
用法: grade.py [--external] [--verify-refs] <dir>
"""
import glob
import os
import re
import sys

KB = os.environ.get("LAB_KB", "/opt/lab/kb")
DATA = os.environ.get("LAB_DATA", "/opt/lab/datasets/parquet")
PLACEHOLDER = re.compile(r"^\s*(待验证|待补|TBD|TODO|待定)[。.]?\s*$", re.I)
CITE = re.compile(r"(?:kb/)?(?:92-论文卡|86-全文语料)/[^|、，；。`\n]{1,120}?\.(?:md|txt)")
EXT = re.compile(r"arXiv:\s*\d{4}\.\d{4,5}|10\.\d{4,}/[^\s,;)]+", re.I)
ARXIV_ID = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})")

# 「作者自己声明这稿不是研究」的信号：真实稿件几乎不会出现
VACUOUS = ("仅用于检验", "不是研究提案", "仅作格式填充", "不支撑正文", "合成负面对照", "仅为词条填充")
PUBLIC_DS = ("SMDB", "SMD", "SWaT", "MSL", "SMAP", "UCR", "UCI", "PSM", "MBA",
             "KPI", "NIPS", "TEP", "Credit", "Shuttle", "MNIST", "ImageNet", "CIFAR")


def read(d, name):
    p = os.path.join(d, name)
    return open(p, encoding="utf-8", errors="ignore").read() if os.path.exists(p) else ""


def gap_ids():
    p = os.path.join(KB, "92-论文卡", "00-空位汇总（T1+T2）.md")
    if not os.path.exists(p):
        return set()
    return set(re.findall(r"\b[ABC]\d{2}b?\b", open(p, encoding="utf-8", errors="ignore").read()))


def verify_arxiv(ids):
    import urllib.request
    bad = []
    for i in ids:
        try:
            body = urllib.request.urlopen(
                "http://export.arxiv.org/api/query?id_list=" + i, timeout=20
            ).read().decode("utf-8", "ignore")
            if "<entry>" not in body:
                bad.append(i)
        except Exception:
            bad.append(i)
    return bad


def score_dir(d, external=False):
    idea, anchors, review = read(d, "idea.md"), read(d, "anchors.md"), read(d, "review.md")
    allt = idea + anchors + review
    rows = []

    def add(name, pts, note):
        rows.append((name, pts, note))

    ph = [ln for ln in allt.splitlines() if PLACEHOLDER.match(ln)]
    vac = [v for v in VACUOUS if v in allt]

    cites = {c[3:] if c.startswith("kb/") else c for c in CITE.findall(allt)}
    real = [c for c in cites if os.path.exists(os.path.join(KB, c))]
    fake = [c for c in cites if c not in real]
    detail = len(re.findall(r"(Table\s*\d+|p\.\s*\d+|§\s*\d)", allt))
    n_ext = len(set(EXT.findall(allt)))
    nums = len(re.findall(r"\d+(?:\.\d+)?", idea))

    # 1 出发点
    ids = gap_ids()
    found = [m for m in re.findall(r"\b[ABC]\d{2}b?\b", idea) if m in ids]
    why = any(k in idea for k in ("为什么是空", "为空的", "单篇占位", "无人做", "没人做过", "尚无"))
    if external:
        p1 = 2 if (why and n_ext >= 2) else (1 if why else 0)
        add("1 空位陈述", p1, "空缺说明=%s，支撑文献 %d" % (why, n_ext))
    else:
        add("1 从空位表出发", 2 if (found and why) else (1 if found else 0),
            ("真实编号 " + found[0]) if found else "编号不在空位表中")

    # 2 引用
    if external:
        p2 = 2 if (n_ext >= 3 and detail >= 3) else (1 if n_ext else 0)
        add("2 断言有来源", p2, "外部标识 %d，页码表号 %d" % (n_ext, detail))
    else:
        if fake:
            p2 = 0
        elif real and len(real) >= 3 and detail >= 3:
            p2 = 2
        elif real:
            p2 = 1
        else:
            p2 = 0
        add("2 断言有来源", p2, "真实引用 %d / 虚构 %d，页码表号 %d" % (len(real), len(fake), detail))

    # 3 反例检索
    did = ("refute" in allt.lower()) or ("反例检索" in allt) or ("negative result" in allt.lower())
    handled = any(k in allt for k in ("直接反例", "领域限制", "边界条件", "不可能", "阳性对照", "反例说明"))
    add("3 反例检索", 2 if (did and handled) else (1 if did else 0), "做了" if did else "没做")

    # 4 逻辑链（每段 ≥30 字，且全文数字 ≥5）
    segs = ["问题成因", "解决动机", "创新机制", "预期证据"]
    hit = 0
    for s in segs:
        m = re.search(s + r"(.{0,600})", idea, re.S)
        if m and len(m.group(1).strip()) >= 30:
            hit += 1
    p4 = 2 if (hit == 4 and nums >= 5) else (1 if hit >= 2 else 0)
    add("4 逻辑链四段", p4, "有效段落 %d/4，数字 %d 个" % (hit, nums))

    # 5 证据可执行
    local = {f[:-8].lower() for f in os.listdir(DATA) if f.endswith(".parquet")} if os.path.isdir(DATA) else set()
    named = {m.lower() for m in re.findall(r"\b([a-z][a-z0-9_]{2,})\b", idea)}
    okds = sorted(n for n in named if n in local or (n + "_official") in local)
    pub = [p for p in PUBLIC_DS if p.lower() in idea.lower()]
    if external:
        p5 = 2 if (len(pub) >= 2 and ("对照" in idea)) else (1 if pub else 0)
        add("5 证据可执行", p5, "公开数据集 %d 个：%s" % (len(pub), ",".join(pub[:3])))
    else:
        add("5 证据可执行", 2 if (len(okds) >= 3 and "对照" in idea) else (1 if okds else 0),
            "本地数据集 %d 个" % len(okds))

    # 6 对抗审查
    n_rej = len(re.findall(r"拒稿理由\s*\d", review))
    fixes = re.findall(r"如何预防[*]{0,2}[：:]\s*(.{0,300})", review)
    good_fix = [f for f in fixes if len(f.strip()) >= 25 and not PLACEHOLDER.match(f.strip())]
    has_blocker = "blocker" in review.lower()
    p6 = 2 if (n_rej >= 3 and len(good_fix) >= 3 and has_blocker) else (1 if n_rej >= 2 else 0)
    add("6 对抗审查", p6, "%d 条理由 / 有效处方 %d" % (n_rej, len(good_fix)))

    # 7 表述纪律
    bad = []
    for ln in allt.splitlines():
        if any(k in ln for k in ("禁用", "不得", "禁止", "避免", "不许", "别用", "不可")):
            continue
        bad += re.findall(r"显著提升|首次提出|效果很好|重大突破", ln)
    marked = ("待验证" in allt) or ("★" in allt) or ("△" in allt)
    add("7 表述纪律", 2 if (not bad and marked) else (1 if not bad else 0),
        ("违规词 " + ",".join(set(bad))) if bad else "无违规词")

    return rows, ph, len(real), len(fake), vac, n_ext


def main():
    ext_mode = "--external" in sys.argv
    verify = "--verify-refs" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    d = args[0]
    if not os.path.isdir(d):
        print("目录不存在:", d)
        return 2
    rows, ph, nreal, nfake, vac, n_ext = score_dir(d, ext_mode)
    print("评分对象: %s%s" % (d, "  [external]" if ext_mode else ""))
    print("-" * 64)
    total = 0
    for name, pts, note in rows:
        total += pts
        print("  %-16s %d/2   %s" % (name, pts, note))
    print("-" * 64)
    total = max(0, total - min(3, len(ph)) - 2 * nfake)
    print("  总分 %d/14   ｜ 占位行 %d ｜ 真实引用 %d / 虚构 %d ｜ 外部标识 %d"
          % (total, len(ph), nreal, nfake, n_ext))
    gates = {r[0][0]: r[1] for r in rows}
    ok = total >= 10 and gates["3"] > 0 and gates["6"] > 0
    reason = []
    if vac:
        ok = False
        reason.append("自我声明非研究：" + "、".join(vac))
    if len(ph) >= 3:
        ok = False
        reason.append("占位行 %d 条" % len(ph))
    if nfake > 0 and nreal == 0:
        ok = False
        reason.append("引用全为虚构")
    if verify and ext_mode and n_ext:
        bad = verify_arxiv(sorted(set(ARXIV_ID.findall(allt_of(d)))))
        if bad:
            ok = False
            reason.append("arXiv 号无法解析：" + ",".join(bad))
    print("  判定: %s%s" % ("通过" if ok else "不通过",
                            ("（" + "；".join(reason) + "）") if reason else ""))
    return 0 if ok else 1


def allt_of(d):
    return "".join(read(d, f) for f in ("idea.md", "anchors.md", "review.md"))


if __name__ == "__main__":
    sys.exit(main())