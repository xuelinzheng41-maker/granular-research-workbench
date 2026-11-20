import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import shortlist


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ShortlistTests(unittest.TestCase):
    def test_accepts_empty_shortlist_and_retains_reported_limits(self):
        source = load(ROOT / "examples/brief.json")
        self.assertEqual(shortlist.compare(source)["eligible_ids"], [])
        ready = source["candidates"][1]
        ready["prior_status"] = "no_overlap_retrieved"
        self.assertEqual(shortlist.compare(source)["eligible_ids"], ["budget-dedup"])
        for change in ({"minutes_this_week": 19}, {"skills": []}, {"resources": []}):
            modified = copy.deepcopy(source)
            modified["profile"].update(change)
            self.assertEqual(shortlist.compare(modified)["eligible_ids"], [], change)

    def test_accepts_more_than_three_candidates(self):
        source = load(ROOT / "examples/brief.json")
        for suffix in ("a", "b"):
            extra = copy.deepcopy(source["candidates"][0])
            extra.update(id=f"extra-candidate-{suffix}", source_kind="transfer", prior_status="unsearched")
            source["candidates"].append(extra)
        result = shortlist.compare(source)
        self.assertEqual(len(result["candidates"]), 4)
        self.assertIn("extra-candidate-a", [row["id"] for row in result["candidates"]])

    def test_performance_brief_requires_a_complete_contract(self):
        source = load(ROOT / "examples/performance-brief.json")
        result = shortlist.compare(source)
        self.assertEqual(result["mode"], "performance")
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["candidates"][0]["performance"]["base_methods"],
                         ["3W-GBSVM++", "VPGBFRS"])
        broken = copy.deepcopy(source)
        del broken["candidates"][0]["performance"]["baselines"]
        with self.assertRaisesRegex(ValueError, "baselines"):
            shortlist.compare(broken)
        missing = copy.deepcopy(source)
        del missing["candidates"][0]["performance"]
        with self.assertRaisesRegex(ValueError, "performance mode requires"):
            shortlist.compare(missing)

    def test_performance_contract_records_component_sources_and_rejected_pairs(self):
        source = load(ROOT / "examples/performance-brief.json")
        result = shortlist.compare(source)
        for row in result["candidates"]:
            contract = row["performance"]
            self.assertEqual(sorted(contract["component_sources"]), contract["components"], row["id"])
            for name, origin in contract["component_sources"].items():
                self.assertTrue(origin.strip(), name)
            self.assertGreaterEqual(len(contract["rejected_pairs"]), 2, row["id"])
            for rejected in contract["rejected_pairs"]:
                self.assertTrue(rejected["pair"].strip() and rejected["reason"].strip(), row["id"])
        self.assertEqual(result["candidates"][0]["performance"]["component_sources"],
                         {"three-way reject threshold": "3W-GBSVM++ (ASOC 2026): three-way decision head "
                                                       "with a calibrated reject band, read from the local paper snapshot.",
                          "variable-precision fuzzy rough weighting": "VPGBFRS (ASOC 2025): variable-precision "
                                                                    "fuzzy rough dependency weights, read from the "
                                                                    "local paper snapshot."})

    def test_performance_contract_requires_a_source_for_every_component(self):
        source = load(ROOT / "examples/performance-brief.json")
        missing = copy.deepcopy(source)
        del missing["candidates"][0]["performance"]["component_sources"]
        with self.assertRaisesRegex(ValueError, "component_sources must be an object"):
            shortlist.compare(missing)
        partial = copy.deepcopy(source)
        partial["candidates"][0]["performance"]["component_sources"].pop("three-way reject threshold")
        with self.assertRaisesRegex(ValueError, "must cover every component"):
            shortlist.compare(partial)
        blank = copy.deepcopy(source)
        blank["candidates"][0]["performance"]["component_sources"]["three-way reject threshold"] = "   "
        with self.assertRaisesRegex(ValueError, "must be a non-empty string"):
            shortlist.compare(blank)
        typo = copy.deepcopy(source)
        typo["candidates"][0]["performance"]["component_sources"]["three-way reject thresold"] = "paper"
        with self.assertRaisesRegex(ValueError, "undeclared component"):
            shortlist.compare(typo)

    def test_performance_contract_requires_two_rejected_pairs(self):
        source = load(ROOT / "examples/performance-brief.json")
        missing = copy.deepcopy(source)
        del missing["candidates"][0]["performance"]["rejected_pairs"]
        with self.assertRaisesRegex(ValueError, "rejected_pairs must be a list"):
            shortlist.compare(missing)
        single = copy.deepcopy(source)
        single["candidates"][0]["performance"]["rejected_pairs"] = [
            {"pair": "score concatenation", "reason": "no new decision rule"}]
        with self.assertRaisesRegex(ValueError, "at least two rejected combinations"):
            shortlist.compare(single)
        blank_reason = copy.deepcopy(source)
        blank_reason["candidates"][0]["performance"]["rejected_pairs"][1]["reason"] = ""
        with self.assertRaisesRegex(ValueError, "missing or blank reason"):
            shortlist.compare(blank_reason)
        malformed = copy.deepcopy(source)
        malformed["candidates"][0]["performance"]["rejected_pairs"][0] = "score concatenation"
        with self.assertRaisesRegex(ValueError, "must be an object"):
            shortlist.compare(malformed)

    def test_audit_mode_still_ignores_the_performance_contract(self):
        source = load(ROOT / "examples/brief.json")
        self.assertNotIn("mode", source)
        self.assertTrue(all("performance" not in item for item in source["candidates"]))
        result = shortlist.compare(source)
        self.assertEqual(result["mode"], "audit")
        self.assertTrue(all(row["performance"] is None for row in result["candidates"]))

    def test_rejects_malformed_or_single_source_briefs(self):
        source = load(ROOT / "examples/brief.json")
        source["candidates"][1]["source_kind"] = source["candidates"][0]["source_kind"]
        with self.assertRaisesRegex(ValueError, "at least two source kinds"):
            shortlist.compare(source)
        source["candidates"][0]["probe_minutes"] = True
        with self.assertRaisesRegex(ValueError, "probe_minutes"):
            shortlist.compare(source)


class ReplayTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-S", str(ROOT / "scripts/replay.py"), *map(str, args)],
                              text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)

    def test_reference_replay_and_stale_review_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "trial"
            verdicts = Path(tmp) / "verdicts.json"
            r = self.cli("prepare", root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.cli("prepare", root).returncode, 2)
            packet = load(root / "review-packet.json")
            for case in packet.values():
                self.assertEqual(set(case), {"plan", "raw_input", "computed_readout", "review_input_sha256"})
            self.assertEqual(packet["case-a"]["computed_readout"]["A"]["diameter"], 5)
            self.assertEqual(packet["case-a"]["computed_readout"]["B"]["diameter"], 4)
            self.assertEqual(packet["case-b"]["computed_readout"]["shared_key"]["baseline"]["distinct_true_count"], 3)
            self.assertEqual(packet["case-b"]["computed_readout"]["shared_key"]["dedup"]["distinct_true_count"], 1)
            reviews = load(ROOT / "examples/reference-review.json")
            for case, row in reviews.items():
                row.update(reviewer="reference mechanics test",
                           reviewer_type="human" if case == "case-a" else "ai_agent",
                           author_result_exposure="none" if case == "case-a" else "seen",
                           review_input_sha256=packet[case]["review_input_sha256"])
            verdicts.write_text(json.dumps(reviews), encoding="utf-8")
            target, = root.glob("*-case-d/readout.json")
            original = target.read_bytes()
            target.write_bytes(original + b"\n")
            r = self.cli("finish", root, verdicts)
            self.assertEqual(r.returncode, 2)
            self.assertIn("digest does not match", r.stderr)
            self.assertEqual(list(root.glob("*/idea.md")), [])
            target.write_bytes(original)
            r = self.cli("finish", root, verdicts)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual({r["case"] for r in load(root / "replay-report.json") if r["formal_files"]},
                             {"case-a", "case-d"})
            for case in packet:
                folder, = root.glob(f"*-{case}")
                record = load(folder / "probe-review.json")
                expected = {"case-a": ("human", "none")}.get(case, ("ai_agent", "seen"))
                self.assertEqual((record["reviewer_type"], record["author_result_exposure"]), expected)


if __name__ == "__main__":
    unittest.main()
