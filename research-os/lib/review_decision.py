"""Explicit local review attestations and conservative pilot decisions."""
from launch import create, digest, encode, read, require
from review_packet import package


def binding(run, p, sha):
    path = run / "results.jsonl"
    before = digest(path.read_bytes())
    packet = package(run, p, sha, 8_000_000)
    require(digest(path.read_bytes()) == before, "results changed during validation")
    require(read(run / "review-package.json") == packet, "review package no longer matches results")
    return {"run": run.name, "run_sha256": digest(encode(str(run))),
            "packet_sha256": packet["packet_sha256"], "results_sha256": before,
            "protocol_sha256": packet["packet"]["protocol_sha256"]}


def check_review(review, expected, gates=None):
    gates = gates or {}
    require(type(review) is dict and set(review) - {"accepted_claims"} == {"binding", "reviewer", "verdict", "rationale"},
            "invalid review shape; scientific promotions are not accepted")
    require(review["binding"] == expected, "review binding mismatch")
    reviewer = review["reviewer"]
    require(type(reviewer) is dict and reviewer.get("independent") is True and
            type(reviewer.get("id")) is str and reviewer["id"].strip(), "independent review declaration required")
    base = {"id", "type", "independent"}
    if reviewer.get("type") == "human":
        require(set(reviewer) == base, "invalid human reviewer")
    else:
        fields = {"model_route", "team_task", "team_attempt"}
        require(reviewer.get("type") == "independent_model" and set(reviewer) == base | fields and
                all(type(reviewer[k]) is str and reviewer[k].strip() for k in fields), "invalid model provenance")
    accepted = review.get("accepted_claims", [])
    require(type(accepted) is list and all(type(k) is str and k in gates for k in accepted)
            and len(set(accepted)) == len(accepted), "unknown or duplicate accepted claim")
    require(review["verdict"] in ("pass", "needs_revision", "reject") and
            type(review["rationale"]) is str and review["rationale"].strip(), "missing review verdict or rationale")


def decision(review, expected, gates=None):
    gates = gates or {}
    check_review(review, expected, gates)
    assessments = {}
    for ident, gate in gates.items():
        accepted = review["verdict"] == "pass" and ident in review.get("accepted_claims", [])
        status = "refuted" if gate["G5"] else "supported" if gate["meets_support"] and accepted else "unknown"
        assessments[ident] = {"G3": accepted and gate["meets_support"], "status": status}
    return {"binding": expected, "review_sha256": digest(encode(review)),
            "decision": "exploratory" if review["verdict"] == "pass" else "do_not_advance",
            "scientific_claims": assessments or "unknown", "paper_ready": False}


def dispatch(args, run, p, sha):
    expected = binding(run, p, sha)
    gates = read(run / "review-package.json")["packet"].get("claim_gates", {})
    if args.command == "review-target":
        print(encode(expected).decode())
        return 0
    if args.command == "review":
        artifact = read(args.review_input)
        check_review(artifact, expected, gates)
        path = run / "review.json"
    else:
        review = read(run / "review.json")
        artifact = decision(review, expected, gates)
        path = run / "decision.json"
        if args.command == "passport":
            require(read(path) == artifact, "decision record mismatch")
            artifact = {"schema_version": 1, "decision_sha256": digest(encode(artifact)),
                        "decision": artifact, "reviewer": review["reviewer"]}
            path = run / "passport.json"
    create(path, artifact)
    print(digest(encode(artifact)))
    return 0
