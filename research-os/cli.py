#!/usr/bin/env python
"""
Research OS v2 - Command Line Interface

Entry point for all research-os commands:
- status: Show run status and stage health
- verify: Verify record integrity and dependency chain
- (future: stage, compile, run, gate, claims, review, decide, passport, import-v1)
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from records import RecordEnvelope, verify_dependency_chain, verify_input_hash
from state import (
    compute_all_stage_statuses,
    format_status_line,
    check_stage_transition_allowed,
    DerivedStatus,
    STAGE_PREREQUISITES
)
from datasets import (
    DatasetRegistry,
    DatasetStatus,
    load_dataset_with_label_info,
    verify_loaded_dataset,
    get_label_distribution
)


def list_stages() -> List[str]:
    """Return ordered list of stage names."""
    return list(STAGE_PREREQUISITES.keys())


def load_run_stages(run_dir: Path) -> Dict[str, Optional[RecordEnvelope]]:
    """
    Load all stage records from a run directory.
    
    Returns:
        Dict mapping stage name -> RecordEnvelope (or None if missing)
    """
    stages = {}
    for stage in list_stages():
        record_path = run_dir / stage / "record.json"
        if record_path.exists():
            try:
                stages[stage] = RecordEnvelope.load(record_path)
            except Exception as e:
                print(f"Warning: Failed to load {stage}: {e}", file=sys.stderr)
                stages[stage] = None
        else:
            stages[stage] = None
    
    return stages


def compute_stage_status(
    stage: str,
    record: Optional[RecordEnvelope],
    upstream_records: Dict[str, Optional[RecordEnvelope]],
    upstream_statuses: Dict[str, StageStatus],
    run_dir: Path
) -> StageStatus:
    """
    Compute derived status for a stage.
    
    Status hierarchy:
    1. missing: No record.json exists
    2. stale_input: Input hashes don't match OR payload corrupted
    3. stale_dependency: Upstream payload_sha256 changed OR upstream is stale
    4. ok: All checks pass
    """
    if record is None:
        return StageStatus(stage, "missing")
    
    # Verify payload_sha256
    if not record.verify_payload_sha256():
        return StageStatus(
            stage, "stale_input",
            record, "payload_sha256 mismatch (corrupted or manually edited)"
        )
    
    # Check if any upstream is stale (propagate staleness)
    for dep_stage in record.depends_on.keys():
        if dep_stage in upstream_statuses:
            upstream_status = upstream_statuses[dep_stage]
            if upstream_status.status in ["stale_input", "stale_dependency"]:
                return StageStatus(
                    stage, "stale_dependency",
                    record, f"upstream {dep_stage} is {upstream_status.status}"
                )
    
    # Verify dependencies
    stale_deps = verify_dependency_chain(record, {
        k: v for k, v in upstream_records.items() if v is not None
    })
    
    if any(stale_deps.values()):
        stale_list = [k for k, v in stale_deps.items() if v]
        return StageStatus(
            stage, "stale_dependency",
            record, f"upstream changed: {', '.join(stale_list)}"
        )
    
    # Check inputs (simplified - just verify they exist for now)
    # Full implementation would check file hashes
    for input_name, input_hash in record.inputs.items():
        # For M0, we just check if inputs dict is present
        # Full implementation in M2+ will verify actual file hashes
        pass
    
    return StageStatus(stage, "ok", record)


def cmd_status(run_dir: Path) -> int:
    """
    Show status of all stages in a run.
    
    Returns:
        Exit code (0 = success)
    """
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}", file=sys.stderr)
        return 2
    
    print(f"Run: {run_dir.name}")
    print()
    
    # Load all stage records
    stage_records = load_run_stages(run_dir)
    
    # Compute statuses using state machine
    statuses = compute_all_stage_statuses(stage_records, run_dir)
    
    # Print status summary
    for stage in list_stages():
        status, details = statuses[stage]
        print(format_status_line(stage, status, details))
    
    return 0


def cmd_verify(run_dir: Path, verbose: bool = False) -> int:
    """
    Verify integrity of all records in a run.
    
    Checks:
    1. Each record.json has valid payload_sha256
    2. Dependencies point to correct upstream hashes
    3. Approvals match current hashes
    4. No stage skipping
    
    Outputs 10-line status summary as per M1 acceptance criterion (d).
    
    Returns:
        Exit code:
        - 0 = all checks pass
        - 2 = integrity check failed
        - 3 = stale_input detected
    """
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}", file=sys.stderr)
        return 2
    
    print(f"Verifying run: {run_dir.name}")
    print()
    
    # Load all stage records
    stage_records = load_run_stages(run_dir)
    
    # Compute statuses using state machine
    statuses = compute_all_stage_statuses(stage_records, run_dir)
    
    # Output 10-line status summary
    all_ok = True
    has_stale = False
    
    for stage in list_stages():
        status, details = statuses[stage]
        print(format_status_line(stage, status, details))
        
        if status == DerivedStatus.STALE_INPUT:
            all_ok = False
        elif status in [DerivedStatus.STALE_DEPENDENCY, DerivedStatus.AWAITING_CONFIRMATION]:
            has_stale = True
    
    print()
    
    if not all_ok:
        print("Verification FAILED: integrity errors detected", file=sys.stderr)
        return 2
    
    if has_stale:
        print("Verification WARNING: stale dependencies or missing approvals", file=sys.stderr)
        return 3
    
    print("Verification PASSED: all records valid")
    return 0


def cmd_import_v1(ideas_dir: Path, output_dir: Path) -> int:
    """
    Import v1 ideas/<id>/ directories as legacy records.

    Per DESIGN.md §11:
    - Mapped to 08-evidence / 09-review records
    - Marked legacy: true
    - CANNOT receive H1/H2 approval
    - Cannot produce decision=viable

    Returns:
        Exit code: 0=success, 2=error
    """
    if not ideas_dir.exists():
        print(f"Error: ideas directory not found: {ideas_dir}", file=sys.stderr)
        print("No v1 ideas to import.")
        return 0  # Empty directory is not an error

    imported = 0
    skipped = 0

    for idea_path in sorted(ideas_dir.iterdir()):
        if not idea_path.is_dir():
            continue

        idea_id = idea_path.name
        print(f"Importing: {idea_id}")

        # Collect v1 record files
        record_files = list(idea_path.glob("*.json")) + list(idea_path.glob("*.md"))
        if not record_files:
            print(f"  Skipping (no files found)")
            skipped += 1
            continue

        # Create legacy record envelope
        import hashlib

        legacy_payload = {
            "legacy": True,
            "v1_idea_id": idea_id,
            "v1_files": [str(f.name) for f in record_files],
            "note": (
                "Imported from v1 ideas/ directory. "
                "Cannot receive H1/H2 approval. "
                "Cannot produce decision=viable."
            ),
            "h1_blocked": True,
            "h2_blocked": True,
        }

        output_run_dir = output_dir / idea_id
        output_run_dir.mkdir(parents=True, exist_ok=True)

        legacy_record = RecordEnvelope(
            stage="08-evidence",
            kind="legacy_import",
            record_id=f"legacy-{idea_id}@1",
            attempt=1,
            payload=legacy_payload,
            by="agent",
        )
        legacy_record.save(output_run_dir / "legacy_record.json")

        print(f"  Imported as legacy: {output_run_dir / 'legacy_record.json'}")
        print(f"  legacy:true, h1_blocked:true, h2_blocked:true")
        imported += 1

    print(f"\nImport complete: {imported} imported, {skipped} skipped")
    if imported == 0 and skipped == 0:
        print("(ideas/ directory is empty)")
    return 0


def cmd_datasets_check(registry_path: Path) -> int:
    """
    Check all datasets in registry.

    Two separate axes are reported per dataset:
    - Integrity: verified | unverified:hash_not_declared | mismatch | missing |
      load_error | not_checked. A computed hash is NOT a verified hash.
    - Classification readiness: ready | not_ready:<reason> | blocked:<reason>.
    An eligible dataset needs real multiclass labels and no verification errors.
    A missing hash declaration alone does not block classification readiness.

    Exit codes (unchanged):
        - 0 = no missing file / load error / mismatch / needs_data
        - 2 = missing file, load error, mismatch, needs_data, or no registry
    """
    if not registry_path.exists():
        print(f"Error: Registry not found: {registry_path}", file=sys.stderr)
        return 2

    print(f"Checking datasets from: {registry_path}")
    print()

    registry = DatasetRegistry(registry_path)
    root = registry.get_root()

    all_ok = True
    declared_ready = []
    loaded = []
    integ_verified, integ_unverified, integ_failed = [], [], []
    cls_ready, cls_not_ready, needs_loader_datasets = [], [], []

    for dataset_entry in registry.registry["datasets"]:
        dataset_id = dataset_entry["id"]
        status = dataset_entry["status"]

        print(f"Dataset: {dataset_id}")
        print(f"  Declared status: {status} (registry declaration, not a check result)")
        if status in [DatasetStatus.READY, DatasetStatus.READY_WITH_SCIPY]:
            declared_ready.append(dataset_id)

        if status == DatasetStatus.NEEDS_LOADER:
            loader = dataset_entry.get("loader", "unknown")
            missing = "MATLAB v7.3/h5py support" if loader == "mat_v73" else f"loader '{loader}'"
            print(f"  ⚠ Requires loader that is not available: {missing}")
            if dataset_entry.get("notes"):
                print(f"  Notes: {dataset_entry['notes']}")
            print("  Integrity: not_checked")
            print(f"  Classification: blocked:needs_loader ({missing})")
            needs_loader_datasets.append(f"{dataset_id}: {missing}")
            cls_not_ready.append(f"{dataset_id}: blocked:needs_loader")
            print()
            continue

        if status == DatasetStatus.NEEDS_DATA:
            print(f"  ✗ Data files missing")
            print("  Integrity: not_checked")
            print("  Classification: blocked:needs_data")
            cls_not_ready.append(f"{dataset_id}: blocked:needs_data")
            all_ok = False
            print()
            continue

        integrity = None
        classification = None
        try:
            X, y, sha256_dict, has_labels = load_dataset_with_label_info(dataset_entry, root)

            rows, features = X.shape
            clustering_only = dataset_entry.get("usage") == "clustering"
            label_dist = get_label_distribution(y) if has_labels else {}
            loaded.append(dataset_id)

            print(f"  Rows: {rows}")
            print(f"  Features: {features}")
            if has_labels:
                print(f"  Labels: {len(label_dist)} classes")
                print(f"  Distribution: {dict(sorted(label_dist.items()))}")
            else:
                print("  Labels: no ground-truth source")

            for key, hash_value in sha256_dict.items():
                print(f"  SHA256 ({key}): {hash_value[:32]}... (computed, not verified)")

            success, error = verify_loaded_dataset(dataset_entry, X, sha256_dict)
            if not success:
                print(f"  ✗ Verification failed: {error}")
                all_ok = False
                integrity = "mismatch" if ("mismatch" in (error or "")) else "load_error"
                classification = "not_ready:load_failed"
            else:
                declared_hashes = dataset_entry.get("sha256") or {}
                undeclared = [k for k in sha256_dict if k not in declared_hashes]
                if undeclared:
                    integrity = "unverified:hash_not_declared"
                    print(f"  ~ Loadable; hash not declared for: {', '.join(undeclared)}")
                else:
                    integrity = "verified"
                    print(f"  ✓ Hashes match declared values")

                if clustering_only:
                    classification = "not_ready:clustering_only"
                elif rows == 0:
                    classification = "not_ready:empty"
                elif not has_labels:
                    classification = "not_ready:no_labels"
                elif len(label_dist) < 2:
                    classification = "not_ready:single_class"
                else:
                    classification = "ready"

        except FileNotFoundError as e:
            print(f"  ✗ File not found: {e}")
            all_ok = False
            integrity = "missing"
            classification = "not_ready:load_failed"
        except Exception as e:
            print(f"  ✗ Load error: {e}")
            all_ok = False
            integrity = "load_error"
            classification = "not_ready:load_failed"

        print(f"  Integrity: {integrity}")
        print(f"  Classification: {classification}")
        if integrity == "verified":
            integ_verified.append(dataset_id)
        elif integrity.startswith("unverified"):
            integ_unverified.append(dataset_id)
        else:
            integ_failed.append(f"{dataset_id}:{integrity}")
        if classification == "ready":
            cls_ready.append(dataset_id)
        else:
            cls_not_ready.append(f"{dataset_id}: {classification}")

        print()

    total = len(registry.registry["datasets"])

    def _j(items):
        return ", ".join(items) if items else "-"

    print("=" * 60)
    print(f"Total datasets: {total}")
    print(f"Declared ready (registry claim): {len(declared_ready)}")
    print(f"Loaded: {len(loaded)}")
    print(f"Integrity verified: {len(integ_verified)}")
    print(f"Integrity unverified (hash not declared): {len(integ_unverified)} ({_j(integ_unverified)})")
    print(f"Integrity failed: {len(integ_failed)} ({_j(integ_failed)})")
    print(f"Classification ready: {len(cls_ready)} ({_j(cls_ready)})")
    print(f"Not classification-ready: {len(cls_not_ready)} ({_j(cls_not_ready)})")
    print(f"Needs loader: {len(needs_loader_datasets)} ({_j(needs_loader_datasets)})")
    print()

    if not all_ok:
        print("Check FAILED: Some datasets have errors", file=sys.stderr)
        return 2

    if integ_unverified:
        print("Check finished: no load errors; some datasets are unverified (hash not declared). "
              "Only datasets listed under 'Classification ready' are usable as classification benchmarks.")
    else:
        print("Check finished: no load errors. "
              "Only datasets listed under 'Classification ready' are usable as classification benchmarks.")
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Research OS v2 - Command Line Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show run status and stage health"
    )
    status_parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to run directory (e.g., runs/2026-11-22-example)"
    )
    
    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify record integrity and dependency chain"
    )
    verify_parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to run directory"
    )
    verify_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed verification output"
    )
    
    # datasets command
    datasets_parser = subparsers.add_parser(
        "datasets",
        help="Dataset registry operations"
    )
    datasets_subparsers = datasets_parser.add_subparsers(dest="datasets_command")
    
    # datasets check
    check_parser = datasets_subparsers.add_parser(
        "check",
        help="Check all datasets in registry"
    )
    check_parser.add_argument(
        "--registry",
        type=Path,
        default=Path("research-os/datasets.json"),
        help="Path to dataset registry (default: research-os/datasets.json)"
    )
    
    paper_parser = datasets_subparsers.add_parser(
        "for-paper", help="Compare a paper's datasets with a local registry"
    )
    paper_parser.add_argument("paper", type=Path, help="UTF-8 Markdown card/paper or plain-text export")
    paper_parser.add_argument("--registry", type=Path, required=True, help="Path to the local registry")
    paper_parser.add_argument("--task", choices=("classification", "clustering"), default="classification")
    paper_parser.add_argument("--dataset", action="append", default=[], help="Confirmed required name; repeat as needed")
    paper_parser.add_argument("--json", action="store_true", help="Emit a machine-readable report")

    # import-v1 command
    import_v1_parser = subparsers.add_parser(
        "import-v1",
        help="Import v1 ideas/<id>/ directories as legacy records"
    )
    import_v1_parser.add_argument(
        "ideas_dir",
        type=Path,
        nargs="?",
        default=Path("ideas"),
        help="Path to v1 ideas directory (default: ideas/)"
    )
    import_v1_parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/_legacy"),
        help="Output directory for imported legacy records"
    )

    import launch
    import research_memory
    launch.add_commands(subparsers)
    research_memory.add_commands(subparsers)
    args = parser.parse_args()
    if getattr(args, "memory_dispatch", False):
        return research_memory.main(args)
    if getattr(args, "launch_dispatch", False):
        return launch.main(args)
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command in ("status", "verify") and any(
        (args.run_dir / marker).exists() for marker in ("proposal.json", "freeze.json", "launch.jsonl", "completion.json")
    ):
        from run_health import report
        return report(args.run_dir.resolve(), args.command == "verify")
    if args.command == "status":
        return cmd_status(args.run_dir)
    elif args.command == "verify":
        return cmd_verify(args.run_dir, args.verbose)
    elif args.command == "datasets":
        if args.datasets_command == "check":
            return cmd_datasets_check(args.registry)
        if args.datasets_command == "for-paper":
            from paper_datasets import run
            return run(args)
        else:
            print(f"Error: Unknown datasets command: {args.datasets_command}", file=sys.stderr)
            return 1
    elif args.command == "import-v1":
        return cmd_import_v1(args.ideas_dir, args.output)
    else:
        print(f"Error: Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
