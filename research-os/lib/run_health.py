"""Run verification and explicit new-attempt registration."""
from pathlib import Path

from launch import CompileError, approved, compile_protocol, create, digest, encode, proposal, read, require
from review_packet import package
from review_decision import binding, decision


def passport_for(record, review):
    return {"schema_version": 1, "decision_sha256": digest(encode(record)),
            "decision": record, "reviewer": review["reviewer"]}


def health(run, p, sha):
    frozen_path = run / "freeze.json"
    launch = run / "launch.jsonl"
    artifacts = [run / name for name in ("completion.json", "review-package.json", "review.json",
                                         "decision.json", "passport.json")]
    h1 = run / "H1.json"
    h2 = run / "H2.json"
    if h1.exists():
        approved(run, "H1", sha)
    if not frozen_path.exists():
        require(not any(x.exists() for x in [launch, h2, run / "results.jsonl", *artifacts]),
                "downstream artifacts without freeze")
        return ("approved_not_frozen" if h1.exists() else "awaiting_H1", None)
    approved(run, "H1", sha)
    protocol = compile_protocol({"payload": p["prereg"]}, sha)
    from pilot_claims import plans
    if declared := plans(p):
        protocol["paired_claims"] = declared
    frozen = read(frozen_path)
    require(frozen["proposal_sha256"] == sha and frozen["protocol_sha256"] == digest(encode(protocol)),
            "freeze binding mismatch")
    if h2.exists():
        require(protocol["stage"] == "full", "unexpected H2")
        approved(run, "H2", digest(encode(frozen)))
    if not launch.exists():
        require(not any(x.exists() for x in [run / "results.jsonl", *artifacts]), "results without launch")
        return ("awaiting_H2" if protocol["stage"] == "full" and not h2.exists() else "frozen_not_started", None)
    result = package(run, p, sha, 8_000_000, inspect=True)
    if not result["complete"]:
        require(not any(x.exists() for x in artifacts), "downstream artifacts on incomplete run")
        return "started_incomplete", result
    packet, review_path, decision_path, passport = artifacts[1:]
    if packet.exists():
        require(read(packet) == package(run, p, sha, 8_000_000), "review package mismatch")
    if any(x.exists() for x in (review_path, decision_path, passport)):
        review = read(review_path)
        record = decision(review, binding(run, p, sha), read(packet)["packet"].get("claim_gates", {}))
        if decision_path.exists() or passport.exists():
            require(read(decision_path) == record, "decision mismatch")
        if passport.exists():
            require(read(passport) == passport_for(record, review), "passport mismatch")
            return "archived", result
    return ("complete_with_failures" if result["failed"] else "complete", result)


def report(run, verify):
    try:
        state, result = health(run, *proposal(run))
        print(encode({"state": state, "results": result}).decode())
        return 3 if verify and state == "started_incomplete" else 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError, CompileError) as exc:
        print(encode({"state": "corrupt", "error": str(exc)}).decode())
        return 2


def parent_link(parent, reason):
    p, sha = proposal(parent)
    state, result = health(parent, p, sha)
    eligible = result and ((reason == "failed" and result["complete"] and result["failed"])
                           or (reason == "interrupted" and state == "started_incomplete"))
    require(eligible, "parent does not have the specified failure or interruption evidence")
    require(p["prereg"]["stage"] == "pilot", "only pilot retries are supported")
    return p, {"parent": str(parent), "reason": reason, "parent_proposal_sha256": sha,
               "parent_launch_sha256": digest(encode(read(parent / "launch.jsonl"))),
               "parent_results_sha256": result["results_sha256"]}


def retry(parent, child, reason):
    p, link = parent_link(parent, reason)
    child.mkdir(parents=True, exist_ok=False)
    create(child / "proposal.json", {**p, "retry": link})
    print(proposal(child)[1])
    return 0


def check_retry(child, p, frozen):
    link = p["retry"]
    parent = Path(link["parent"]).resolve()
    require(parent != child, "retry cannot reference itself")
    parent_p, current = parent_link(parent, link["reason"])
    require(link == current and p == {**parent_p, "retry": current}, "retry lineage or design changed")
    previous = read(parent / "freeze.json")
    keys = set(frozen) - {"proposal_sha256", "protocol_sha256", "sealed_results"}
    require(all(frozen[k] == previous.get(k) for k in keys), "retry execution inputs changed; use a new experiment")
