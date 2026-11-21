"""Unit tests for components_gate.py (3 required tests per captain strategy)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from components_gate import run_gate, _locator_ok


def _make_raw(components, auto_cards=None):
    return {
        "schema_version": 1, "kind": "components_raw",
        "components": components,
        "auto_cards_registered": auto_cards or [],
        "kb_snapshot_sha256": "sha256:test",
    }


def _make_index(cards):
    return {"schema_version": 1, "cards": cards}


class TestAutoCardRejected(unittest.TestCase):
    """(a) Auto-inferred card components and auto_cards_registered are all rejected."""

    def test_auto_card_component_rejected(self):
        """A component from a 自动推断 card must be rejected."""
        raw = _make_raw([
            {
                "id": "auto-1", "card_id": "AutoCard",
                "card_status": "自动推断",
                "locator": "p.2",
                "mechanism": "some mechanism",
                "span_sha256": "sha256:abc",
            }
        ])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "raw.json").write_text(json.dumps(raw), encoding="utf-8")
            (d / "idx.json").write_text(json.dumps(_make_index([])), encoding="utf-8")
            stats = run_gate(d / "raw.json", d / "idx.json", d / "out")
        self.assertEqual(stats["passed"], 0)
        self.assertGreater(stats["by_rule"]["R1_auto_card"], 0)

    def test_auto_cards_registered_counted(self):
        """68 auto cards in auto_cards_registered appear in rejected stats."""
        auto_entries = [{"card_id": f"Auto{i}", "status": "自动推断"} for i in range(5)]
        raw = _make_raw([], auto_cards=auto_entries)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "raw.json").write_text(json.dumps(raw), encoding="utf-8")
            (d / "idx.json").write_text(json.dumps(_make_index([])), encoding="utf-8")
            stats = run_gate(d / "raw.json", d / "idx.json", d / "out")
        self.assertEqual(stats["by_rule"]["R1_auto_card"], 5)


class TestLocatorPass(unittest.TestCase):
    """(b) Valid locator from 手工九块 card passes."""

    def test_valid_locator_passes(self):
        """A 手工九块 component with p.2 locator should pass all rules."""
        card = {
            "card_id": "GoodCard",
            "front_matter": {"status": "手工九块"},
            "blocks": [
                {"n": 1, "text_chars": 100, "key": "文章脉络"},
                {"n": 2, "text_chars": 200, "key": "核心思想"},
                {"n": 3, "text_chars": 500, "key": "方法骨架"},
            ],
        }
        comp = {
            "id": "good-1", "card_id": "GoodCard",
            "card_status": "手工九块",
            "locator": "p.2",
            "mechanism": "Ball generation using purity threshold",
            "paper": "Test Paper",
            "span_sha256": "sha256:abc123",
        }
        raw = _make_raw([comp])
        import shutil
        d = Path(tempfile.mkdtemp())
        try:
            (d / "raw.json").write_text(json.dumps(raw), encoding="utf-8")
            (d / "idx.json").write_text(json.dumps(_make_index([card])), encoding="utf-8")
            stats = run_gate(d / "raw.json", d / "idx.json", d / "out")
            self.assertGreaterEqual(stats["passed"], 1)
            lib = json.loads((d / "out" / "library.json").read_text(encoding="utf-8"))
            self.assertTrue(lib["components"][0].get("span_sha256", "").startswith("sha256:"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestFakeLocatorExit2(unittest.TestCase):
    """(c) Fake locator p.999 triggers exit 2."""

    def test_fake_locator_exits(self):
        """p.999 must trigger sys.exit(2)."""
        import shutil
        card = {
            "card_id": "FakeCard",
            "front_matter": {"status": "手工九块"},
            "blocks": [
                {"n": 3, "text_chars": 500, "key": "方法骨架"},
            ],
        }
        comp = {
            "id": "fake-1", "card_id": "FakeCard",
            "card_status": "手工九块",
            "locator": "p.99999",
            "mechanism": "some mechanism",
            "span_sha256": "sha256:abc",
        }
        raw = _make_raw([comp])
        d = Path(tempfile.mkdtemp())
        try:
            (d / "raw.json").write_text(json.dumps(raw), encoding="utf-8")
            (d / "idx.json").write_text(json.dumps(_make_index([card])), encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                run_gate(d / "raw.json", d / "idx.json", d / "out")
            self.assertEqual(ctx.exception.code, 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
