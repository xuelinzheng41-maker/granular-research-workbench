import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import shortlist


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PerformanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.source = load(ROOT / "examples/performance-brief.json")

    def test_example_carries_anchors_and_refutation_coverage(self):
        result = shortlist.compare(self.source)
        self.assertEqual(result["mode"], "performance")
        for row in result["candidates"]:
            contract = row["performance"]
            self.assertGreaterEqual(len(contract["anchors"]), 2, row["id"])
            for anchor in contract["anchors"]:
                self.assertTrue(anchor["source"].strip(), row["id"])
                self.assertTrue(anchor["why"].strip(), row["id"])
            self.assertGreaterEqual(len(contract["refutation"]["queries"]), 1, row["id"])
            self.assertTrue(all(query.strip() for query in contract["refutation"]["queries"]), row["id"])
            self.assertTrue(contract["refutation"]["coverage"].strip(), row["id"])

    def test_missing_or_short_anchors_are_rejected(self):
        missing = copy.deepcopy(self.source)
        del missing["candidates"][0]["performance"]["anchors"]
        with self.assertRaisesRegex(ValueError, "anchors must be a list"):
            shortlist.compare(missing)

        short = copy.deepcopy(self.source)
        short["candidates"][0]["performance"]["anchors"] = [
            {"source": "VPGBFRS (ASOC 2025), section 3.", "why": "Defines the weighting."}]
        with self.assertRaisesRegex(ValueError, "at least two anchor objects"):
            shortlist.compare(short)

        blank_why = copy.deepcopy(self.source)
        blank_why["candidates"][0]["performance"]["anchors"][1]["why"] = "  "
        with self.assertRaisesRegex(ValueError, "missing or blank why"):
            shortlist.compare(blank_why)

        not_object = copy.deepcopy(self.source)
        not_object["candidates"][0]["performance"]["anchors"][0] = "VPGBFRS (ASOC 2025)"
        with self.assertRaisesRegex(ValueError, "entry must be an object"):
            shortlist.compare(not_object)

    def test_missing_or_empty_refutation_is_rejected(self):
        missing = copy.deepcopy(self.source)
        del missing["candidates"][0]["performance"]["refutation"]
        with self.assertRaisesRegex(ValueError, "refutation must be an object"):
            shortlist.compare(missing)

        empty = copy.deepcopy(self.source)
        empty["candidates"][0]["performance"]["refutation"] = {}
        with self.assertRaisesRegex(ValueError, "queries must be a list"):
            shortlist.compare(empty)

        no_queries = copy.deepcopy(self.source)
        no_queries["candidates"][0]["performance"]["refutation"]["queries"] = []
        with self.assertRaisesRegex(ValueError, "at least one query"):
            shortlist.compare(no_queries)

        blank_query = copy.deepcopy(self.source)
        blank_query["candidates"][0]["performance"]["refutation"]["queries"][0] = " "
        with self.assertRaisesRegex(ValueError, "queries must be a list of non-empty strings"):
            shortlist.compare(blank_query)

        blank_coverage = copy.deepcopy(self.source)
        blank_coverage["candidates"][0]["performance"]["refutation"]["coverage"] = ""
        with self.assertRaisesRegex(ValueError, "missing or blank coverage"):
            shortlist.compare(blank_coverage)

    def test_audit_brief_default_is_unchanged(self):
        result = shortlist.compare(load(ROOT / "examples/brief.json"))
        self.assertEqual(result["mode"], "audit")
        self.assertTrue(all(row["performance"] is None for row in result["candidates"]))
        self.assertEqual(result["eligible_ids"], [])


if __name__ == "__main__":
    unittest.main()
