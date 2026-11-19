#!/usr/bin/env python3
"""Check preliminary probe records; this does not certify scientific validity."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

from shortlist import compare


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


SELECTION = "candidate-selection.json"
PLAN_LOCK = "probe-plan-lock.json"
EVIDENCE_LOCK = "probe-evidence-lock.json"


def record_digest(record):
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_new(folder, name, record):
    with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def candidate_fields(selection):
    require_fields(selection, SELECTION, "candidate_id attempt_id")
    report = compare(selection.get("brief"))
    key = selection["candidate_id"]
    if key not in report["eligible_ids"]:
        raise ProbeError(f"candidate {key!r} is unknown or not eligible for a probe")
    row = next(item for item in report["candidates"] if item["id"] == key)
    return dict(candidate_id=key, selection_sha256=record_digest(selection),
                core_claim=row["claim"], budget_minutes=row["probe_minutes"],
                advance_if=row["advance_if"], stop_if=row["stop_if"],
                source_kind=row["source_kind"], source=row["source"])


def select_candidate(brief, key):
    selection = dict(candidate_id=key, attempt_id=uuid4().hex, brief=brief)
    return selection, candidate_fields(selection)


def is_linked(folder, plan):
    return (any(key in plan for key in ("candidate_id", "selection_sha256"))
            or any((folder / name).exists() or (folder / name).is_symlink()
                   for name in (SELECTION, PLAN_LOCK, EVIDENCE_LOCK)))


def check_link(folder, plan):
    if not is_linked(folder, plan):
        return False
    fields = candidate_fields(read_record(folder, SELECTION))
    for field, value in fields.items():
        if plan.get(field) != value:
            raise ProbeError(f"{field}: differs from selected candidate; create a new draft to revise the claim or contract")
    entry = plan.get("implementation")
    if not isinstance(entry, dict):
        raise ProbeError("implementation: declare a path and a reproduction command or proof checking steps")
    require_fields(entry, "implementation", "path reproduce")
    if local_artifact(folder.resolve(), entry["path"]) is None:
        raise ProbeError("implementation.path must be a local, non-record file path")
    return True


def freeze_plan(folder):
    plan = check_plan(folder, require_claim=True)
    if not is_linked(folder, plan):
        raise ProbeError("freeze requires a draft linked to a shortlisted candidate")
    lock = dict(plan_sha256=record_digest(plan))
    save_new(folder, PLAN_LOCK, lock)
    return lock


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
    check_link(folder, plan)
    return plan


def local_artifact(folder, item):
    if not isinstance(item, str) or not item.strip() or Path(item).anchor:
        return None
    artifact = (folder / item).resolve()
    reserved = {name.casefold() for name in (
        "probe-plan.json", "probe-result.json", "probe-review.json",
        "idea.md", "anchors.md", "review.md", SELECTION, PLAN_LOCK, EVIDENCE_LOCK)}
    if not artifact.is_relative_to(folder) or ({Path(item).name.casefold(), artifact.name.casefold()} & reserved):
        return None
    return artifact


def read_result(folder, *, sealing=False):
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
        artifact = local_artifact(folder, item)
        if artifact is None or not artifact.is_file() or artifact.stat().st_size == 0:
            raise ProbeError(f"{name}: missing, empty or invalid evidence artifact: {item}")
        artifacts[item] = artifact
    if is_linked(folder, plan):
        digest = record_digest(plan)
        if read_record(folder, PLAN_LOCK).get("plan_sha256") != digest:
            raise ProbeError("plan differs from the frozen plan; create a new draft")
        if result.get("frozen_plan_sha256") != digest:
            raise ProbeError("result does not identify this frozen plan; do not reuse results from another run")
        entry = plan["implementation"]["path"]
        if entry not in artifacts or len(set(artifacts.values())) < 2:
            raise ProbeError("artifacts must include the declared implementation and a separate evidence file")
        if not sealing and read_record(folder, EVIDENCE_LOCK) != evidence_lock(plan, result, artifacts):
            raise ProbeError("sealed result or artifact changed; create a new draft")
    return folder, plan, result, artifacts


def artifact_digests(artifacts):
    evidence_hashes = {}
    for name, file in artifacts.items():
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
        evidence_hashes[name] = digest.hexdigest()
    return evidence_hashes


def evidence_lock(plan, result, artifacts):
    return dict(plan_sha256=record_digest(plan), result_sha256=record_digest(result), files=artifact_digests(artifacts))


def seal_run(folder):
    folder, plan, result, artifacts = read_result(folder, sealing=True)
    if not is_linked(folder, plan):
        raise ProbeError("seal requires a draft linked to a shortlisted candidate")
    require_fields(result, "probe-result.json", "supported_claim")
    lock = evidence_lock(plan, result, artifacts)
    save_new(folder, EVIDENCE_LOCK, lock)
    return lock


def review_snapshot(plan, result, artifacts):
    require_fields(plan, "probe-plan.json", "core_claim")
    require_fields(result, "probe-result.json", "supported_claim")
    digests = artifact_digests(artifacts)
    snapshot = json.dumps([plan, result, digests], sort_keys=True, ensure_ascii=False)
    return digests, hashlib.sha256(snapshot.encode("utf-8")).hexdigest()


def review_input(plan, result, artifacts):
    _, digest = review_snapshot(plan, result, artifacts)
    return dict(core_claim=plan["core_claim"], supported_claim=result["supported_claim"],
                artifacts=list(artifacts), review_input_sha256=digest,
                plan=plan, author_result=result)


PLAN_VIEW = ("source_kind", "source", "question", "kind", "setup", "control",
             "rival", "advance_if", "stop_if", "budget_minutes", "implementation")
WITHHELD = ("author status", "author's strongest supporting statement", "author observation",
            "author-stated limitations", "author next steps")
REVIEWER_TYPES = ("human", "ai_agent", "unspecified")
EXPOSURES = ("none", "seen", "unspecified")


def review_brief(plan, result, artifacts):
    """First-round packet: contract, provenance-free evidence references and review summary only."""
    digests, digest = review_snapshot(plan, result, artifacts)
    return dict(core_claim=plan["core_claim"],
                plan={key: plan[key] for key in PLAN_VIEW if key in plan},
                artifacts=list(artifacts), artifact_sha256=digests,
                review_input_sha256=digest,
                review_summary=dict(
                    view="first_round",
                    withholds=list(WITHHELD),
                    full_view="probe.py review-input <folder> --full",
                    record_fields=dict(
                        required=["reviewer", "verdict", "evidence_artifact", "reason", "review_input_sha256"],
                        direct_requires=["evidence_location", "rival_check"],
                        verdicts=["direct", "proxy_only", "insufficient", "contradicted"],
                        provenance=dict(reviewer_type=list(REVIEWER_TYPES),
                                        author_result_exposure=list(EXPOSURES))),
                    note=("Declarations only; identity, timing and independence are not verified. "
                          "A missing provenance field is reported as unspecified, never as a blind review.")))


def submitted(result):
    # Legacy records used advance to mean both recommendation and submission.
    return result.get("submitted_for_review", result["status"] == "advance")


def review_provenance(review, name="probe-review.json"):
    """Return self-declared reviewer provenance; blank or absent fields stay unspecified."""
    values = {}
    for key, allowed in (("reviewer_type", REVIEWER_TYPES),
                         ("author_result_exposure", EXPOSURES)):
        value = review.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            values[key] = "unspecified"
        elif not isinstance(value, str) or value not in allowed:
            raise ProbeError(f"{name}: {key} must be one of {', '.join(allowed)}")
        else:
            values[key] = value
    return values


def check_record(folder):
    """Return the recorded outcome and, when a review was applied, its declared provenance."""
    folder, plan, result, artifacts = read_result(folder)
    if not submitted(result):
        return result["status"], None
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
    provenance = review_provenance(review, name)
    verdict = statuses[review["verdict"]]
    if verdict == "advance" and result["status"] != "advance":
        raise ProbeError(f"{name}: reviewer supports the claim but author did not; reconcile and review again")
    return verdict, provenance


def check_result(folder):
    return check_record(folder)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "freeze", "seal", "review-input", "check"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("--full", action="store_true",
                        help="with review-input: also show the author's result (explicit request)")
    args = parser.parse_args()
    if args.full and args.mode != "review-input":
        print("probe: --full only applies to review-input", file=sys.stderr)
        return 2
    try:
        if args.mode == "plan":
            check_plan(args.folder, require_claim=True)
            print("plan: ready to run (structure only)")
            return 0
        if args.mode in ("freeze", "seal"):
            lock = freeze_plan(args.folder) if args.mode == "freeze" else seal_run(args.folder)
            print(json.dumps(lock, ensure_ascii=False, indent=2))
            return 0
        if args.mode == "review-input":
            _, plan, result, artifacts = read_result(args.folder)
            if not submitted(result):
                raise ProbeError("review-input: result has not been submitted for review")
            packet = review_input(plan, result, artifacts) if args.full else review_brief(plan, result, artifacts)
            print(json.dumps(packet, ensure_ascii=False, indent=2))
            return 0
        status, provenance = check_record(args.folder)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"probe: {exc}", file=sys.stderr)
        return 2
    print(f"probe: {status} (record checks only; scientific judgment belongs to the reviewer)")
    if provenance is not None:
        print("probe: review record (self-declared; identity and timing are not verified): "
              f"reviewer_type={provenance['reviewer_type']}, "
              f"author_result_exposure={provenance['author_result_exposure']}")
        if "unspecified" in provenance.values():
            print("probe: unspecified provenance is not treated as a blind review")
    return 0 if status == "advance" else 3


if __name__ == "__main__":
    sys.exit(main())
