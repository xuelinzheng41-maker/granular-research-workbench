"""
Research OS v2 - Claim Ledger with Promotion Gates G1-G5

Implements DESIGN.md §8:
- Claim status: hypothesis/supported/refuted/unknown
- Evidence types: paper_span, run, math_check
- Promotion gates G1-G5
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum


class ClaimStatus(str, Enum):
    """Claim status values."""
    HYPOTHESIS = "hypothesis"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNKNOWN = "unknown"


class EvidenceLevel(str, Enum):
    """Evidence quality levels."""
    LOCAL_SUBSTITUTE = "local-substitute"
    CLOUD_FILTER = "cloud-filter"


def load_results_jsonl(results_path: Path) -> List[Dict[str, Any]]:
    """Load results.jsonl as list of dicts."""
    results = []
    with open(results_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def check_row_ref_exists(
    row_ref: str,
    results: List[Dict[str, Any]],
    expected_protocol_sha256: str
) -> Tuple[bool, Optional[str]]:
    """
    G2: Verify row_ref exists in results.jsonl.
    
    Args:
        row_ref: Format "dataset|arm|seed"
        results: Loaded results.jsonl
        expected_protocol_sha256: Protocol hash to verify
        
    Returns:
        (exists, error_message)
    """
    parts = row_ref.split('|')
    if len(parts) != 3:
        return False, f"Invalid row_ref format: {row_ref}"
    
    dataset, arm, seed = parts
    try:
        seed_int = int(seed)
    except ValueError:
        return False, f"Invalid seed in row_ref: {seed}"
    
    # Find matching row
    for row in results:
        if (row.get('dataset') == dataset and 
            row.get('arm') == arm and 
            row.get('seed') == seed_int):
            
            # Check protocol hash
            row_protocol = row.get('protocol_sha256')
            if row_protocol != expected_protocol_sha256:
                return False, f"Protocol mismatch: row has {row_protocol}, expected {expected_protocol_sha256}"
            
            return True, None
    
    return False, f"Row not found: {row_ref}"


def validate_paper_span_evidence(
    evidence: Dict[str, Any],
    cards_index: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """
    G1: Validate paper_span evidence.
    
    Checks:
    - card_id exists in KB index
    - locator is present
    - span_sha256 is present
    """
    card_id = evidence.get('card_id')
    if not card_id:
        return False, "Missing card_id"
    
    if cards_index and card_id not in cards_index:
        return False, f"card_id not in KB: {card_id}"
    
    locator = evidence.get('locator')
    if not locator:
        return False, "Missing locator"
    
    span_sha256 = evidence.get('span_sha256')
    if not span_sha256:
        return False, "Missing span_sha256"
    
    return True, None


def validate_run_evidence(
    evidence: Dict[str, Any],
    results: List[Dict[str, Any]],
    protocol_sha256: str
) -> Tuple[bool, Optional[str]]:
    """
    G2: Validate run evidence.
    
    Checks:
    - row_refs exist in results.jsonl
    - protocol_sha256 matches
    """
    row_refs = evidence.get('row_refs', [])
    if not row_refs:
        return False, "Missing row_refs"
    
    for row_ref in row_refs:
        exists, error = check_row_ref_exists(row_ref, results, protocol_sha256)
        if not exists:
            return False, error
    
    return True, None


def check_scope_coverage(
    claim_scope: List[str],
    tested_datasets: List[str]
) -> Tuple[bool, List[str], List[str]]:
    """
    G4: Check if claim scope is covered by actual tests.
    
    Returns:
        (is_covered, valid_datasets, overflow_datasets)
    """
    claim_set = set(claim_scope)
    tested_set = set(tested_datasets)
    
    valid = list(claim_set & tested_set)
    overflow = list(claim_set - tested_set)
    
    is_covered = len(overflow) == 0
    
    return is_covered, valid, overflow


def can_promote_to_supported(
    claim: Dict[str, Any],
    results: List[Dict[str, Any]],
    protocol_sha256: str,
    review_mentioned: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    G3: Check if claim can be promoted to supported.
    
    Requirements:
    - At least 1 run evidence
    - evidence_level >= local-substitute
    - review mentions this claim (optional check)
    """
    evidence_list = claim.get('evidence', [])
    
    # Check for run evidence
    has_run_evidence = False
    has_sufficient_level = False
    
    for ev in evidence_list:
        if ev.get('kind') == 'run':
            has_run_evidence = True
            
            # Check evidence level
            level = ev.get('evidence_level', '')
            if level == EvidenceLevel.LOCAL_SUBSTITUTE:
                has_sufficient_level = True
                break
    
    if not has_run_evidence:
        return False, "No run evidence"
    
    if not has_sufficient_level:
        return False, "evidence_level below local-substitute"
    
    # Note: review check would be implemented when review stage is available
    # For now, we allow promotion if evidence requirements are met
    
    return True, None


def evaluate_falsifier(
    claim: Dict[str, Any],
    results: List[Dict[str, Any]]
) -> bool:
    """
    G5: Check if falsifier condition is met.
    
    Simplified: Check if any result contradicts the claim.
    Real implementation would evaluate structured falsifier.
    """
    falsifier = claim.get('falsifier', {})
    
    # Example: metric_below falsifier
    if falsifier.get('kind') == 'metric_below':
        metric_name = falsifier.get('metric')
        threshold = falsifier.get('value')
        
        for result in results:
            if result.get('metric') is not None:
                if result['metric'] < threshold:
                    return True  # Falsifier triggered
    
    return False


def validate_decision_consistency(
    decision: str,
    claims: List[Dict[str, Any]]
) -> Tuple[bool, Optional[str]]:
    """
    Validate decision is consistent with claim statuses.
    
    Rules:
    - partial requires ≥1 refuted or unknown
    - viable requires all supported
    """
    statuses = [c.get('status') for c in claims]
    
    supported = sum(1 for s in statuses if s == ClaimStatus.SUPPORTED)
    refuted = sum(1 for s in statuses if s == ClaimStatus.REFUTED)
    unknown = sum(1 for s in statuses if s == ClaimStatus.UNKNOWN)
    
    if decision == 'partial':
        if refuted == 0 and unknown == 0:
            return False, "partial decision requires ≥1 refuted or unknown claim"
    
    elif decision == 'viable':
        if refuted > 0 or unknown > 0:
            return False, "viable decision requires all claims supported"
    
    return True, None


class ClaimLedger:
    """Claim ledger manager."""
    
    def __init__(self, claims_path: Path, results_path: Optional[Path] = None):
        """Initialize ledger."""
        with open(claims_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        self.results = []
        if results_path and results_path.exists():
            self.results = load_results_jsonl(results_path)
    
    def validate_all_claims(
        self,
        protocol_sha256: str,
        tested_datasets: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Validate all claims in ledger.
        
        Returns:
            (all_valid, errors)
        """
        errors = []
        
        claims = self.data.get('claims', [])
        
        for claim in claims:
            claim_id = claim.get('id', '?')
            
            # Validate evidence
            for evidence in claim.get('evidence', []):
                kind = evidence.get('kind')
                
                if kind == 'paper_span':
                    valid, error = validate_paper_span_evidence(evidence)
                    if not valid:
                        errors.append(f"Claim {claim_id}: {error}")
                
                elif kind == 'run':
                    valid, error = validate_run_evidence(
                        evidence, self.results, protocol_sha256
                    )
                    if not valid:
                        errors.append(f"Claim {claim_id}: {error}")
            
            # Check scope
            scope = claim.get('scope', '')
            if scope and tested_datasets:
                # Parse scope (simplified)
                claim_datasets = [ds.strip() for ds in scope.split(',') if ds.strip()]
                covered, valid, overflow = check_scope_coverage(claim_datasets, tested_datasets)
                
                if not covered:
                    errors.append(f"Claim {claim_id}: scope overflow - {overflow} not tested")
        
        return len(errors) == 0, errors
