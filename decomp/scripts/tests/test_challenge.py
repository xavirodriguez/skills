from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge import evaluate, percentile75


class UnifiedChallengeTests(unittest.TestCase):
    def test_p75_is_explicit_linear_interpolation(self) -> None:
        self.assertEqual(percentile75([100, 200, 300, 400]), 325.0)

    def test_tier2_uses_only_zero_match_and_p75_population(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "u", "functions": [
                    {"name": "A", "size": 256, "address": "0x1000"},
                    {"name": "B", "size": 300, "address": "0x1100"},
                    {"name": "C", "size": 400, "address": "0x1200"},
                    {"name": "P", "size": 900, "address": "0x1300", "fuzzy_match_percent": 50},
                    {"name": "M", "size": 1000, "address": "0x1400", "fuzzy_match_percent": 100},
                ]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "A", "entry": "0x1000", "has_branch": True, "blocks": 3},
                {"name": "B", "entry": "0x1100", "has_branch": True, "blocks": 3},
                {"name": "C", "entry": "0x1200", "has_loop": True, "blocks": 6},
            ]
        }
        result = evaluate(report, scout)
        self.assertEqual(result["summary"]["p75_bytes"], 350.0)
        self.assertEqual([x["name"] for x in result["tier2"]["candidates"]], ["C"])

    def test_partial_match_is_never_classified_as_zero_match(self) -> None:
        report = {
            "version": 2,
            "units": [{
                "name": "u",
                "functions": [
                    {"name": "Partial", "size": 900, "address": "0x2000", "fuzzy_match_percent": 1},
                    {"name": "Zero", "size": 900, "address": "0x2100"},
                ],
            }],
        }
        scout = {
            "candidates": [{
                "name": "Zero",
                "entry": "0x2100",
                "has_loop": True,
                "blocks": 5,
            }]
        }
        result = evaluate(report, scout)
        self.assertEqual(result["summary"]["undecompiled_functions"], 1)
        self.assertEqual(result["tier2"]["candidates"][0]["match_kind"], "zero_match_no_source")

    def test_logic_and_success_scores_are_exposed(self) -> None:
        report = {
            "version": 2,
            "units": [{
                "name": "u",
                "functions": [{
                    "name": "UpdateEnemy",
                    "size": 1200,
                    "address": "0x3000",
                }],
            }],
        }
        scout = {
            "candidates": [{
                "name": "UpdateEnemy",
                "entry": "0x3000",
                "has_loop": True,
                "conditional_branches": 5,
                "blocks": 10,
                "callees": 3,
                "globals": 2,
                "stores": 4,
            }]
        }
        result = evaluate(report, scout)
        candidate = result["tier2"]["candidates"][0]
        self.assertIn("success_score", candidate)
        self.assertIn("game_logic_score", candidate)
        self.assertGreater(candidate["game_logic_score"], 0)

    def test_accessor_is_rejected(self) -> None:
        report = {
            "version": 2,
            "units": [{
                "name": "u",
                "functions": [{
                    "name": "GetHealth",
                    "size": 800,
                    "address": "0x4000",
                }],
            }],
        }
        scout = {
            "candidates": [{
                "name": "GetHealth",
                "entry": "0x4000",
                "has_branch": True,
                "blocks": 5,
            }]
        }
        result = evaluate(report, scout)
        self.assertEqual(result["tier2"]["candidates"], [])


if __name__ == "__main__":
    unittest.main()
