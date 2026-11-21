import hashlib
import json
import sys
import tempfile
from pathlib import Path

import test_launch

sys.path.insert(0, str(test_launch.CLI.parent / "lib"))
from source_evidence import formal, ready


def configuration(card):
    span = "sha256:" + hashlib.sha256(b"mechanism reference").hexdigest()
    axes = ("mechanism", "data", "metric", "setting")
    candidate = dict(card=card.name, body_line=1, span_sha256=span)
    return dict(mode="formal", components=[dict(id="component", **candidate)], scoop={
        "cards": str(card.parent), "queries": {a: [a] for a in axes},
        "judgments": {a: [dict(candidate, overlap="none", reason="different_method")]
                      if a == "mechanism" else [] for a in axes}})


class SourceEvidenceTests(test_launch.LaunchTests):
    def configure_proposal(self, path, card):
        card.write_text("---\ncard_status: handmade\n---\nmechanism reference\n", encoding="utf-8")
        p = json.loads(path.read_bytes())
        p.update(configuration(card))
        path.write_text(json.dumps(p), encoding="utf-8")

    def after_package(self, cli, run):
        packet = json.loads((run / "review-package.json").read_bytes())["packet"]
        self.assertEqual(packet["proposal_mode"], "formal")
        evidence = packet["source_evidence"]
        self.assertEqual(evidence["anchors"][0]["body_line"], 1)
        self.assertEqual(evidence["axes"]["mechanism"]["judgments"][0]["reason"], "different_method")
        self.assertEqual(evidence["axes"]["data"]["status"], "zero_hits")
        self.assertNotIn("mechanism reference", json.dumps(packet))

    def test_source_and_coverage_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "card.md"
            good = "---\ncard_status: handmade\n---\nmechanism reference\n"
            card.write_text(good, encoding="utf-8")
            p = configuration(card)
            ready(formal(root, p["scoop"], p))
            for field, invalid in (("body_line", 9), ("span_sha256", "wrong")):
                item = p["components"][0]
                old = item[field]
                item[field] = invalid
                with self.assertRaises(ValueError):
                    formal(root, p["scoop"], p)
                item[field] = old
            card.write_text(good.replace("handmade", "auto"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "handmade"):
                formal(root, p["scoop"], p)
            card.write_text(good, encoding="utf-8")
            (root / "bad.md").write_text("---\nbroken", encoding="utf-8")
            report = formal(root, p["scoop"], p)
            self.assertEqual(report["axes"]["data"]["status"], "partial_coverage")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                ready(report)
