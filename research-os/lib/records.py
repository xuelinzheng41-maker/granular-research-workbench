"""
Research OS v2 - Records: Envelope, Canonical JSON, Hashing, Chain

Implements:
- Envelope structure (schema_version, stage, kind, record_id, attempt, etc.)
- Canonical JSON serialization (sort_keys, ensure_ascii=False, indent=2, LF)
- SHA256 hashing for records and payloads
- Dependency chain tracking
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def canonical_json(obj: Any) -> str:
    """
    Serialize object to canonical JSON:
    - sort_keys=True
    - ensure_ascii=False
    - indent=2
    - LF line endings
    - UTF-8 encoding
    
    Returns the canonical JSON string.
    """
    json_str = json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        indent=2
    )
    # Ensure LF line endings (Python's json uses platform-specific by default)
    json_str = json_str.replace('\r\n', '\n').replace('\r', '\n')
    return json_str


def sha256_canonical(obj: Any) -> str:
    """
    Compute SHA256 hash of the canonical JSON representation.
    
    Returns: "sha256:<hex>"
    """
    canonical = canonical_json(obj)
    hash_bytes = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return f"sha256:{hash_bytes}"


def compute_payload_sha256(
    payload: Dict[str, Any],
    depends_on: Optional[Dict[str, str]] = None,
    inputs: Optional[Dict[str, str]] = None
) -> str:
    """
    Compute payload_sha256 from payload, depends_on, and inputs.
    
    According to DESIGN.md §3:
    payload_sha256 = sha256(canonical({"payload", "depends_on", "inputs"}))
    
    Returns: "sha256:<hex>"
    """
    composite = {
        "payload": payload,
        "depends_on": depends_on or {},
        "inputs": inputs or {}
    }
    return sha256_canonical(composite)


class RecordEnvelope:
    """
    Record envelope structure according to DESIGN.md §3.
    
    Required fields:
    - schema_version: int (always 2 for v2)
    - stage: str (e.g., "01-problem", "04-idea")
    - kind: str (stage-specific, e.g., "idea_card")
    - record_id: str (e.g., "04-idea@1")
    - attempt: int
    - created_at: ISO 8601 timestamp with timezone
    - produced_by: dict with tool/version/tool_sha256/by
    - depends_on: dict mapping stage -> sha256
    - inputs: dict mapping input_name -> sha256
    - checks: list of dicts with tool/exit/output_sha256
    - payload: dict (stage-specific)
    - payload_sha256: str
    """
    
    def __init__(
        self,
        stage: str,
        kind: str,
        record_id: str,
        attempt: int,
        payload: Dict[str, Any],
        depends_on: Optional[Dict[str, str]] = None,
        inputs: Optional[Dict[str, str]] = None,
        checks: Optional[List[Dict[str, Any]]] = None,
        tool_version: str = "2.0.0-dev",
        tool_sha256: Optional[str] = None,
        by: str = "agent"
    ):
        self.schema_version = 2
        self.stage = stage
        self.kind = kind
        self.record_id = record_id
        self.attempt = attempt
        self.created_at = datetime.now(timezone.utc).isoformat()
        
        self.produced_by = {
            "tool": "research-os",
            "version": tool_version,
            "tool_sha256": tool_sha256 or "sha256:placeholder",
            "by": by
        }
        
        self.depends_on = depends_on or {}
        self.inputs = inputs or {}
        self.checks = checks or []
        self.payload = payload
        
        # Compute payload_sha256
        self.payload_sha256 = compute_payload_sha256(
            payload, self.depends_on, self.inputs
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert envelope to dictionary."""
        return {
            "schema_version": self.schema_version,
            "stage": self.stage,
            "kind": self.kind,
            "record_id": self.record_id,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "produced_by": self.produced_by,
            "depends_on": self.depends_on,
            "inputs": self.inputs,
            "checks": self.checks,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256
        }
    
    def to_canonical_json(self) -> str:
        """Serialize envelope to canonical JSON."""
        return canonical_json(self.to_dict())
    
    def save(self, path: Union[str, Path]) -> None:
        """
        Save envelope to file as canonical JSON with UTF-8 encoding.
        
        Args:
            path: File path to save to (typically <stage>/record.json)
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with UTF-8 encoding and LF line endings
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.to_canonical_json())
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> 'RecordEnvelope':
        """
        Load envelope from file.
        
        Args:
            path: File path to load from
            
        Returns:
            RecordEnvelope instance
        """
        path = Path(path)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct envelope
        envelope = cls.__new__(cls)
        envelope.schema_version = data["schema_version"]
        envelope.stage = data["stage"]
        envelope.kind = data["kind"]
        envelope.record_id = data["record_id"]
        envelope.attempt = data["attempt"]
        envelope.created_at = data["created_at"]
        envelope.produced_by = data["produced_by"]
        envelope.depends_on = data["depends_on"]
        envelope.inputs = data["inputs"]
        envelope.checks = data["checks"]
        envelope.payload = data["payload"]
        envelope.payload_sha256 = data["payload_sha256"]
        
        return envelope
    
    def verify_payload_sha256(self) -> bool:
        """
        Verify that stored payload_sha256 matches the computed hash.
        
        Returns:
            True if hash matches, False otherwise
        """
        expected = compute_payload_sha256(
            self.payload, self.depends_on, self.inputs
        )
        return self.payload_sha256 == expected


def verify_dependency_chain(
    stage_record: RecordEnvelope,
    upstream_records: Dict[str, RecordEnvelope]
) -> Dict[str, bool]:
    """
    Verify that depends_on hashes match current upstream payload_sha256.
    
    Args:
        stage_record: The record to verify
        upstream_records: Dict mapping stage name -> RecordEnvelope
        
    Returns:
        Dict mapping stage name -> is_stale (True if stale, False if ok)
    """
    stale_status = {}
    
    for dep_stage, dep_hash in stage_record.depends_on.items():
        if dep_stage not in upstream_records:
            stale_status[dep_stage] = True  # Missing dependency
            continue
        
        current_hash = upstream_records[dep_stage].payload_sha256
        stale_status[dep_stage] = (dep_hash != current_hash)
    
    return stale_status


def verify_input_hash(
    input_name: str,
    input_path: Union[str, Path],
    expected_hash: str
) -> bool:
    """
    Verify that an input file's hash matches the expected hash.
    
    Args:
        input_name: Name of the input (for error messages)
        input_path: Path to the input file
        expected_hash: Expected hash (format: "sha256:<hex>")
        
    Returns:
        True if hash matches, False otherwise
    """
    path = Path(input_path)
    if not path.exists():
        return False
    
    with open(path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    file_hash_str = f"sha256:{file_hash}"
    return file_hash_str == expected_hash
