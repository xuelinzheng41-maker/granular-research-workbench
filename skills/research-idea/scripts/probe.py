#!/usr/bin/env python3
"""Check preliminary probe records; this does not certify scientific validity."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


class ProbeError(ValueError):
    pass


def read_record(folder, name):
    path = folder / name
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProbeError(f"{name}: {exc}") from exc
    if not isinstance(record, dict):
        raise ProbeError(f"{name}: expected a JSON object")
    return record


def require_fields(record, name, fields):
    for key in fields.split():
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ProbeError(f"{name}: fill in {key}")


def check_plan(folder, *, require_claim=False):
    name = "probe-plan.json"
    plan = read_record(folder, name)
    require_fields(plan, name, "source_kind source question rival setup control advance_if stop_if")
    if require_claim:
        require_fields(plan, name, "core_claim")
    if plan["source_kind"] not in ("literature", "anomaly", "transfer"):
        raise ProbeError(f"{name}: source_kind must be literature, anomaly or transfer")
    if plan.get("kind") not in ("empirical", "theory"):
        raise ProbeError(f"{name}: kind must be empirical or theory")
    budget = plan.get("budget_minutes")
    if type(budget) is not int or budget <= 0:
        raise ProbeError(f"{name}: budget_minutes must be a positive integer")
    if plan["advance_if"].strip() == plan["stop_if"].strip():
        raise ProbeError(f"{name}: advance_if and stop_if must differ")
    return plan


def read_result(folder):
    folder = Path(folder).resolve()
    plan = check_plan(folder)
    name = "probe-result.json"
    result = read_record(folder, name)
    require_fields(result, name, "observation limitations next_step")
    status = result.get("status")
    if status not in ("advance", "refuted", "inconclusive"):
        raise ProbeError(f"{name}: status must be advance, refuted or inconclusive")
    if "submitted_for_review" in result and type(result["submitted_for_review"]) is not bool:
        raise ProbeError(f"{name}: submitted_for_review must be a boolean")
    if status == "advance" and not submitted(result):
        raise ProbeError(f"{name}: an advance recommendation must be submitted for review")
    items = result.get("artifacts")
    if not isinstance(items, list) or not items:
        raise ProbeError(f"{name}: list at least one local evidence artifact")
    artifacts = {}
    for item in items:
        if not isinstance(item, str) or not item.strip() or Path(item).is_absolute():
            raise ProbeError(f"{name}: artifacts must be relative file paths")
        artifact = (folder / item).resolve()
        if (not artifact.is_relative_to(folder)
                or any(name in ("probe-plan.json", "probe-result.json", "probe-review.json",
                                "idea.md", "anchors.md", "review.md") for name in (Path(item).name, artifact.name))
                or not artifact.is_file() or artifact.stat().st_size == 0):
            raise ProbeError(f"{name}: missing, empty or invalid evidence artifact: {item}")
        artifacts[item] = artifact
    return folder, plan, result, artifacts


def review_input(plan, result, artifacts):
    require_fields(plan, "probe-plan.json", "core_claim")
    require_fields(result, "probe-result.json", "supported_claim")
    evidence_hashes = {}
    for name, file in artifacts.items():
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
        evidence_hashes[name] = digest.hexdigest()
    snapshot = json.dumps([plan, result, evidence_hashes], sort_keys=True, ensure_ascii=False)
    return dict(core_claim=plan["core_claim"], supported_claim=result["supported_claim"],
                artifacts=list(artifacts), review_input_sha256=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
                plan=plan, author_result=result)


def submitted(result):
    # Legacy records used advance to mean both recommendation and submission.
    return result.get("submitted_for_review", result["status"] == "advance")


def check_result(folder):
    folder, plan, result, artifacts = read_result(folder)
    if not submitted(result):
        return result["status"]
    packet = review_input(plan, result, artifacts)
    name = "probe-review.json"
    review = read_record(folder, name)
    require_fields(review, name, "reviewer verdict evidence_artifact reason review_input_sha256")
    if review["review_input_sha256"] != packet["review_input_sha256"]:
        raise ProbeError(f"{name}: review does not match the current plan, result and evidence; review again")
    if review["evidence_artifact"] not in artifacts:
        raise ProbeError(f"{name}: evidence_artifact must name an artifact listed in probe-result.json")
    if review["verdict"] == "direct":
        require_fields(review, name, "evidence_location rival_check")
    statuses = {"direct": "advance", "proxy_only": "inconclusive",
                "insufficient": "inconclusive", "contradicted": "refuted"}
    if review["verdict"] not in statuses:
        raise ProbeError(f"{name}: verdict must be direct, proxy_only, insufficient or contradicted")
    verdict = statuses[review["verdict"]]
    if verdict == "advance" and result["status"] != "advance":
        raise ProbeError(f"{name}: reviewer supports the claim but author did not; reconcile and review again")
    return verdict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "review-input", "check"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "plan":
            check_plan(args.folder, require_claim=True)
            print("plan: ready to run (structure only)")
            return 0
        if args.mode == "review-input":
            _, plan, result, artifacts = read_result(args.folder)
            if not submitted(result):
                raise ProbeError("review-input: result has not been submitted for review")
            print(json.dumps(review_input(plan, result, artifacts), ensure_ascii=False, indent=2))
            return 0
        status = check_result(args.folder)
    except (ProbeError, OSError, RuntimeError) as exc:
        print(f"probe: {exc}", file=sys.stderr)
        return 2
    print(f"probe: {status} (record checks only; scientific judgment belongs to the reviewer)")
    return 0 if status == "advance" else 3


if __name__ == "__main__":
    sys.exit(main())
