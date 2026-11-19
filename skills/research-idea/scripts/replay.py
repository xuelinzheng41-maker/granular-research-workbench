#!/usr/bin/env python3
"""Prepare reviewer inputs from bundled raw data; apply and score reviewer decisions."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import probe

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"
FORMAL = ("idea.md", "anchors.md", "review.md")
CASES = {
    "case-a": ("theory", "graphs.json", "There exist connected simple graphs with the same sorted degrees and different diameters."),
    "case-b": ("empirical", "streams.json", "On both named streams, key deduplication never finds fewer distinct true incidents than first-in-order alerts under the same cap."),
    "case-c": ("theory", "graphs.json", "Every pair of connected simple graphs with the same sorted degrees has equal diameter."),
    "case-d": ("empirical", "streams.json", "On duplicate_heavy, key deduplication detects at least two more distinct true incidents than first-in-order alerts, using the same number of alerts."),
}


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def graph_stats(edges):
    neighbors = {}
    for a, b in edges:
        if a == b or b in neighbors.get(a, ()):
            raise ValueError("expected simple graph edges")
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
    diameter = 0
    for start in neighbors:
        distance, queue = {start: 0}, deque([start])
        while queue:
            node = queue.popleft()
            for next_node in neighbors[node] - distance.keys():
                distance[next_node] = distance[node] + 1
                queue.append(next_node)
        if distance.keys() != neighbors.keys():
            raise ValueError("expected connected graph")
        diameter = max(diameter, max(distance.values()))
    return {"vertices": len(neighbors), "edges": len(edges),
            "degrees": sorted(map(len, neighbors.values())), "diameter": diameter}


def alerts(events, cap, *, deduplicate):
    indices, keys, hits = [], set(), set()
    for i, (key, incident) in enumerate(events, 1):
        if deduplicate and key in keys:
            continue
        keys.add(key)
        indices.append(i)
        if incident is not None:
            hits.add(incident)
        if len(indices) == cap:
            break
    return {"alert_rows_1_based": indices, "alert_count": len(indices),
            "true_incidents": sorted(hits), "distinct_true_count": len(hits)}


def recompute(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if path.name == "graphs.json":
        return {name: graph_stats(edges) for name, edges in data.items()}
    cap = data.pop("budget")
    if type(cap) is not int or cap < 1:
        raise ValueError("budget must be positive")
    return {name: {"cap": cap, "baseline": alerts(events, cap, deduplicate=False),
                   "dedup": alerts(events, cap, deduplicate=True)} for name, events in data.items()}


def call(root, script, *args):
    return subprocess.run([sys.executable, "-B", str(HERE / script), *map(str, args)],
                          env=dict(os.environ, LAB_IDEAS=str(root), PYTHONUTF8="1"),
                          text=True, encoding="utf-8", capture_output=True, check=False)


def require_code(result, want):
    if result.returncode != want:
        raise ValueError(f"expected exit {want}, got {result.returncode}: {result.stderr or result.stdout}")


def plan(kind, claim):
    maths = kind == "theory"
    return dict(kind=kind, source_kind="anomaly" if maths else "transfer",
                source="Bundled synthetic inputs, not a research contribution", question=claim, core_claim=claim,
                rival="Equal summaries may hide different structure." if maths else "Different incidents may share one key.",
                setup="Undirected simple graphs; unweighted diameter is the maximum shortest-path distance."
                if maths else "Rows arrive in the given order. Null is a non-incident. Count distinct named true incidents.",
                control="Check connectivity, sorted degrees and exact diameter on the same pair."
                if maths else "First cap rows vs first distinct keys, same input and cap; both consume one alert per admission.",
                advance_if="The computed evidence settles the stated claim in its exact scope.",
                stop_if="An in-scope counterexample exists or a required comparison is absent.", budget_minutes=15)


def prepare(root):
    root.mkdir()
    packet = {}
    for case, (kind, src, claim) in CASES.items():
        require_code(call(root, "kb.py", "draft", case), 0)
        folder, = root.glob(f"*-{case}")
        p = plan(kind, claim)
        (folder / "probe-plan.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        require_code(call(root, "probe.py", "plan", folder), 0)
        shutil.copyfile(EXAMPLES / src, folder / src)
        raw = json.loads((folder / src).read_text(encoding="utf-8"))
        readout = recompute(folder / src)
        save(folder / "readout.json", readout)
        r = dict(status="advance", observation="Computed readout attached; author asks for review.",
                 supported_claim="The raw inputs provide a bounded check of the proposed claim.",
                 limitations="Synthetic inputs; no novelty, population-level or publication claim.",
                 next_step="Independent decision on this exact claim.", artifacts=[src, "readout.json"])
        (folder / "probe-result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        require_code(call(root, "kb.py", "scaffold", folder.name), 2)
        if any((folder / name).exists() for name in FORMAL):
            raise ValueError("scaffold wrote formal files before review")
        digest = call(root, "probe.py", "review-input", folder)
        require_code(digest, 0)
        packet[case] = {"plan": p, "raw_input": raw, "computed_readout": readout,
                        "review_input_sha256": json.loads(digest.stdout)["review_input_sha256"]}
    save(root / "review-packet.json", packet)
    print(f"{len(packet)} candidates prepared; pre-review scaffold blocked in all cases")


def finish(root, review_file):
    decided = json.loads(review_file.read_text(encoding="utf-8"))
    if not isinstance(decided, dict) or set(decided) != set(CASES):
        raise ValueError("the review file must cover the exact four case IDs")
    rows, prepared = [], []
    for case in CASES:
        answer = decided[case]
        if not isinstance(answer, dict):
            raise ValueError(f"{case}: expected a review object")
        probe.require_fields(answer, case, "reviewer verdict evidence_location rival_check reason review_input_sha256")
        if answer["verdict"] not in ("direct", "proxy_only", "insufficient", "contradicted"):
            raise ValueError(f"{case}: invalid verdict")
        provenance = probe.review_provenance(answer, case)
        folder, = root.glob(f"*-{case}")
        if probe.read_record(folder, "probe-review.json").get("verdict") or any((folder / f).exists() for f in FORMAL):
            raise ValueError(f"{case}: already reviewed; prepare a fresh replay directory")
        digest = call(root, "probe.py", "review-input", folder)
        require_code(digest, 0)
        checksum = json.loads(digest.stdout)["review_input_sha256"]
        if checksum != answer["review_input_sha256"]:
            raise ValueError(f"{case}: the review digest does not match the current material; review again")
        prepared.append((case, folder, answer, checksum, provenance))
    # Compare only after all reviewer decisions are supplied and validated.
    reference = json.loads((EXAMPLES / "reference-review.json").read_text(encoding="utf-8"))
    for case, folder, answer, digest, provenance in prepared:
        record = {key: answer[key] for key in ("reviewer", "verdict", "evidence_location", "rival_check", "reason")}
        record.update(evidence_artifact="readout.json", review_input_sha256=digest, **provenance)
        (folder / "probe-review.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        want = 0 if record["verdict"] == "direct" else 3
        require_code(call(root, "probe.py", "check", folder), want)
        require_code(call(root, "kb.py", "scaffold", folder.name), want)
        files = [name for name in FORMAL if (folder / name).is_file()]
        if files != (list(FORMAL) if want == 0 else []):
            raise ValueError(f"{case}: unexpected scaffold outputs: {files}")
        rows.append(dict(case=case, verdict=record["verdict"], reference=reference[case]["verdict"],
                         scaffold_exit=want, formal_files=files))
    save(root / "replay-report.json", rows)
    matched = sum(row["verdict"] == row["reference"] for row in rows)
    print(f"Workflow: {len(rows)}/{len(rows)}; scientific verdict agreement: {matched}/{len(rows)}")
    return 0 if matched == len(rows) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare").add_argument("directory", type=Path)
    evaluate = sub.add_parser("finish")
    evaluate.add_argument("directory", type=Path)
    evaluate.add_argument("verdicts", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            prepare(args.directory.resolve())
            return 0
        return finish(args.directory.resolve(), args.verdicts)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"replay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
