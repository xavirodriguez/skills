from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from roi_selector import select


class RoiSelectorTests(unittest.TestCase):
    def make_report(self) -> dict:
        return {
            "version": 2,
            "units": [{
                "name": "u",
                "functions": [
                    {"name": "A", "size": 128, "address": "0x1000", "fuzzy_match_percent": 0},
                    {"name": "B", "size": 256, "address": "0x1100", "fuzzy_match_percent": 0},
                    {"name": "C", "size": 512, "address": "0x1200", "fuzzy_match_percent": 0},
                    {"name": "D", "size": 768, "address": "0x1300", "fuzzy_match_percent": 0},
                    {"name": "E", "size": 1024, "address": "0x1400", "fuzzy_match_percent": 0},
                    {"name": "Unknown", "size": 64, "address": "0x1500"},
                    {"name": "Exact", "size": 512, "address": "0x1600", "fuzzy_match_percent": 100},
                ],
            }],
        }

    def make_scout(self) -> dict:
        return {
            "candidates": [
                {"name": "A", "entry": "0x1000", "blocks": 2, "callers": 0},
                {
                    "name": "B", "entry": "0x1100", "blocks": 4,
                    "has_loop": True, "conditional_branches": 2,
                    "callers": 5, "callees": 2, "resolved_callers": 3,
                    "globals": 2,
                },
                {
                    "name": "C", "entry": "0x1200", "blocks": 8,
                    "conditional_branches": 4, "callers": 2, "callees": 5,
                    "resolved_callees": 3, "globals": 3,
                },
                {
                    "name": "D", "entry": "0x1300", "blocks": 3,
                    "has_switch": True, "callers": 8, "callees": 4,
                    "resolved_callers": 2, "globals": 1,
                },
                {
                    "name": "E", "entry": "0x1400", "blocks": 12,
                    "conditional_branches": 8, "callers": 1, "callees": 8,
                    "globals": 5,
                },
            ]
        }

    def test_returns_exactly_five_known_unmatched_candidates(self) -> None:
        result = select(self.make_report(), self.make_scout())
        self.assertEqual(result["summary"]["candidate_universe"], 5)
        self.assertEqual(result["summary"]["returned"], 5)
        self.assertEqual(len(result["candidates"]), 5)
        names = {item["name"] for item in result["candidates"]}
        self.assertNotIn("Unknown", names)
        self.assertNotIn("Exact", names)

    def test_roi_formula_and_scores_are_exposed(self) -> None:
        result = select(self.make_report(), self.make_scout())
        for item in result["candidates"]:
            expected = round(item["ease_score"] * item["impact_score"] / 100.0, 2)
            self.assertEqual(item["roi_score"], expected)
            self.assertGreaterEqual(item["ease_score"], 0)
            self.assertLessEqual(item["ease_score"], 100)
            self.assertGreaterEqual(item["impact_score"], 0)
            self.assertLessEqual(item["impact_score"], 100)
            self.assertGreaterEqual(item["unlock_score"], 0)
            self.assertLessEqual(item["unlock_score"], 100)

    def test_call_graph_context_increases_impact(self) -> None:
        result = select(self.make_report(), self.make_scout())
        by_name = {item["name"]: item for item in result["candidates"]}
        self.assertGreater(by_name["B"]["impact_score"], by_name["A"]["impact_score"])
        self.assertGreater(by_name["B"]["unlock_score"], by_name["A"]["unlock_score"])

    def test_milestone_delta_detects_newly_completed_unit(self) -> None:
        previous = self.make_report()
        previous["units"][0]["functions"][-3]["fuzzy_match_percent"] = 0
        previous["units"][0]["functions"][-2]["fuzzy_match_percent"] = 0
        previous["units"][0]["functions"][-1]["fuzzy_match_percent"] = 0

        current = self.make_report()
        result = select(
            current,
            self.make_scout(),
            previous_report=previous,
        )
        self.assertTrue(result["milestone"]["available"])
        self.assertEqual(result["milestone"]["newly_completed_units"], ["u"])
        self.assertEqual(result["milestone"]["new_exact_functions"], 3)


if __name__ == "__main__":
    unittest.main()
