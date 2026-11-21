"""Allowlisted portable view of a completed local launch."""
import json
import math
import re

from launch import approved, compile_protocol, create, digest, encode, read, require


def package(run, p, sha, limit, *, inspect=False):
    require(0 < limit <= 8_000_000, "packet byte limit must be in 1..8000000")
    approved(run, "H1", sha)
    protocol = compile_protocol({"payload": p["prereg"]}, sha)
    from pilot_claims import plans
    if declared := plans(p):
        protocol["paired_claims"] = declared
    frozen = read(run / "freeze.json")
    freeze_hash = digest(encode(frozen))
    protocol_hash = digest(encode(protocol))
    require(frozen["proposal_sha256"] == sha and frozen["protocol_sha256"] == protocol_hash,
            "freeze binding mismatch")
    require(read(run / "launch.jsonl") == {"event": "launch", "freeze_sha256": freeze_hash,
            "protocol_sha256": protocol_hash}, "launch binding mismatch")
    if protocol["stage"] == "full":
        approved(run, "H2", freeze_hash)
    datasets, arms, seeds = (protocol[field] for field in ("datasets", "arms", "seeds"))
    expected = {(d, a, s) for d in datasets for a in arms for s in seeds}
    ids = {name: i for i, name in enumerate(datasets, 1)}
    methods = {name: i for i, name in enumerate(sorted(arms), 1)}
    rows = {}
    import io
    path = run / "results.jsonl"
    raw = path.read_bytes() if path.exists() else b""
    with io.BytesIO(raw) as source:
        while line := source.readline(65537):
            require(len(line) <= 65536, "oversized result row")
            row = json.loads(line)
            key = (row["dataset"], row["arm"], row["seed"])
            d, a, s = key
            require(key in expected and key not in rows, "unexpected or duplicate result row")
            checks = {"row_key": [d, a, s, 1], "attempt": 1,
                      "freeze_sha256": freeze_hash, "protocol_sha256": protocol_hash,
                      "runner_sha256": frozen["runner"], "method_sha256": frozen["method"][a],
                      "split_sha256": frozen["split"][d + ":" + str(s)],
                      "input_sha256": digest(encode(frozen["data"][d])), "budget_s": arms[a]["budget_s"]}
            if "plugins" in frozen:
                checks.update(plugin_sha256=digest(encode(frozen["plugins"][a])),
                              environment_sha256=digest(encode(frozen["environment"])))
            require(all(row[k] == v for k, v in checks.items()), "result binding mismatch")
            status, metric = row["status"], row["metric"]
            require(status in ("ok", "timeout", "error", "invalid", "memory", "nan"), "invalid status")
            require((type(metric) in (int, float) and math.isfinite(metric) and 0 <= metric <= 1)
                     if status == "ok" else metric is None, "invalid metric")
            for field in ("runner_sha256", "method_sha256", "split_sha256", "input_sha256"):
                require(re.fullmatch(r"sha256:[0-9a-f]{64}", row[field]), "invalid digest")
            rows[key] = {"dataset": ids[d], "arm": methods[a], "seed": s, "status": status,
                         "metric": metric, "budget_s": row["budget_s"],
                         **{k: checks[k] for k in ("method_sha256", "split_sha256", "input_sha256")}}
            if "plugins" in frozen:
                rows[key]["plugin_sha256"] = checks["plugin_sha256"]
    complete = bool(expected) and rows.keys() == expected
    receipt = run / "completion.json"
    observed = {"freeze_sha256": freeze_hash, "results_sha256": digest(raw), "rows": len(rows)}
    if receipt.exists():
        require(complete and read(receipt) == observed, "completion binding mismatch")
    if inspect:
        return {**observed, "complete": complete and (receipt.exists() or not frozen.get("sealed_results")),
                "failed": sum(row["status"] != "ok" for row in rows.values()),
                "expected_rows": len(expected)}
    require(complete and (receipt.exists() or not frozen.get("sealed_results")), "incomplete result matrix")
    payload = {"schema_version": 1, "protocol_sha256": protocol_hash, "freeze_sha256": freeze_hash,
               "metric": protocol["metric"], "rows": [rows[k] for k in sorted(rows)]}
    if "retry" in p:
        payload["retry"] = {k: p["retry"][k] for k in ("parent_launch_sha256", "parent_results_sha256", "reason")}
    if "plugins" in frozen:
        payload["environment_sha256"] = digest(encode(frozen["environment"]))
    payload["proposal_mode"] = p.get("mode", "exploratory")
    if payload["proposal_mode"] == "formal":
        from source_evidence import formal, ready
        from pathlib import Path
        cfg = p["scoop"]
        current = formal(Path(cfg["cards"]), cfg, p)
        require(current == read(run / "scoop.json"), "formal evidence replay mismatch")
        ready(current)
        payload["source_evidence"] = current["formal_evidence"]
        from pilot_claims import assess
        anchors = dict(zip(sorted(x["id"] for x in p["components"]), current["formal_evidence"]["anchors"]))
        if gates := assess(p, rows, ids, methods, anchors):
            payload["claim_gates"] = gates
    artifact = {"packet": payload, "packet_sha256": digest(encode(payload))}
    require(len(encode(artifact)) + 1 <= limit, "review packet exceeds byte limit")
    return artifact


def export(run, p, sha, limit):
    artifact = package(run, p, sha, limit)
    create(run / "review-package.json", artifact)
    print(artifact["packet_sha256"])
    return 0
