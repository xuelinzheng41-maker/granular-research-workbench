"""
Unit tests for research-os/lib/state.py

Tests:
1. Stage prerequisites
2. Transition rules
3. Approval checking (by-hash)
4. Stage skip prevention
5. Stale propagation
6. Derived status computation
7. Approval invalidation on hash change
8. Rejection path (no --force)
"""

import unittest
import tempfile
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from records import RecordEnvelope
from state import (
    STAGE_PREREQUISITES,
    APPROVAL_CHECKPOINTS,
    DerivedStatus,
    check_approval_status,
    check_stage_transition_allowed,
    compute_derived_status,
    compute_all_stage_statuses,
    save_approval,
    load_approvals
)


class TestStagePrerequisites(unittest.TestCase):
    """Test stage prerequisite definitions."""
    
    def test_stage_count(self):
        """Test that we have exactly 10 stages."""
        self.assertEqual(len(STAGE_PREREQUISITES), 10)
    
    def test_stage_order(self):
        """Test that stages are in correct order."""
        stages = list(STAGE_PREREQUISITES.keys())
        expected = [
            "01-problem", "02-evidence", "03-components", "04-idea", "05-scoop",
            "06-prereg", "07-pilot", "08-evidence", "09-review", "10-decision"
        ]
        self.assertEqual(stages, expected)
    
    def test_01_has_no_prerequisites(self):
        """Test that first stage has no prerequisites."""
        self.assertEqual(STAGE_PREREQUISITES["01-problem"], [])
    
    def test_04_requires_02_and_03(self):
        """Test that 04-idea requires both 02 and 03."""
        prereqs = STAGE_PREREQUISITES["04-idea"]
        self.assertIn("02-evidence", prereqs)
        self.assertIn("03-components", prereqs)


class TestApprovalCheckpoints(unittest.TestCase):
    """Test approval checkpoint configuration."""
    
    def test_h1_checkpoint_on_04(self):
        """Test that H1 checkpoint is on 04-idea."""
        self.assertEqual(APPROVAL_CHECKPOINTS.get("04-idea"), "H1")
    
    def test_h2_checkpoint_on_06(self):
        """Test that H2 checkpoint is on 06-prereg."""
        self.assertEqual(APPROVAL_CHECKPOINTS.get("06-prereg"), "H2")
    
    def test_no_force_flag(self):
        """Test that there's no --force mechanism (design requirement)."""
        # This is enforced by not having any bypass in check_approval_status
        # We verify by checking the function signature has no force parameter
        import inspect
        sig = inspect.signature(check_approval_status)
        self.assertNotIn('force', sig.parameters)
        self.assertNotIn('skip_approval', sig.parameters)


class TestApprovalSaveLoad(unittest.TestCase):
    """Test saving and loading approvals."""
    
    def test_save_and_load_approval(self):
        """Test saving and loading approval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            test_hash = "sha256:abcd1234"
            
            save_approval(
                stage_dir,
                checkpoint="H1",
                stage_sha256=test_hash,
                by="human:tester",
                decision="approve",
                rationale="Test approval"
            )
            
            approvals = load_approvals(stage_dir)
            
            self.assertIsNotNone(approvals)
            self.assertEqual(approvals["checkpoint"], "H1")
            self.assertEqual(approvals["stage_sha256"], test_hash)
            self.assertEqual(len(approvals["approvals"]), 1)
            self.assertEqual(approvals["approvals"][0]["decision"], "approve")
    
    def test_load_missing_approvals(self):
        """Test loading non-existent approvals returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            approvals = load_approvals(stage_dir)
            self.assertIsNone(approvals)


class TestApprovalValidation(unittest.TestCase):
    """Test approval validation (approve-by-hash)."""
    
    def test_valid_approval(self):
        """Test that valid approval passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            
            payload = {"test": "data"}
            record = RecordEnvelope(
                stage="04-idea",
                kind="idea_card",
                record_id="04-idea@1",
                attempt=1,
                payload=payload
            )
            
            # Save approval with matching hash
            save_approval(
                stage_dir,
                checkpoint="H1",
                stage_sha256=record.payload_sha256,
                by="human:tester",
                decision="approve"
            )
            
            is_approved, reason = check_approval_status(record, stage_dir, "H1")
            
            self.assertTrue(is_approved)
            self.assertIsNone(reason)
    
    def test_hash_mismatch_invalidates(self):
        """Test that hash mismatch invalidates approval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            
            payload = {"test": "data"}
            record = RecordEnvelope(
                stage="04-idea",
                kind="idea_card",
                record_id="04-idea@1",
                attempt=1,
                payload=payload
            )
            
            # Save approval with WRONG hash
            save_approval(
                stage_dir,
                checkpoint="H1",
                stage_sha256="sha256:wrong_hash_0000000000000000000000000000000000000000000000000000",
                by="human:tester",
                decision="approve"
            )
            
            is_approved, reason = check_approval_status(record, stage_dir, "H1")
            
            self.assertFalse(is_approved)
            self.assertIn("mismatch", reason.lower())
    
    def test_missing_approval_file(self):
        """Test that missing approval file fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            
            payload = {"test": "data"}
            record = RecordEnvelope(
                stage="04-idea",
                kind="idea_card",
                record_id="04-idea@1",
                attempt=1,
                payload=payload
            )
            
            is_approved, reason = check_approval_status(record, stage_dir, "H1")
            
            self.assertFalse(is_approved)
            self.assertIn("No approvals.json", reason)
    
    def test_rejection_blocks_progress(self):
        """Test that decision='reject' blocks progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stage_dir = Path(tmpdir)
            
            payload = {"test": "data"}
            record = RecordEnvelope(
                stage="04-idea",
                kind="idea_card",
                record_id="04-idea@1",
                attempt=1,
                payload=payload
            )
            
            # Save rejection
            save_approval(
                stage_dir,
                checkpoint="H1",
                stage_sha256=record.payload_sha256,
                by="human:tester",
                decision="reject",
                rationale="Not ready"
            )
            
            is_approved, reason = check_approval_status(record, stage_dir, "H1")
            
            self.assertFalse(is_approved)
            self.assertIn("No approval with decision='approve'", reason)


class TestStageTransitions(unittest.TestCase):
    """Test stage transition validation."""
    
    def test_cannot_skip_stages(self):
        """Test that skipping stages is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            # Create records for 01-03 only
            r1 = RecordEnvelope("01-problem", "problem_card", "01-problem@1", 1, {"q": "x"})
            r2 = RecordEnvelope("02-evidence", "evidence_card", "02-evidence@1", 1, {"a": []}, 
                               depends_on={"01-problem": r1.payload_sha256})
            r3 = RecordEnvelope("03-components", "component_library", "03-components@1", 1, {"l": []},
                               depends_on={"02-evidence": r2.payload_sha256})
            
            stage_records = {
                "01-problem": r1,
                "02-evidence": r2,
                "03-components": r3,
                "04-idea": None,  # Missing!
                "05-scoop": None
            }
            
            # Try to create 05-scoop without 04-idea
            allowed, reason = check_stage_transition_allowed("05-scoop", stage_records, run_dir)
            
            self.assertFalse(allowed)
            self.assertIn("04-idea", reason)
    
    def test_valid_sequential_transition(self):
        """Test that sequential transitions are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            r1 = RecordEnvelope("01-problem", "problem_card", "01-problem@1", 1, {"q": "x"})
            
            stage_records = {
                "01-problem": r1,
                "02-evidence": None
            }
            
            allowed, reason = check_stage_transition_allowed("02-evidence", stage_records, run_dir)
            
            self.assertTrue(allowed)
            self.assertIsNone(reason)


class TestDerivedStatus(unittest.TestCase):
    """Test derived status computation."""
    
    def test_missing_status(self):
        """Test that missing record gives missing status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            status, details = compute_derived_status(
                "01-problem", None, {}, {}, run_dir
            )
            
            self.assertEqual(status, DerivedStatus.MISSING)
    
    def test_corrupted_payload_gives_stale_input(self):
        """Test that corrupted payload_sha256 gives stale_input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            record = RecordEnvelope(
                "01-problem", "problem_card", "01-problem@1", 1,
                {"test": "data"}
            )
            
            # Tamper with payload
            record.payload["test"] = "modified"
            
            status, details = compute_derived_status(
                "01-problem", record, {}, {}, run_dir
            )
            
            self.assertEqual(status, DerivedStatus.STALE_INPUT)
            self.assertIn("payload_sha256 mismatch", details)
    
    def test_missing_approval_gives_awaiting_confirmation(self):
        """Test that missing H1 approval gives awaiting_confirmation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "04-idea"
            run_dir.mkdir(parents=True)
            
            record = RecordEnvelope(
                "04-idea", "idea_card", "04-idea@1", 1,
                {"test": "data"}
            )
            
            status, details = compute_derived_status(
                "04-idea", record, {}, {}, run_dir.parent
            )
            
            self.assertEqual(status, DerivedStatus.AWAITING_CONFIRMATION)
            self.assertIn("No approvals.json", details)
    
    def test_stale_upstream_propagates(self):
        """Test that stale upstream propagates to downstream."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            r1 = RecordEnvelope("01-problem", "problem_card", "01-problem@1", 1, {"q": "x"})
            r2 = RecordEnvelope("02-evidence", "evidence_card", "02-evidence@1", 1, {"a": []},
                               depends_on={"01-problem": r1.payload_sha256})
            
            # Mark 01 as stale
            upstream_statuses = {
                "01-problem": DerivedStatus.STALE_INPUT
            }
            
            upstream_records = {
                "01-problem": r1
            }
            
            status, details = compute_derived_status(
                "02-evidence", r2, upstream_statuses, upstream_records, run_dir
            )
            
            self.assertEqual(status, DerivedStatus.STALE_DEPENDENCY)
            self.assertIn("01-problem", details)


if __name__ == '__main__':
    unittest.main()
