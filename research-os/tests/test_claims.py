"""
Unit tests for claims.py - Gates G1-G5
"""

import unittest
import tempfile
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from claims import (
    check_row_ref_exists,
    validate_paper_span_evidence,
    validate_run_evidence,
    check_scope_coverage,
    can_promote_to_supported,
    validate_decision_consistency,
    ClaimStatus
)


class TestG2RunEvidence(unittest.TestCase):
    """Test G2: run evidence validation."""
    
    def test_valid_row_ref(self):
        """Test valid row reference."""
        results = [
            {
                "dataset": "Waveform",
                "arm": "hybrid",
                "seed": 11,
                "metric": 0.85,
                "protocol_sha256": "sha256:abc123"
            }
        ]
        
        exists, error = check_row_ref_exists(
            "Waveform|hybrid|11",
            results,
            "sha256:abc123"
        )
        
        self.assertTrue(exists)
        self.assertIsNone(error)
    
    def test_fake_row_ref(self):
        """Test (b): fake row_ref fails."""
        results = [
            {
                "dataset": "Waveform",
                "arm": "hybrid",
                "seed": 11,
                "protocol_sha256": "sha256:abc123"
            }
        ]
        
        # Non-existent row
        exists, error = check_row_ref_exists(
            "Waveform|hybrid|99",
            results,
            "sha256:abc123"
        )
        
        self.assertFalse(exists)
        self.assertIn("not found", error)


class TestG3Promotion(unittest.TestCase):
    """Test G3: promotion to supported."""
    
    def test_no_run_evidence(self):
        """Test (a): no run evidence cannot support."""
        claim = {
            "evidence": [
                {"kind": "paper_span", "card_id": "c1"}
            ]
        }
        
        can_promote, error = can_promote_to_supported(
            claim, [], "sha256:test"
        )
        
        self.assertFalse(can_promote)
        self.assertIn("No run evidence", error)
    
    def test_with_run_evidence(self):
        """Test promotion with valid run evidence."""
        claim = {
            "evidence": [
                {
                    "kind": "run",
                    "evidence_level": "local-substitute",
                    "row_refs": ["W|h|11"]
                }
            ]
        }
        
        can_promote, error = can_promote_to_supported(
            claim, [], "sha256:test"
        )
        
        self.assertTrue(can_promote)


class TestG4ScopeCoverage(unittest.TestCase):
    """Test G4: scope convergence."""
    
    def test_scope_overflow(self):
        """Test (c): scope overflow detected."""
        claim_scope = ["DS1", "DS2", "DS3", "DS4", "DS5"]
        tested = ["DS1", "DS2", "DS3"]
        
        covered, valid, overflow = check_scope_coverage(claim_scope, tested)
        
        self.assertFalse(covered)
        self.assertEqual(len(overflow), 2)
        self.assertIn("DS4", overflow)
        self.assertIn("DS5", overflow)
    
    def test_scope_covered(self):
        """Test scope fully covered."""
        claim_scope = ["DS1", "DS2"]
        tested = ["DS1", "DS2", "DS3"]
        
        covered, valid, overflow = check_scope_coverage(claim_scope, tested)
        
        self.assertTrue(covered)
        self.assertEqual(len(overflow), 0)


class TestDecisionValidation(unittest.TestCase):
    """Test decision consistency."""
    
    def test_partial_missing_refuted(self):
        """Test (d): partial without refuted/unknown fails."""
        claims = [
            {"status": "supported"},
            {"status": "supported"}
        ]
        
        valid, error = validate_decision_consistency("partial", claims)
        
        self.assertFalse(valid)
        self.assertIn("refuted or unknown", error)
    
    def test_partial_with_refuted(self):
        """Test partial with refuted is valid."""
        claims = [
            {"status": "supported"},
            {"status": "refuted"}
        ]
        
        valid, error = validate_decision_consistency("partial", claims)
        
        self.assertTrue(valid)


if __name__ == '__main__':
    unittest.main()
