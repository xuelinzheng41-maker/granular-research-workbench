import sys
import unittest

from test_launch import CLI

sys.path.insert(0, str(CLI.parent / "lib"))
from pilot_claims import assess
from review_decision import decision


class ClaimChecks(unittest.TestCase):
    def test_pairing_refutation_and_review(self):
        claim = dict(id="C1", component="X", datasets=["d"], seeds=[1], candidate="a", control="b",
                     support_min=.1, refute_max=-.1)
        p = dict(mode="formal", components=[dict(id="X")], prereg=dict(stage="pilot", datasets=["d"],
                 seeds=[1], arms={"a": {}, "b": {}}, paired_claims=[claim]))
        key = ("d", "b", 1)
        rows = {("d", "a", 1): dict(status="ok", metric=.8, split_sha256="split"),
                key: dict(status="ok", metric=.5, split_sha256="split")}
        binding = dict(packet_sha256="expected")
        review = dict(binding=binding, reviewer=dict(id="fixture", type="independent_model", independent=True,
                      model_route="fixture-model", team_task="fixture-task", team_attempt="fixture-attempt"),
                      verdict="pass", rationale="Synthetic verification")

        def gates():
            return assess(p, rows, {"d": 1}, {"a": 1, "b": 2}, {"X": {"body_line": 1}})

        def status(**fields):
            return decision(dict(review, **fields), binding, gates())["scientific_claims"]["C1"]["status"]

        self.assertEqual(status(), "unknown")
        self.assertEqual(status(accepted_claims=["C1"]), "supported")
        with self.assertRaises(ValueError):
            status(binding=dict(packet_sha256="wrong"))
        rows[key]["metric"] = 1.0
        self.assertEqual(status(verdict="reject"), "refuted")
        rows[key]["split_sha256"] = "different"
        self.assertEqual(status(), "unknown")
        del rows[key]
        self.assertEqual(status(), "unknown")
        p["mode"] = "exploratory"
        self.assertFalse(gates())
