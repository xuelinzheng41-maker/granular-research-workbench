"""
Research OS v2 - Protocol Compiler: prereg → protocol with conflict detection

Implements DESIGN.md §6:
- 06-prereg/record.json is the SINGLE SOURCE OF TRUTH for:
  * metric, threshold, seeds, datasets, split, arms, verdict_rules
- manifest.json and pilot records can ONLY reference prereg_sha256
- Compiler expands prereg into protocol.json
- Conflict detection: any value in manifest/pilot that differs from prereg → exit 2

This enforces P2: "bind by hash, don't restate"
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class CompileError(Exception):
    """Compilation error (conflicts, missing fields, etc.)."""
    pass


def load_json(path: Path) -> Dict:
    """Load JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_prereg_values(prereg_record: Dict) -> Dict[str, Any]:
    """
    Extract experimental parameters from prereg record.
    
    Args:
        prereg_record: The 06-prereg record.json
        
    Returns:
        Dict of extracted values
    """
    payload = prereg_record.get("payload", {})
    
    # Required fields per DESIGN.md §5.6
    required = [
        "hypothesis_claims", "metric", "datasets", "seeds", 
        "stage", "split", "arms", "threshold"
    ]
    
    missing = [f for f in required if f not in payload]
    if missing:
        raise CompileError(f"Missing required fields in prereg: {', '.join(missing)}")
    
    return {
        "hypothesis_claims": payload["hypothesis_claims"],
        "metric": payload["metric"],
        "datasets": payload["datasets"],
        "seeds": payload["seeds"],
        "stage": payload["stage"],
        "split": payload["split"],
        "arms": payload["arms"],
        "threshold": payload["threshold"],
        "min_datasets": payload.get("min_datasets"),
        "win_rule": payload.get("win_rule"),
        "kill_if": payload.get("kill_if"),
        "compute_budget_minutes": payload.get("compute_budget_minutes"),
        "analysis_plan": payload.get("analysis_plan")
    }


def check_manifest_conflicts(
    manifest: Dict,
    prereg_values: Dict[str, Any],
    prereg_sha256: str
) -> List[str]:
    """
    Check if manifest has any values that conflict with prereg.
    
    Manifest should ONLY contain prereg_sha256, not actual values.
    
    Args:
        manifest: The manifest.json content
        prereg_values: Extracted prereg values
        prereg_sha256: Hash of prereg record
        
    Returns:
        List of conflict messages (empty if no conflicts)
    """
    conflicts = []
    
    # Check if manifest has prereg_sha256 reference
    manifest_prereg_ref = manifest.get("prereg_sha256")
    if not manifest_prereg_ref:
        conflicts.append("manifest.json missing prereg_sha256 reference")
    elif manifest_prereg_ref != prereg_sha256:
        conflicts.append(
            f"manifest.json prereg_sha256 mismatch: "
            f"expected {prereg_sha256[:16]}..., got {manifest_prereg_ref[:16]}..."
        )
    
    # Check for forbidden direct values (should use prereg_sha256 instead)
    forbidden_keys = ["threshold", "seeds", "datasets", "metric"]
    
    for key in forbidden_keys:
        if key in manifest and manifest[key] != prereg_values.get(key):
            conflicts.append(
                f"manifest.json contains {key}={manifest[key]} but prereg has {key}={prereg_values.get(key)}"
            )
    
    return conflicts


def check_pilot_conflicts(
    pilot_payload: Dict,
    prereg_values: Dict[str, Any],
    prereg_sha256: str
) -> List[str]:
    """
    Check if pilot record has any values that conflict with prereg.
    
    Args:
        pilot_payload: The pilot record payload
        prereg_values: Extracted prereg values
        prereg_sha256: Hash of prereg record
        
    Returns:
        List of conflict messages (empty if no conflicts)
    """
    conflicts = []
    
    # Check if pilot has prereg_sha256 reference in inputs
    if "prereg_sha256" in pilot_payload:
        pilot_prereg_ref = pilot_payload["prereg_sha256"]
        if pilot_prereg_ref != prereg_sha256:
            conflicts.append(
                f"pilot prereg_sha256 mismatch: "
                f"expected {prereg_sha256[:16]}..., got {pilot_prereg_ref[:16]}..."
            )
    
    # Check for conflicting values
    conflict_keys = {
        "threshold": "threshold",
        "datasets": "datasets",
        "seeds": "seeds"
    }
    
    for pilot_key, prereg_key in conflict_keys.items():
        if pilot_key in pilot_payload:
            pilot_val = pilot_payload[pilot_key]
            prereg_val = prereg_values.get(prereg_key)
            
            if pilot_val != prereg_val:
                conflicts.append(
                    f"pilot {pilot_key}={pilot_val} conflicts with prereg {prereg_key}={prereg_val}"
                )
    
    return conflicts


def compile_protocol(
    prereg_record: Dict,
    prereg_sha256: str,
    manifest: Optional[Dict] = None,
    pilot_payload: Optional[Dict] = None
) -> Dict:
    """
    Compile protocol.json from prereg record.
    
    Args:
        prereg_record: The 06-prereg record
        prereg_sha256: Hash of prereg record
        manifest: Optional manifest.json for conflict checking
        pilot_payload: Optional pilot payload for conflict checking
        
    Returns:
        protocol dict
        
    Raises:
        CompileError: If conflicts detected or required fields missing
    """
    # Extract values from prereg
    try:
        prereg_values = extract_prereg_values(prereg_record)
    except CompileError as e:
        raise CompileError(f"Failed to extract prereg values: {e}")
    
    # Check for conflicts
    all_conflicts = []
    
    if manifest:
        manifest_conflicts = check_manifest_conflicts(manifest, prereg_values, prereg_sha256)
        all_conflicts.extend(manifest_conflicts)
    
    if pilot_payload:
        pilot_conflicts = check_pilot_conflicts(pilot_payload, prereg_values, prereg_sha256)
        all_conflicts.extend(pilot_conflicts)
    
    if all_conflicts:
        conflict_msg = "\n".join(f"  - {c}" for c in all_conflicts)
        raise CompileError(f"Compilation conflicts detected:\n{conflict_msg}")
    
    # Build protocol.json
    protocol = {
        "schema_version": 1,
        "source": "06-prereg",
        "prereg_sha256": prereg_sha256,
        "hypothesis_claims": prereg_values["hypothesis_claims"],
        "metric": prereg_values["metric"],
        "datasets": prereg_values["datasets"],
        "seeds": prereg_values["seeds"],
        "stage": prereg_values["stage"],
        "split": prereg_values["split"],
        "arms": prereg_values["arms"],
        "threshold": prereg_values["threshold"]
    }
    
    # Add optional fields if present
    optional = ["min_datasets", "win_rule", "kill_if", "compute_budget_minutes", "analysis_plan"]
    for key in optional:
        if prereg_values.get(key) is not None:
            protocol[key] = prereg_values[key]
    
    return protocol


def save_protocol(protocol: Dict, output_path: Path) -> None:
    """
    Save protocol to JSON file with canonical format.
    
    Args:
        protocol: Protocol dict
        output_path: Where to save protocol.json
    """
    # Use canonical JSON from records module
    sys.path.insert(0, str(Path(__file__).parent))
    from records import canonical_json
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(canonical_json(protocol))


def compile_prereg_to_protocol(
    prereg_path: Path,
    output_path: Path,
    manifest_path: Optional[Path] = None,
    pilot_path: Optional[Path] = None
) -> Tuple[bool, Optional[str]]:
    """
    Main compilation function.
    
    Args:
        prereg_path: Path to 06-prereg/record.json
        output_path: Path to output protocol.json
        manifest_path: Optional path to manifest.json for checking
        pilot_path: Optional path to pilot record.json for checking
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Load prereg
        prereg_record = load_json(prereg_path)
        prereg_sha256 = prereg_record.get("payload_sha256")
        
        if not prereg_sha256:
            return False, "prereg record missing payload_sha256"
        
        # Load optional files
        manifest = None
        if manifest_path and manifest_path.exists():
            manifest = load_json(manifest_path)
        
        pilot_payload = None
        if pilot_path and pilot_path.exists():
            pilot_record = load_json(pilot_path)
            pilot_payload = pilot_record.get("payload")
        
        # Compile
        protocol = compile_protocol(prereg_record, prereg_sha256, manifest, pilot_payload)
        
        # Save
        save_protocol(protocol, output_path)
        
        return True, None
        
    except FileNotFoundError as e:
        return False, str(e)
    except CompileError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"
