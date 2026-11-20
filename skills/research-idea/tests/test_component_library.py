import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import component_library

EXAMPLE = ROOT / "examples/component-library.json"
SCRIPT = ROOT / "scripts/component_library.py"


def example():
    return copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))


class ComponentLibraryTests(unittest.TestCase):
    def test_example_is_valid(self):
        summary = component_library.validate(example())
        self.assertEqual(summary["component_count"], 2)
        self.assertEqual(
            summary["ids"],
            ["granular-ball-cover", "ball-level-evidence-accumulation"],
        )
        self.assertEqual(summary["checks"]["form"], "ok")
        self.assertEqual(summary["components"][0]["paper"], "GBCRS (IJAR 2025)")

    def test_missing_field_is_rejected(self):
        source = example()
        del source["components"][0]["bottleneck"]
        with self.assertRaisesRegex(ValueError, "bottleneck"):
            component_library.validate(source)

    def test_duplicate_id_is_rejected(self):
        source = example()
        source["components"][1]["id"] = source["components"][0]["id"]
        with self.assertRaisesRegex(ValueError, "duplicate component id"):
            component_library.validate(source)

    def test_blank_source_is_rejected(self):
        source = example()
        source["components"][0]["source"] = "   "
        with self.assertRaisesRegex(ValueError, "source: missing or blank"):
            component_library.validate(source)

    def test_source_needs_a_line_or_page_locator(self):
        source = example()
        source["components"][0]["source"] = "paper: GBCRS (IJAR 2025); card GBCRS-2025"
        with self.assertRaisesRegex(ValueError, "line or page locator"):
            component_library.validate(source)

    def test_source_needs_a_card_or_paper(self):
        source = example()
        source["components"][0]["source"] = "GBCRS, p. 4, lines 118-146"
        with self.assertRaisesRegex(ValueError, "card or paper"):
            component_library.validate(source)

    def test_source_may_name_the_paper_value_directly(self):
        source = example()
        source["components"][0]["source"] = "GBCRS (IJAR 2025), p. 4, lines 118-146."
        self.assertEqual(component_library.validate(source)["component_count"], 2)

    def test_two_components_are_required(self):
        source = example()
        source["components"] = source["components"][:1]
        with self.assertRaisesRegex(ValueError, "at least 2 components"):
            component_library.validate(source)

    def test_cli_exit_codes(self):
        ok = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(EXAMPLE)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["component_count"], 2)

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            source = example()
            source["components"][0]["source"] = ""
            bad.write_text(json.dumps(source), encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(bad)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
            )
            self.assertEqual(broken.returncode, 2)
            self.assertIn("source", broken.stderr)


if __name__ == "__main__":
    unittest.main()
