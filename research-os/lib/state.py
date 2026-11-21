"""
Research OS v2 - State Machine: Transition Rules, Approvals, Stale Propagation

Implements DESIGN.md §4:
- Transition matrix (10 stages with prerequisites)
- Derived states (missing/ok/stale_dependency/stale_input/blocked/awaiting_confirmation)
- Stale propagation through dependency chain
- Approve-by-hash checkpoints (H1, H2)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

# Import from records module
import sys
sys.path.insert(0, str(Path(__file__).parent))
from records import RecordEnvelope


class DerivedStatus(str, Enum):
    """Derived status values (computed, not stored)."""
    MISSING = "missing"
    OK = "ok"
    STALE_DEPENDENCY = "stale_dependency"
    STALE_INPUT = "stale_input"
    BLOCKED = "blocked"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class StageTransition:
    """Represents a stage transition rule."""
    
    def __init__(
        self,
        from_stage: str,
        to_stage: str,
        required_prerequisites: List[str],
        approval_required: Optional[str] = None,
        conditions: Optional[List[str]] = None
    ):
        self.from_stage = from_stage
        self.to_stage = to_stage
        self.required_prerequisites = required_prerequisites
        self.approval_required = approval_required  # H1, H2, or None
        self.conditions = conditions or []


# Transition matrix from DESIGN.md §4.3
TRANSITION_RULES = [
    StageTransition("01-problem", "02-evidence", ["01-problem"]),
    StageTransition("02-evidence", "03-components", ["02-evidence"]),
    StageTransition("03-components", "04-idea", ["03-components"]),
    StageTransition("04-idea", "05-scoop", ["04-idea"], approval_required="H1"),
    StageTransition("05-scoop", "06-prereg", ["05-scoop"], 
                   conditions=["no_blocking_overlap"]),
    StageTransition("06-prereg", "07-pilot", ["06-prereg"]),
    StageTransition("07-pilot", "08-evidence", ["07-pilot"]),
    StageTransition("08-evidence", "09-review", ["08-evidence"]),
    StageTransition("09-review", "10-decision", ["09-review"], 
                   conditions=["verdict_in_pass_or_reject"]),
]


# Stage prerequisites (what must exist before this stage can be created)
STAGE_PREREQUISITES = {
    "01-problem": [],
    "02-evidence": ["01-problem"],
    "03-components": ["02-evidence"],
    "04-idea": ["02-evidence", "03-components"],
    "05-scoop": ["04-idea"],
    "06-prereg": ["04-idea", "05-scoop"],
    "07-pilot": ["06-prereg"],
    "08-evidence": ["07-pilot"],
    "09-review": ["08-evidence"],
    "10-decision": ["09-review"]
}


# Stages requiring human approval
APPROVAL_CHECKPOINTS = {
    "04-idea": "H1",  # After idea card is finalized
    "06-prereg": "H2"  # Before full-stage execution (when stage=full)
}


def load_approvals(stage_dir: Path) -> Optional[Dict]:
    """
    Load approvals.json from stage directory.
    
    Returns:
        Approvals dict or None if file doesn't exist
    """
    approvals_path = stage_dir / "approvals.json"
    if not approvals_path.exists():
        return None
    
    with open(approvals_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def check_approval_status(
    record: RecordEnvelope,
    stage_dir: Path,
    checkpoint: str
) -> Tuple[bool, Optional[str]]:
    """
    Check if a stage has valid approval that matches current record hash.
    
    Args:
        record: The stage record to check
        stage_dir: Directory containing approvals.json
        checkpoint: Checkpoint name (e.g., "H1", "H2")
        
    Returns:
        Tuple of (is_approved, reason)
        - (True, None) if approved and hash matches
        - (False, reason) if not approved or hash mismatch
    """
    approvals = load_approvals(stage_dir)
    
    if approvals is None:
        return False, f"No approvals.json found (checkpoint {checkpoint} required)"
    
    # Check checkpoint field
    if approvals.get("checkpoint") != checkpoint:
        return False, f"Checkpoint mismatch: expected {checkpoint}, got {approvals.get('checkpoint')}"
    
    # Check stage_sha256 matches current record
    expected_hash = record.payload_sha256
    recorded_hash = approvals.get("stage_sha256")
    
    if recorded_hash != expected_hash:
        return False, f"stage_sha256 mismatch: approval for {recorded_hash[:16]}..., current {expected_hash[:16]}..."
    
    # Check that there's at least one approval with decision="approve"
    approval_list = approvals.get("approvals", [])
    has_approval = any(
        a.get("decision") == "approve" 
        for a in approval_list
    )
    
    if not has_approval:
        return False, f"No approval with decision='approve' found"
    
    return True, None


def check_stage_transition_allowed(
    target_stage: str,
    existing_stages: Dict[str, Optional[RecordEnvelope]],
    run_dir: Path
) -> Tuple[bool, Optional[str]]:
    """
    Check if transition to target_stage is allowed.
    
    Checks:
    1. All prerequisite stages exist and are ok
    2. No stage gaps (can't skip stages)
    3. Required approvals exist and match hashes
    
    Args:
        target_stage: Stage to transition to (e.g., "06-prereg")
        existing_stages: Dict of stage -> RecordEnvelope (None if missing)
        run_dir: Run directory path
        
    Returns:
        Tuple of (allowed, reason)
    """
    # Check prerequisites exist
    prerequisites = STAGE_PREREQUISITES.get(target_stage, [])
    
    for prereq in prerequisites:
        if existing_stages.get(prereq) is None:
            return False, f"Missing prerequisite: {prereq}"
    
    # Check no stage gaps (can't skip stages)
    stage_order = list(STAGE_PREREQUISITES.keys())
    target_idx = stage_order.index(target_stage)
    
    for i in range(target_idx):
        stage = stage_order[i]
        if existing_stages.get(stage) is None:
            return False, f"Cannot skip stage {stage}"
    
    # Check approvals for prerequisites that require them
    for prereq in prerequisites:
        if prereq in APPROVAL_CHECKPOINTS:
            checkpoint = APPROVAL_CHECKPOINTS[prereq]
            prereq_record = existing_stages[prereq]
            prereq_dir = run_dir / prereq
            
            is_approved, reason = check_approval_status(
                prereq_record, prereq_dir, checkpoint
            )
            
            if not is_approved:
                return False, f"{prereq} requires approval: {reason}"
    
    return True, None


def compute_derived_status(
    stage: str,
    record: Optional[RecordEnvelope],
    upstream_statuses: Dict[str, DerivedStatus],
    upstream_records: Dict[str, Optional[RecordEnvelope]],
    run_dir: Path
) -> Tuple[DerivedStatus, Optional[str]]:
    """
    Compute derived status for a stage.
    
    Status hierarchy (DESIGN.md §4.2):
    1. missing: No record.json exists
    2. awaiting_confirmation: Needs approval but doesn't have valid one
    3. stale_input: payload_sha256 mismatch
    4. stale_dependency: Upstream changed or is stale
    5. blocked: Condition blocks progress
    6. ok: All checks pass
    
    Args:
        stage: Stage name
        record: Stage record (None if missing)
        upstream_statuses: Map of upstream stage -> status
        upstream_records: Map of stage -> record
        run_dir: Run directory
        
    Returns:
        Tuple of (status, details)
    """
    # 1. Missing
    if record is None:
        return DerivedStatus.MISSING, None
    
    # 2. Verify payload_sha256
    if not record.verify_payload_sha256():
        return (
            DerivedStatus.STALE_INPUT,
            "payload_sha256 mismatch (corrupted or manually edited)"
        )
    
    # 3. Check if approval required and valid
    if stage in APPROVAL_CHECKPOINTS:
        checkpoint = APPROVAL_CHECKPOINTS[stage]
        stage_dir = run_dir / stage
        
        is_approved, reason = check_approval_status(record, stage_dir, checkpoint)
        
        if not is_approved:
            return DerivedStatus.AWAITING_CONFIRMATION, reason
    
    # 4. Check if any upstream is stale (propagate staleness)
    for dep_stage in record.depends_on.keys():
        if dep_stage in upstream_statuses:
            upstream_status = upstream_statuses[dep_stage]
            if upstream_status in [
                DerivedStatus.STALE_INPUT,
                DerivedStatus.STALE_DEPENDENCY,
                DerivedStatus.AWAITING_CONFIRMATION
            ]:
                return (
                    DerivedStatus.STALE_DEPENDENCY,
                    f"upstream {dep_stage} is {upstream_status.value}"
                )
    
    # 5. Verify dependency hashes
    from records import verify_dependency_chain
    
    stale_deps = verify_dependency_chain(record, {
        k: v for k, v in upstream_records.items() if v is not None
    })
    
    if any(stale_deps.values()):
        stale_list = [k for k, v in stale_deps.items() if v]
        return (
            DerivedStatus.STALE_DEPENDENCY,
            f"upstream hash changed: {', '.join(stale_list)}"
        )
    
    # 6. All checks pass
    return DerivedStatus.OK, None


def compute_all_stage_statuses(
    stage_records: Dict[str, Optional[RecordEnvelope]],
    run_dir: Path
) -> Dict[str, Tuple[DerivedStatus, Optional[str]]]:
    """
    Compute derived status for all stages.
    
    Args:
        stage_records: Dict mapping stage name -> RecordEnvelope (or None)
        run_dir: Run directory path
        
    Returns:
        Dict mapping stage name -> (status, details)
    """
    stage_order = list(STAGE_PREREQUISITES.keys())
    statuses = {}
    status_values = {}  # Just the enum values for propagation
    
    for stage in stage_order:
        record = stage_records.get(stage)
        
        # Get upstream records and statuses
        upstream_records = {
            s: stage_records[s]
            for s in stage_order
            if s < stage
        }
        
        status, details = compute_derived_status(
            stage, record, status_values, upstream_records, run_dir
        )
        
        statuses[stage] = (status, details)
        status_values[stage] = status
    
    return statuses


def format_status_line(
    stage: str,
    status: DerivedStatus,
    details: Optional[str] = None
) -> str:
    """
    Format a status line for display.
    
    Args:
        stage: Stage name
        status: Derived status
        details: Optional details string
        
    Returns:
        Formatted line with emoji and spacing
    """
    status_marks = {
        DerivedStatus.MISSING: "⚫",
        DerivedStatus.OK: "✓",
        DerivedStatus.STALE_DEPENDENCY: "⚠",
        DerivedStatus.STALE_INPUT: "⚠",
        DerivedStatus.BLOCKED: "✗",
        DerivedStatus.AWAITING_CONFIRMATION: "?"
    }
    
    mark = status_marks.get(status, "?")
    line = f"{mark} {stage:15s} {status.value:25s}"
    
    if details:
        line += f"  ({details})"
    
    return line


def save_approval(
    stage_dir: Path,
    checkpoint: str,
    stage_sha256: str,
    by: str = "human",
    decision: str = "approve",
    rationale: Optional[str] = None
) -> None:
    """
    Save approval record to approvals.json.
    
    Args:
        stage_dir: Stage directory
        checkpoint: Checkpoint name (H1, H2)
        stage_sha256: Hash of the stage being approved
        by: Who approved (human:<name> or agent)
        decision: approve, reject, or modify
        rationale: Optional explanation
    """
    from datetime import datetime, timezone
    
    approval_entry = {
        "by": by,
        "at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "rationale": rationale or "",
        "changes_requested": []
    }
    
    approvals = {
        "checkpoint": checkpoint,
        "stage_sha256": stage_sha256,
        "approvals": [approval_entry]
    }
    
    # Write with canonical JSON
    from records import canonical_json
    
    stage_dir.mkdir(parents=True, exist_ok=True)
    approvals_path = stage_dir / "approvals.json"
    
    with open(approvals_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(canonical_json(approvals))
