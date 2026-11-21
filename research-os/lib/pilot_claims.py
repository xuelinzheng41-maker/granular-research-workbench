"""One preregistered pilot statistic: mean paired ACC difference."""
import math
import re


def plans(p):
    if p.get("mode") != "formal" or p["prereg"]["stage"] != "pilot":
        return []
    prereg = p["prereg"]
    valid = []
    seen = set()
    for c in prereg.get("paired_claims", []):
        if not isinstance(c, dict) or set(c) != {"id", "component", "datasets", "seeds", "candidate", "control", "support_min", "refute_max"}:
            continue
        ident = c["id"]
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", ident) or ident in seen:
            raise ValueError("invalid or duplicate claim id")
        seen.add(ident)
        component = c["component"]
        if component not in {a["id"] for a in p["components"]}:
            continue
        if c["candidate"] == c["control"] or any(c[k] not in prereg["arms"] for k in ("candidate", "control")):
            continue
        if any(type(c[k]) is not list or not c[k] or len(set(c[k])) != len(c[k]) or not set(c[k]) <= set(prereg[k]) for k in ("datasets", "seeds")):
            continue
        lo, hi = c["refute_max"], c["support_min"]
        if not all(type(x) in (int, float) and math.isfinite(x) for x in (lo, hi)) or not -1 <= lo < hi <= 1:
            continue
        valid.append(c)
    return valid


def assess(p, rows, aliases, methods, anchors):
    out = {}
    for c in plans(p):
        a, b = c["candidate"], c["control"]
        pairs = []
        for d in c["datasets"]:
            for s in c["seeds"]:
                left, right = rows.get((d, a, s)), rows.get((d, b, s))
                if not left or not right or left["status"] != "ok" or right["status"] != "ok" or left["split_sha256"] != right["split_sha256"]:
                    continue
                pairs.append({"dataset": aliases[d], "seed": s, "split_sha256": left["split_sha256"],
                              "candidate_acc": left["metric"], "control_acc": right["metric"]})
        full = len(pairs) == len(c["datasets"]) * len(c["seeds"])
        mean = math.fsum(pair["candidate_acc"] - pair["control_acc"] for pair in pairs) / len(pairs) if full else None
        out[c["id"]] = {"G1": anchors[c["component"]], "G2": full, "G3": "awaiting_claim_review",
                        "G4": full, "G5": full and mean <= c["refute_max"],
                        "meets_support": full and mean >= c["support_min"], "paired_mean_acc_delta": mean,
                        "support_min": c["support_min"], "refute_max": c["refute_max"],
                        "datasets": [aliases[d] for d in c["datasets"]], "seeds": c["seeds"],
                        "candidate": methods[a], "control": methods[b], "pairs": pairs,
                        "scope_limit": "pilot only; not Full or general validity"}
    return out
