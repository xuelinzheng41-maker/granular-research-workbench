"""Strict source evidence for formal candidates; no novelty inference."""
import hashlib
import re
from pathlib import Path

from card_parser import read_card
from scoop import AXES, collect


def sha(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def formal(directory, config, proposal):
    report = collect(directory, config["queries"])
    components = proposal["components"]
    need(type(components) is list and components, "formal mode needs components")
    anchors = {}
    for item in components:
        ident, card, line = (item[k] for k in ("id", "card", "body_line"))
        need(re.fullmatch(r"[A-Za-z0-9_-]+", ident) and ident not in anchors, "invalid component ID")
        need(card in report["inventory"], "unknown component card")
        path = directory / card
        need(path.resolve().parent == directory.resolve(), "component card escapes corpus")
        meta, body, _ = read_card(path)
        need(meta.get("card_status") == "handmade", "component requires handmade source card")
        lines = body.splitlines()
        need(type(line) is int and 1 <= line <= len(lines) and lines[line-1].strip(), "component locator not found")
        span = sha(lines[line-1].encode())
        source = sha(path.read_bytes())
        need(span == item["span_sha256"] and source == report["inventory"][card], "component source drift or span mismatch")
        anchors[ident] = {"body_line": line, "span_sha256": span, "card_sha256": source}
    judgments = config["judgments"]
    need(set(judgments) == set(AXES), "four axes require explicit judgments lists")
    axes = {}
    codes = {"none": {"different_scope", "different_method", "irrelevant_match"},
             "partial": {"shared_element"}, "blocking": {"same_claim"}}
    for axis in AXES:
        result = report["axes"][axis]
        candidates = {(hit["card"], hit["body_line"]): hit for hit in result["hits"]}
        assessed = {}
        for entry in judgments[axis]:
            key = (entry["card"], entry["body_line"])
            need(key in candidates and key not in assessed, "judgment must cite one retrieved candidate")
            status, reason = entry["overlap"], entry["reason"]
            need(status in codes and reason in codes[status], "invalid overlap reason code")
            span = sha(candidates[key]["span"].encode())
            need(entry["span_sha256"] == span, "judgment span mismatch")
            assessed[key] = {"overlap": status, "reason": reason, "span_sha256": span,
                             "card_sha256": report["inventory"][key[0]], "body_line": key[1]}
        axes[axis] = {"status": result["status"], "query_count": len(result["terms"]),
                      "excluded_count": len(result["excluded"]), "unassessed_count": len(candidates.keys() - assessed.keys()),
                      "judgments": [assessed[k] for k in sorted(assessed)]}
    report["formal_evidence"] = {"anchors": [anchors[k] for k in sorted(anchors)], "axes": axes,
                                 "limits": report["limits"], "failed_cards": len(report["failures"])}
    return report


def ready(report):
    for axis in report["formal_evidence"]["axes"].values():
        need(axis["status"] in ("hits", "zero_hits") and not axis["unassessed_count"], "incomplete formal scoop evidence")
        need(not any(j["overlap"] == "blocking" for j in axis["judgments"]), "blocking overlap")
