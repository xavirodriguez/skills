from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge_autopilot import select_tier2


class Tier2AutopilotTests(unittest.TestCase):
    def test_applies_p75_and_256_gate(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "a", "functions": [{"name": "A", "size": 256, "address": "0x1000"}]},
                {"name": "b", "functions": [{"name": "B", "size": 300, "address": "0x1100"}]},
                {"name": "c", "functions": [{"name": "C", "size": 400, "address": "0x1200"}]},
                {"name": "d", "functions": [{"name": "D", "size": 900, "address": "0x1300", "fuzzy_match_percent": 100}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "A", "entry": "0x1000", "has_branch": True, "blocks": 4, "callees": 2},
                {"name": "B", "entry": "0x1100", "has_branch": True, "blocks": 4, "callees": 2},
                {"name": "C", "entry": "0x1200", "has_loop": True, "blocks": 6, "callees": 2},
            ]
        }

        result = select_tier2(report, scout)
        self.assertEqual(result["summary"]["p75_bytes"], 350.0)
        self.assertEqual([item["name"] for item in result["eligible"]], ["C"])

    def test_rejects_accessor_and_table_like_functions(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "u1", "functions": [{"name": "GetHealth", "size": 512, "address": "0x2000"}]},
                {"name": "u2", "functions": [{"name": "EnemyTable", "size": 1024, "address": "0x3000"}]},
                {"name": "u3", "functions": [{"name": "UpdateEnemy", "size": 1024, "address": "0x4000"}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "GetHealth", "entry": "0x2000", "has_branch": True, "blocks": 4, "callees": 2},
                {"name": "EnemyTable", "entry": "0x3000", "has_branch": True, "blocks": 4, "callees": 2},
                {"name": "UpdateEnemy", "entry": "0x4000", "has_branch": True, "blocks": 8, "callees": 4},
            ]
        }

        result = select_tier2(report, scout)
        self.assertEqual([item["name"] for item in result["eligible"]], ["UpdateEnemy"])

    def test_requires_stronger_logic_evidence_than_one_branch(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "BigWrapper", "functions": [{"name": "BigWrapper", "size": 600, "address": "0x5000"}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "BigWrapper", "entry": "0x5000", "has_branch": True, "blocks": 2, "callees": 0, "globals": 0}
            ]
        }
        result = select_tier2(report, scout)
        self.assertEqual(result["eligible"], [])

    def test_partial_match_is_not_undecompiled(self) -> None:
        report = {
            "version": 2,
            "units": [
                {"name": "partial", "functions": [{"name": "Partial", "size": 900, "address": "0x6000", "fuzzy_match_percent": 12.5}]},
                {"name": "logic", "functions": [{"name": "Logic", "size": 900, "address": "0x6100"}]},
            ],
        }
        scout = {
            "candidates": [
                {"name": "Logic", "entry": "0x6100", "has_loop": True, "blocks": 7, "callees": 3},
            ]
        }
        result = select_tier2(report, scout)
        self.assertEqual([item["name"] for item in result["eligible"]], ["Logic"])


if __name__ == "__main__":
    unittest.main()
