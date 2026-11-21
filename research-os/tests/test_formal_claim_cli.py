import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_launch import CLI
from test_source_evidence import configuration


class FormalClaimCLI(unittest.TestCase):
    def test_formal_paired_outcomes_and_review_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "card.md"
            card.write_text("---\ncard_status: handmade\n---\nmechanism reference\n", encoding="utf-8")
            for name in ("x", "y"):
                (root / f"{name}.txt").write_text("0\n0\n0\n0\n1\n1\n1\n1\n", encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"root": str(root), "datasets": [dict(id="fixture", status="ready",
                loader="txt_pair", data="x.txt", labels="y.txt")]}), encoding="utf-8")
            arms = {}
            for name, expression in (("a", "test[:, 0]"), ("b", "1 - test[:, 0]")):
                directory = root / name
                directory.mkdir()
                (directory / "method.py").write_text(
                    f"def fit_predict(X, y, test, **kw): return {{'predictions': {expression}}}\n", encoding="utf-8")
                arms[name] = dict(directory=str(directory), budget_s=5)
            claim = dict(component="component", datasets=["fixture"], seeds=[11], support_min=.1, refute_max=-.1)
            payload = dict(configuration(card), idea="Synthetic formal claim fixture", registry=str(registry), prereg=dict(
                hypothesis_claims=[], metric="ACC", datasets=["fixture"], seeds=[11], stage="pilot",
                split={"test_size": .5, "stratify": True}, arms=arms, threshold=.01, compute_budget_minutes=1,
                paired_claims=[dict(claim, id="C1", candidate="a", control="b"),
                               dict(claim, id="C2", candidate="b", control="a"),
                               dict(claim, id="C3", candidate="a", control="b")]))
            source = root / "proposal.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            def cli(command, *args, code=0):
                proc = subprocess.run([sys.executable, "-B", str(CLI), command, str(run), *map(str, args)],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
                return proc.stdout

            cli("init", source)
            cli("scoop")
            cli("approve", "H1", json.loads(cli("proposal"))["proposal_sha256"])
            cli("freeze")
            cli("run")
            cli("review-package")
            target = json.loads(cli("review-target"))
            review = dict(binding=target, reviewer=dict(id="fixture-model", type="independent_model", independent=True,
                          model_route="synthetic", team_task="fixture", team_attempt="fixture"), verdict="pass",
                          rationale="Synthetic case", accepted_claims=["C1"])
            review_input = root / "review-input.json"
            review_input.write_text(json.dumps(dict(review, binding=dict(target, results_sha256="wrong"))), encoding="utf-8")
            cli("review", review_input, code=2)
            review_input.write_text(json.dumps(review), encoding="utf-8")
            cli("review", review_input)
            cli("decide")
            cli("passport")
            self.assertEqual(json.loads(cli("verify"))["state"], "archived")
            decision = json.loads((run / "decision.json").read_bytes())
            self.assertEqual({key: value["status"] for key, value in decision["scientific_claims"].items()},
                             {"C1": "supported", "C2": "refuted", "C3": "unknown"})
            (run / "review.json").write_text(json.dumps(dict(review, accepted_claims=["C3"])), encoding="utf-8")
            self.assertEqual(json.loads(cli("verify", code=2))["state"], "corrupt")
