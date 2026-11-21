"""
Unit tests for research-os/lib/records.py

Tests:
1. Canonical JSON serialization
2. SHA256 hashing
3. Payload SHA256 computation
4. Envelope creation and serialization
5. Envelope save/load
6. Payload SHA256 verification
7. Dependency chain verification
8. Input hash verification
"""

import unittest
import tempfile
import json
from pathlib import Path
import sys

# Add parent lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from records import (
    canonical_json,
    sha256_canonical,
    compute_payload_sha256,
    RecordEnvelope,
    verify_dependency_chain,
    verify_input_hash
)


class TestCanonicalJSON(unittest.TestCase):
    """Test canonical JSON serialization."""
    
    def test_canonical_json_basic(self):
        """Test basic canonical JSON output."""
        obj = {"b": 2, "a": 1}
        result = canonical_json(obj)
        
        # Should be sorted
        self.assertIn('"a"', result)
        self.assertIn('"b"', result)
        self.assertTrue(result.index('"a"') < result.index('"b"'))
    
    def test_canonical_json_unicode(self):
        """Test that Unicode is preserved (ensure_ascii=False)."""
        obj = {"name": "测试"}
        result = canonical_json(obj)
        
        # Should contain actual Unicode, not escaped
        self.assertIn('测试', result)
        self.assertNotIn('\\u', result)
    
    def test_canonical_json_nested(self):
        """Test nested objects."""
        obj = {
            "outer": {
                "z": 3,
                "a": 1
            },
            "list": [3, 2, 1]
        }
        result = canonical_json(obj)
        
        # Should sort keys at all levels
        self.assertIn('"a"', result)
        self.assertIn('"z"', result)
    
    def test_canonical_json_deterministic(self):
        """Test that serialization is deterministic."""
        obj = {"z": 3, "a": 1, "m": 2}
        result1 = canonical_json(obj)
        result2 = canonical_json(obj)
        
        self.assertEqual(result1, result2)


class TestSHA256(unittest.TestCase):
    """Test SHA256 hashing."""
    
    def test_sha256_canonical_basic(self):
        """Test basic SHA256 computation."""
        obj = {"a": 1}
        result = sha256_canonical(obj)
        
        # Should start with "sha256:"
        self.assertTrue(result.startswith("sha256:"))
        
        # Should be deterministic
        result2 = sha256_canonical(obj)
        self.assertEqual(result, result2)
    
    def test_sha256_canonical_different_order(self):
        """Test that different key order produces same hash."""
        obj1 = {"a": 1, "b": 2}
        obj2 = {"b": 2, "a": 1}
        
        hash1 = sha256_canonical(obj1)
        hash2 = sha256_canonical(obj2)
        
        # Should be identical due to canonical ordering
        self.assertEqual(hash1, hash2)
    
    def test_sha256_canonical_different_content(self):
        """Test that different content produces different hash."""
        obj1 = {"a": 1}
        obj2 = {"a": 2}
        
        hash1 = sha256_canonical(obj1)
        hash2 = sha256_canonical(obj2)
        
        self.assertNotEqual(hash1, hash2)


class TestPayloadSHA256(unittest.TestCase):
    """Test payload SHA256 computation."""
    
    def test_compute_payload_sha256_basic(self):
        """Test basic payload hash."""
        payload = {"data": "test"}
        result = compute_payload_sha256(payload)
        
        self.assertTrue(result.startswith("sha256:"))
    
    def test_compute_payload_sha256_with_depends(self):
        """Test payload hash with dependencies."""
        payload = {"data": "test"}
        depends_on = {"01-problem": "sha256:abc123"}
        
        result = compute_payload_sha256(payload, depends_on=depends_on)
        
        self.assertTrue(result.startswith("sha256:"))
    
    def test_compute_payload_sha256_with_inputs(self):
        """Test payload hash with inputs."""
        payload = {"data": "test"}
        inputs = {"kb_index": "sha256:def456"}
        
        result = compute_payload_sha256(payload, inputs=inputs)
        
        self.assertTrue(result.startswith("sha256:"))
    
    def test_compute_payload_sha256_deterministic(self):
        """Test that hash is deterministic."""
        payload = {"z": 3, "a": 1}
        depends_on = {"stage1": "sha256:abc"}
        inputs = {"input1": "sha256:def"}
        
        result1 = compute_payload_sha256(payload, depends_on, inputs)
        result2 = compute_payload_sha256(payload, depends_on, inputs)
        
        self.assertEqual(result1, result2)


class TestRecordEnvelope(unittest.TestCase):
    """Test RecordEnvelope class."""
    
    def test_envelope_creation(self):
        """Test creating an envelope."""
        payload = {"test": "data"}
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload
        )
        
        self.assertEqual(envelope.schema_version, 2)
        self.assertEqual(envelope.stage, "01-problem")
        self.assertEqual(envelope.kind, "problem_card")
        self.assertEqual(envelope.attempt, 1)
        self.assertTrue(envelope.payload_sha256.startswith("sha256:"))
    
    def test_envelope_with_dependencies(self):
        """Test envelope with dependencies."""
        payload = {"test": "data"}
        depends_on = {"00-constraints": "sha256:abc123"}
        
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload,
            depends_on=depends_on
        )
        
        self.assertEqual(envelope.depends_on, depends_on)
    
    def test_envelope_to_dict(self):
        """Test converting envelope to dict."""
        payload = {"test": "data"}
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload
        )
        
        d = envelope.to_dict()
        
        self.assertEqual(d["schema_version"], 2)
        self.assertEqual(d["stage"], "01-problem")
        self.assertIn("created_at", d)
        self.assertIn("produced_by", d)
        self.assertIn("payload_sha256", d)
    
    def test_envelope_canonical_json(self):
        """Test canonical JSON serialization of envelope."""
        payload = {"z": 3, "a": 1}
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload
        )
        
        json_str = envelope.to_canonical_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed["stage"], "01-problem")
        
        # Should be sorted
        self.assertTrue(json_str.index('"a"') < json_str.index('"z"'))


class TestEnvelopeSaveLoad(unittest.TestCase):
    """Test envelope save/load functionality."""
    
    def test_save_and_load(self):
        """Test saving and loading an envelope."""
        payload = {"data": "test", "value": 42}
        depends_on = {"00-constraints": "sha256:abc123"}
        
        original = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload,
            depends_on=depends_on
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stage" / "record.json"
            
            # Save
            original.save(path)
            self.assertTrue(path.exists())
            
            # Load
            loaded = RecordEnvelope.load(path)
            
            # Verify fields
            self.assertEqual(loaded.stage, original.stage)
            self.assertEqual(loaded.kind, original.kind)
            self.assertEqual(loaded.record_id, original.record_id)
            self.assertEqual(loaded.attempt, original.attempt)
            self.assertEqual(loaded.payload, original.payload)
            self.assertEqual(loaded.depends_on, original.depends_on)
            self.assertEqual(loaded.payload_sha256, original.payload_sha256)
    
    def test_verify_payload_sha256_valid(self):
        """Test verifying valid payload_sha256."""
        payload = {"data": "test"}
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload
        )
        
        self.assertTrue(envelope.verify_payload_sha256())
    
    def test_verify_payload_sha256_tampered(self):
        """Test detecting tampered payload."""
        payload = {"data": "test"}
        envelope = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=payload
        )
        
        # Tamper with payload
        envelope.payload["data"] = "modified"
        
        # Should detect mismatch
        self.assertFalse(envelope.verify_payload_sha256())


class TestDependencyChain(unittest.TestCase):
    """Test dependency chain verification."""
    
    def test_verify_dependency_chain_ok(self):
        """Test verifying valid dependency chain."""
        # Create upstream record
        upstream_payload = {"data": "upstream"}
        upstream = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=upstream_payload
        )
        
        # Create downstream record that depends on upstream
        downstream_payload = {"data": "downstream"}
        downstream = RecordEnvelope(
            stage="02-evidence",
            kind="evidence_card",
            record_id="02-evidence@1",
            attempt=1,
            payload=downstream_payload,
            depends_on={"01-problem": upstream.payload_sha256}
        )
        
        # Verify chain
        stale = verify_dependency_chain(
            downstream,
            {"01-problem": upstream}
        )
        
        self.assertFalse(stale["01-problem"])
    
    def test_verify_dependency_chain_stale(self):
        """Test detecting stale dependency."""
        # Create original upstream
        upstream_payload_v1 = {"data": "version1"}
        upstream_v1 = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@1",
            attempt=1,
            payload=upstream_payload_v1
        )
        
        # Downstream depends on v1
        downstream_payload = {"data": "downstream"}
        downstream = RecordEnvelope(
            stage="02-evidence",
            kind="evidence_card",
            record_id="02-evidence@1",
            attempt=1,
            payload=downstream_payload,
            depends_on={"01-problem": upstream_v1.payload_sha256}
        )
        
        # Upstream is modified (new attempt)
        upstream_payload_v2 = {"data": "version2"}
        upstream_v2 = RecordEnvelope(
            stage="01-problem",
            kind="problem_card",
            record_id="01-problem@2",
            attempt=2,
            payload=upstream_payload_v2
        )
        
        # Verify chain - should detect stale
        stale = verify_dependency_chain(
            downstream,
            {"01-problem": upstream_v2}
        )
        
        self.assertTrue(stale["01-problem"])


if __name__ == '__main__':
    unittest.main()
