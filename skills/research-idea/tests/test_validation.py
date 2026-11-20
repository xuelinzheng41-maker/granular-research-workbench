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
