"""
Unit tests for research-os/lib/compile.py

Tests prereg → protocol compilation and conflict detection.
"""

import unittest
import tempfile
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from compile import (
    CompileError,
    extract_prereg_values,
    check_manifest_conflicts,
    check_pilot_conflicts,
    compile_protocol,
    compile_prereg_to_protocol
)
from records import RecordEnvelope


class TestExtractPreregValues(unittest.TestCase):
    """Test extracting values from prereg."""
    
    def test_extract_complete_prereg(self):
        """Test extracting all required fields."""
        prereg_payload = {
            "hypothesis_claims": ["C1"],
            "metric": {"name": "ACC"},
            "datasets": ["DS1", "DS2"],
            "seeds": [11, 29, 47],
            "stage": "pilot",
            "split": {"kind": "holdout", "test_size": 0.3},
            "arms": {"candidate": "hybrid", "base": ["baseline"]},
            "threshold": 0.01
        }
        
        prereg_record = {
            "payload": prereg_payload,
            "payload_sha256": "sha256:test123"
        }
        
        values = extract_prereg_values(prereg_record)
        
        self.assertEqual(values["threshold"], 0.01)
        self.assertEqual(values["seeds"], [11, 29, 47])
        self.assertEqual(values["datasets"], ["DS1", "DS2"])
    
    def test_extract_missing_required_field(self):
        """Test error on missing required field."""
        prereg_payload = {
            "metric": {"name": "ACC"},
            "datasets": ["DS1"],
            # Missing seeds, threshold, etc.
        }
        
        prereg_record = {"payload": prereg_payload}
        
        with self.assertRaises(CompileError) as ctx:
            extract_prereg_values(prereg_record)
        
        self.assertIn("Missing required fields", str(ctx.exception))


class TestManifestConflicts(unittest.TestCase):
    """Test manifest conflict detection."""
    
    def test_no_conflicts_with_hash_reference(self):
        """Test manifest with only prereg_sha256."""
        manifest = {
            "prereg_sha256": "sha256:abc123"
        }
        
        prereg_values = {
            "threshold": 0.01,
            "seeds": [11, 29]
        }
        
        conflicts = check_manifest_conflicts(manifest, prereg_values, "sha256:abc123")
        
        self.assertEqual(len(conflicts), 0)
    
    def test_conflict_wrong_threshold(self):
        """Test conflict when manifest has different threshold."""
        manifest = {
            "prereg_sha256": "sha256:abc123",
            "threshold": 0.05  # Conflicts with prereg
        }
        
        prereg_values = {
            "threshold": 0.01,
            "seeds": [11, 29]
        }
        
        conflicts = check_manifest_conflicts(manifest, prereg_values, "sha256:abc123")
        
        self.assertGreater(len(conflicts), 0)
        self.assertTrue(any("threshold" in c for c in conflicts))
    
    def test_conflict_wrong_prereg_hash(self):
        """Test conflict when manifest has wrong prereg_sha256."""
        manifest = {
            "prereg_sha256": "sha256:wrong_hash"
        }
        
        prereg_values = {"threshold": 0.01}
        
        conflicts = check_manifest_conflicts(manifest, prereg_values, "sha256:correct_hash")
        
        self.assertGreater(len(conflicts), 0)
        self.assertTrue(any("mismatch" in c for c in conflicts))
    
    def test_conflict_missing_prereg_hash(self):
        """Test conflict when manifest missing prereg_sha256."""
        manifest = {
            "threshold": 0.01
        }
        
        prereg_values = {"threshold": 0.01}
        
        conflicts = check_manifest_conflicts(manifest, prereg_values, "sha256:test")
        
        self.assertGreater(len(conflicts), 0)
        self.assertTrue(any("missing prereg_sha256" in c for c in conflicts))


class TestPilotConflicts(unittest.TestCase):
    """Test pilot conflict detection."""
    
    def test_no_conflicts_with_matching_values(self):
        """Test pilot with matching prereg reference."""
        pilot_payload = {
            "prereg_sha256": "sha256:abc123"
        }
        
        prereg_values = {
            "threshold": 0.01,
            "datasets": ["DS1"]
        }
        
        conflicts = check_pilot_conflicts(pilot_payload, prereg_values, "sha256:abc123")
        
        self.assertEqual(len(conflicts), 0)
    
    def test_conflict_different_datasets(self):
        """Test conflict when pilot has different datasets."""
        pilot_payload = {
            "prereg_sha256": "sha256:abc123",
            "datasets": ["DS1", "DS2", "DS3"]  # More than prereg
        }
        
        prereg_values = {
            "datasets": ["DS1", "DS2"]
        }
        
        conflicts = check_pilot_conflicts(pilot_payload, prereg_values, "sha256:abc123")
        
        self.assertGreater(len(conflicts), 0)
        self.assertTrue(any("datasets" in c for c in conflicts))
    
    def test_conflict_different_seeds(self):
        """Test conflict when pilot has different seeds."""
        pilot_payload = {
            "seeds": [11, 29, 47, 53]  # Extra seed
        }
        
        prereg_values = {
            "seeds": [11, 29, 47]
        }
        
        conflicts = check_pilot_conflicts(pilot_payload, prereg_values, "sha256:test")
        
        self.assertGreater(len(conflicts), 0)
        self.assertTrue(any("seeds" in c for c in conflicts))


class TestCompileProtocol(unittest.TestCase):
    """Test protocol compilation."""
    
    def test_compile_basic_protocol(self):
        """Test compiling basic protocol."""
        prereg_payload = {
            "hypothesis_claims": ["C1"],
            "metric": {"name": "ACC", "direction": "max"},
            "datasets": ["DS1", "DS2"],
            "seeds": [11, 29, 47],
            "stage": "pilot",
            "split": {"kind": "holdout", "test_size": 0.3},
            "arms": {"candidate": "hybrid"},
            "threshold": 0.01
        }
        
        prereg_record = {
            "payload": prereg_payload,
            "payload_sha256": "sha256:test_hash"
        }
        
        protocol = compile_protocol(prereg_record, "sha256:test_hash")
        
        self.assertEqual(protocol["schema_version"], 1)
        self.assertEqual(protocol["source"], "06-prereg")
        self.assertEqual(protocol["prereg_sha256"], "sha256:test_hash")
        self.assertEqual(protocol["threshold"], 0.01)
        self.assertEqual(protocol["seeds"], [11, 29, 47])
        self.assertEqual(protocol["datasets"], ["DS1", "DS2"])
    
    def test_compile_with_manifest_conflict(self):
        """Test compilation fails with manifest conflict."""
        prereg_payload = {
            "hypothesis_claims": ["C1"],
            "metric": {"name": "ACC"},
            "datasets": ["DS1"],
            "seeds": [11],
            "stage": "pilot",
            "split": {},
            "arms": {},
            "threshold": 0.01
        }
        
        prereg_record = {
            "payload": prereg_payload,
            "payload_sha256": "sha256:test"
        }
        
        manifest = {
            "prereg_sha256": "sha256:test",
            "threshold": 0.05  # Conflict!
        }
        
        with self.assertRaises(CompileError) as ctx:
            compile_protocol(prereg_record, "sha256:test", manifest=manifest)
        
        self.assertIn("Compilation conflicts", str(ctx.exception))
        self.assertIn("threshold", str(ctx.exception))


class TestEndToEnd(unittest.TestCase):
    """Test end-to-end compilation."""
    
    def test_compile_to_file(self):
        """Test compiling prereg to protocol file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create prereg record
            prereg_payload = {
                "hypothesis_claims": ["C1", "C2"],
                "metric": {"name": "ACC", "direction": "max"},
                "datasets": ["Waveform", "S3"],
                "seeds": [11, 29, 47],
                "stage": "pilot",
                "split": {"kind": "holdout", "test_size": 0.3},
                "arms": {"candidate": "hybrid", "base": ["baseline"]},
                "threshold": 0.01,
                "min_datasets": 2
            }
            
            prereg_record = RecordEnvelope(
                stage="06-prereg",
                kind="prereg",
                record_id="06-prereg@1",
                attempt=1,
                payload=prereg_payload
            )
            
            prereg_path = tmpdir / "prereg_record.json"
            prereg_record.save(prereg_path)
            
            # Compile
            protocol_path = tmpdir / "protocol.json"
            success, error = compile_prereg_to_protocol(prereg_path, protocol_path)
            
            self.assertTrue(success, f"Compilation failed: {error}")
            self.assertTrue(protocol_path.exists())
            
            # Load and verify protocol
            with open(protocol_path, 'r', encoding='utf-8') as f:
                protocol = json.load(f)
            
            self.assertEqual(protocol["threshold"], 0.01)
            self.assertEqual(protocol["datasets"], ["Waveform", "S3"])
            self.assertEqual(protocol["seeds"], [11, 29, 47])
            self.assertEqual(protocol["prereg_sha256"], prereg_record.payload_sha256)


if __name__ == '__main__':
    unittest.main()
