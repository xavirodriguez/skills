from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge_selector import percentile75, select


class ChallengeSelectorTests(unittest.TestCase):
    def test_percentile75_uses_linear_interpolation(self) -> None:
        self.assertEqual(percentile75([100, 200, 300, 400]), 325.0)

    def test_missing_fuzzy_percent_is_unavailable(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "A", "functions": [{"name": "fn_a", "size": "64", "address": "0x1000"}]},
                {"name": "B", "functions": [{"name": "fn_b", "size": "300", "address": "0x1100", "fuzzy_match_percent": 100}]},
            ],
        }
        result = select(report)
        self.assertEqual(result["summary"]["undecompiled_functions"], 0)
        self.assertEqual(result["summary"]["unavailable_match_data_functions"], 1)
        self.assertEqual(result["tier1"]["candidates"], [])

    def test_tier2_applies_both_size_gates(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "f1", "functions": [{"name": "a", "size": 256, "address": "0x1000", "fuzzy_match_percent": 0}]},
                {"name": "f2", "functions": [{"name": "b", "size": 300, "address": "0x1100", "fuzzy_match_percent": 0}]},
                {"name": "f3", "functions": [{"name": "c", "size": 400, "address": "0x1200", "fuzzy_match_percent": 0}]},
                {"name": "done", "functions": [{"name": "d", "size": 900, "address": "0x1300", "fuzzy_match_percent": 100}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "a", "entry": "0x1000", "has_branch": True, "blocks": 4},
                {"name": "b", "entry": "0x1100", "has_branch": True, "blocks": 5},
                {"name": "c", "entry": "0x1200", "has_branch": True, "blocks": 6},
            ]
        }

        result = select(report, scout)
        self.assertEqual(result["summary"]["remaining_undecompiled_p75_bytes"], 350.0)
        self.assertEqual(result["summary"]["tier2_size_threshold_bytes"], 350.0)
        self.assertEqual([item["name"] for item in result["tier2"]["candidates"]], ["c"])

    def test_tier2_requires_confirmed_control_flow(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "logic", "functions": [{"name": "logic", "size": 512, "address": "0x2000", "fuzzy_match_percent": 0}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "logic", "entry": "0x2000", "blocks": 5}
            ]
        }

        result = select(report, scout)
        self.assertEqual(result["tier2"]["candidates"], [])

    def test_obvious_table_is_excluded_from_tiers(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "table", "functions": [{"name": "EnemyTable", "size": 1024, "address": "0x3000", "fuzzy_match_percent": 0}]},
                {"name": "logic", "functions": [{"name": "UpdateEnemy", "size": 1200, "address": "0x4000", "fuzzy_match_percent": 0}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "EnemyTable", "entry": "0x3000", "has_branch": True, "blocks": 3},
                {"name": "UpdateEnemy", "entry": "0x4000", "has_branch": True, "has_loop": True, "blocks": 8},
            ]
        }

        result = select(report, scout)
        tier2_names = [item["name"] for item in result["tier2"]["candidates"]]
        self.assertNotIn("EnemyTable", tier2_names)
        self.assertIn("UpdateEnemy", tier2_names)

    def test_partial_function_is_not_called_undecompiled(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "partial", "functions": [{"name": "partial", "size": 300, "address": "0x5000", "fuzzy_match_percent": 42.5}]},
                {"name": "new", "functions": [{"name": "new", "size": 320, "address": "0x5100", "fuzzy_match_percent": 0}]},
            ],
        }
        result = select(report)
        self.assertEqual(result["summary"]["partial_functions"], 1)
        self.assertEqual(result["summary"]["undecompiled_functions"], 1)

if __name__ == "__main__":
    unittest.main()
