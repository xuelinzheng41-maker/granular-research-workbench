#!/usr/bin/env python3
"""research-idea 工具箱：知识库体检 + 检索 + 空位 + 可行性 + 脚手架

环境变量：
  LAB_KB      知识库根目录（默认 /opt/lab/kb）
  LAB_DATA    数据集目录（默认 /opt/lab/datasets/parquet）
  LAB_IDEAS   产出目录（发行副本默认 ./ideas，云端原位默认 /opt/lab/ideas）

子命令：
  doctor                     知识库体检（卡片数/字段缺失/空位行数/数据集覆盖）
  stats                      方法族 × 层级分布（判断哪个族群被研究透了）
  gaps --section A|B|C       空位表（A=无人做 B=没解决 C=已解决）
  search "kw" [--tier N] [--family F]
  anchors "kw1 kw2" --n 5    选锚点（tier 加权，排除二手整理稿）
  show "卡片名"
  feasibility "卡片名"        卡片声明的数据集 vs 本地数据集
  falsified                  读 kb/85-先前结论 下的已证伪方向
  draft <slug>               创建候选目录和探针模板
  scaffold <candidate-id>   探针通过后生成正式三件套
"""
import argparse
import glob
import os
import re
import shutil
import sys
import datetime
from pathlib import Path

from probe import SELECTION, ProbeError, check_result, read_record, save_new, select_candidate

try:
    import yaml
except ImportError:
    yaml = None

KB = os.environ.get("LAB_KB", "/opt/lab/kb")
CARDS = os.path.join(KB, "92-论文卡")
DATASETS = os.environ.get("LAB_DATA", "/opt/lab/datasets/parquet")
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IDEAS = "/opt/lab/ideas" if Path(HERE) == Path("/opt/lab/skills/research-idea/scripts") else "ideas"
IDEAS = os.environ.get("LAB_IDEAS", DEFAULT_IDEAS)
TIER_WEIGHT = {1: 4, 2: 3, 3: 2, 4: 1}
SECONDARY = ("整理稿", "学习稿", "综述", "导读", "笔记")


def read_card(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    meta, body = {}, txt
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", txt, re.S)
    if m:
        if yaml is None:
            raise ValueError("PyYAML 未安装，无法读取论文卡元数据；运行 python -m pip install PyYAML")
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: YAML 元数据无效") from exc
        if not isinstance(meta, dict):
            raise ValueError(f"{path}: YAML 元数据必须为映射")
        body = m.group(2)
    return meta, body, txt


def all_cards(include_secondary=True):
    out = []
    for p in glob.glob(os.path.join(CARDS, "*.md")):
        base = os.path.basename(p)
        if base.startswith("00-"):
            continue
        if not include_secondary and any(k in base for k in SECONDARY):
            continue
        meta, body, txt = read_card(p)
        out.append({"path": p, "name": base[:-3], "meta": meta, "body": body, "txt": txt})
    return out


def gaps_file():
    p = os.path.join(CARDS, "00-空位汇总（T1+T2）.md")
    if os.path.exists(p):
        return p
    cand = glob.glob(os.path.join(CARDS, "00-空位汇总*.md"))
    return cand[0] if cand else None


def gap_rows(section=None):
    p = gaps_file()
    if not p:
        return []
    rows = []
    for ln in open(p, encoding="utf-8").read().splitlines():
        if not ln.strip().startswith("|"):
            continue
        if not re.search(r"\b[ABC]\d{2}b?\b", ln):
            continue
        if "A01–A13" in ln:
            continue
        if section and not re.search(r"\b" + section + r"\d{2}", ln):
            continue
        rows.append(ln)
    return rows


def local_datasets():
    if not os.path.isdir(DATASETS):
        return {}
    return {f[:-8]: f[:-8] for f in os.listdir(DATASETS) if f.endswith(".parquet")}


def cmd_doctor(a):
    cards = all_cards()
    print("知识库: %s" % KB)
    print("  论文卡: %d 张（含二手 %d）" % (len(cards), len([c for c in cards if any(k in c["name"] for k in SECONDARY)])))
    miss = {k: sum(1 for c in cards if not c["meta"].get(k)) for k in ("tier", "method_family", "datasets", "metrics")}
    print("  字段缺失: " + ", ".join("%s=%d" % (k, v) for k, v in miss.items()))
    rows = gap_rows()
    print("  空位行: %d 行（A=%d B=%d C=%d）" % (
        len(rows),
        len(gap_rows("A")), len(gap_rows("B")), len(gap_rows("C"))))
    print("  数据集: %d 个（%s）" % (len(local_datasets()), DATASETS))
    fal = os.path.join(KB, "85-先前结论")
    print("  已证伪目录: %s" % ("有" if os.path.isdir(fal) else "无（可后续补）"))
    ok = len(cards) > 0 and len(rows) > 0
    print("  状态: " + ("OK" if ok else "异常：卡片或空位表缺失"))
    return 0 if ok else 1


def cmd_stats(a):
    cards = all_cards(include_secondary=False)
    fam, tier = {}, {}
    for c in cards:
        f = str(c["meta"].get("method_family") or "未标注")
        fam[f] = fam.get(f, 0) + 1
        t = str(c["meta"].get("tier") or "?")
        tier[t] = tier.get(t, 0) + 1
    print("层级分布: " + ", ".join("T%s=%d" % (k, v) for k, v in sorted(tier.items())))
    print("方法族分布（真论文，%d 张）：" % len(cards))
    for k, v in sorted(fam.items(), key=lambda x: -x[1]):
        print("  %-42s %d" % (k, v))
    print()
    print("解读：一族卡片越多 = 越拥挤；少且 tier 高的族往往是空位富矿")


def cmd_gaps(a):
    rows = gap_rows(a.section)
    if not rows:
        print("没有匹配的空位行")
        return
    for ln in rows[: a.limit]:
        print(ln[:240])


def fmt_card(c, extra=""):
    m = c["meta"]
    s = "%s\n  tier=%s family=%s task=%s\n  datasets=%s\n  %s" % (
        c["name"], m.get("tier"), m.get("method_family"), m.get("task"), m.get("datasets"), c["path"])
    return s + (("\n  " + extra) if extra else "")


def cmd_search(a):
    kw = a.keyword.lower()
    n = 0
    for c in all_cards():
        if a.tier and str(c["meta"].get("tier")) != str(a.tier):
            continue
        if a.family and a.family not in str(c["meta"].get("method_family") or ""):
            continue
        if kw not in c["txt"].lower():
            continue
        hit = ""
        for ln in c["body"].splitlines():
            if kw in ln.lower() and len(ln.strip()) > 10:
                hit = ln.strip()[:120]
                break
        print(fmt_card(c, hit))
        print()
        n += 1
        if n >= a.limit:
            break
    if n == 0:
        print("没有命中（换关键词，或用 --family 放宽）")


def cmd_show(a):
    for c in all_cards():
        if a.name.lower() in c["name"].lower():
            print(c["txt"])
            return
    print("找不到卡片:", a.name)


def cmd_anchors(a):
    kws = [k.lower() for k in a.topic.split()]
    scored = []
    for c in all_cards(include_secondary=a.include_secondary):
        title = str(c["meta"].get("title") or "").lower()
        body = c["body"].lower()
        score, reasons = 0, []
        for k in kws:
            t, b = title.count(k), min(body.count(k), 5)
            if t:
                score += t * 5
                reasons.append("标题命中 %s×%d" % (k, t))
            if b:
                score += b
                reasons.append("正文命中 %s×%d" % (k, b))
        if score == 0:
            continue
        try:
            score += TIER_WEIGHT.get(int(c["meta"].get("tier")), 0)
        except Exception:
            pass
        scored.append((score, c, reasons))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        print("没有匹配，换关键词")
        return
    print("候选锚点（相关性 + tier 加权）：")
    for i, (s, c, r) in enumerate(scored[: a.n], 1):
        m = c["meta"]
        print("%d. %s  [score %d]" % (i, c["name"], s))
        print("   tier=%s family=%s" % (m.get("tier"), m.get("method_family")))
        print("   %s" % "; ".join(r[:3]))
        print("   %s" % c["path"])


def norm(s):
    s = str(s).lower().strip()
    for suf in ("_official", "-official"):
        s = s.replace(suf, "")
    return re.sub(r"[^a-z0-9]", "", s)


def cmd_feasibility(a):
    local = {norm(k): v for k, v in local_datasets().items()}
    for c in all_cards():
        if a.name.lower() not in c["name"].lower():
            continue
        ds = c["meta"].get("datasets") or []
        if isinstance(ds, str):
            ds = [ds]
        print("卡片:", c["name"])
        if not ds:
            print("  未标注数据集")
            return
        if len(ds) == 1 and len(str(ds[0])) > 40:
            print("  数据集是自然语言描述，无法自动比对：")
            print("   ", str(ds[0])[:200])
            print("  → 人工抽出具体数据集名后再核对")
            return
        for d in ds:
            hit = local.get(norm(d))
            print("  %-28s %s" % (d, ("OK  有 " + hit) if hit else "MISS 缺"))
        return
    print("找不到卡片:", a.name)


def cmd_falsified(a):
    d = os.path.join(KB, "85-先前结论")
    if not os.path.isdir(d):
        print("没有 85-先前结论 目录；可从旧工作区同步已证伪清单后重试")
        return
    hits = 0
    for p in sorted(glob.glob(os.path.join(d, "**/*.md"), recursive=True)):
        for ln in open(p, encoding="utf-8", errors="ignore"):
            if re.match(r"^##\s*方向\s*\d+", ln.strip()):
                print("%s  ← %s" % (ln.strip(), os.path.basename(p)))
                hits += 1
    if not hits:
        print("未找到「## 方向 N」结构的已证伪条目")


SLUG = r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}"
TEMPLATES = Path(HERE).parent / "templates"


def write_new(dst, text):
    with dst.open("x", encoding="utf-8") as file:
        file.write(text)


def cmd_draft(a):
    if not re.fullmatch(SLUG, a.slug):
        print("draft: slug 必须为 1–80 个字母/数字/连字符/下划线，且以字母或数字开头", file=sys.stderr)
        return 2
    if (a.brief is None) != (a.candidate is None):
        raise ValueError("draft: --brief and --candidate must be given together")
    selection = None
    if a.brief is not None:
        selection, fields = select_candidate(read_record(a.brief.parent, a.brief.name), a.candidate)
        plan = read_record(TEMPLATES, "probe-plan.json")
        plan.update(fields, implementation=dict(path="", reproduce=""))
    out = Path(IDEAS) / f"{datetime.date.today().isoformat()}-{a.slug}"
    try:
        out.mkdir(parents=True, exist_ok=False)
        for name in ("probe-plan.json", "probe-result.json", "probe-review.json"):
            if name == "probe-plan.json" and selection is not None:
                save_new(out, SELECTION, selection)
                save_new(out, name, plan)
            else:
                shutil.copyfile(TEMPLATES / name, out / name)
    except OSError as exc:
        print(f"draft: {exc}", file=sys.stderr)
        return 2
    print(f"候选 ID: {out.name}\n目录: {out}")


def cmd_scaffold(a):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-" + SLUG, a.candidate_id):
        print("scaffold: 请使用 draft 生成的带日期候选 ID", file=sys.stderr)
        return 2
    out = Path(IDEAS) / a.candidate_id
    try:
        if out.is_symlink():
            raise ProbeError("不接受符号链接候选目录")
        status = check_result(out)
        if status != "advance":
            print(f"scaffold: {status}，保留探针记录，不生成正式三件套", file=sys.stderr)
            return 3
        contents = {
            "idea.md": (TEMPLATES / "idea.md").read_text(encoding="utf-8"),
            "review.md": (TEMPLATES / "reviewer.md").read_text(encoding="utf-8"),
            "anchors.md": "# 锚点清单\n\n（每篇写「做到哪 / 卡在哪」）\n",
        }
        if any((out / name).exists() or (out / name).is_symlink() for name in contents):
            raise ProbeError("已存在正式文件，不覆盖")
        for name, text in contents.items():
            write_new(out / name, text)
    except (ProbeError, OSError, RuntimeError) as exc:
        print(f"scaffold: {exc}", file=sys.stderr)
        return 2
    print(f"已创建正式三件套: {out}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    s = sub.add_parser("gaps"); s.add_argument("--section", type=str.upper, choices=("A", "B", "C")); s.add_argument("--limit", type=int, default=12); s.set_defaults(fn=cmd_gaps)
    s = sub.add_parser("search"); s.add_argument("keyword"); s.add_argument("--tier"); s.add_argument("--family"); s.add_argument("--limit", type=int, default=10); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("show"); s.add_argument("name"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("anchors"); s.add_argument("topic"); s.add_argument("--n", type=int, default=5); s.add_argument("--include-secondary", action="store_true"); s.set_defaults(fn=cmd_anchors)
    s = sub.add_parser("feasibility"); s.add_argument("name"); s.set_defaults(fn=cmd_feasibility)
    sub.add_parser("falsified").set_defaults(fn=cmd_falsified)
    s = sub.add_parser("draft")
    s.add_argument("slug")
    s.add_argument("--brief", type=Path)
    s.add_argument("--candidate", help="eligible ID from the comparison brief")
    s.set_defaults(fn=cmd_draft)
    s = sub.add_parser("scaffold"); s.add_argument("candidate_id"); s.set_defaults(fn=cmd_scaffold)

    a = p.parse_args()
    try:
        return a.fn(a) or 0
    except (ValueError, OSError) as exc:
        print(f"kb: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
