from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis_knowledge import compact, search


class HypothesisKnowledgeTests(unittest.TestCase):
    def test_reuses_lessons_across_different_targets(self) -> None:
        entries = [
            {
                "target": "func_A",
                "hypothesis": "Use uint16 for enemy count",
                "source_change": "Change local counter type",
                "lesson": "Match improved by +7.00 percentage points",
                "mismatch_tags": ["stack_layout", "load_store_width"],
                "match_before": 70.0,
                "match_after": 77.0,
            },
            {
                "target": "func_B",
                "hypothesis": "Change unrelated branch",
                "source_change": "Invert branch",
                "lesson": "No improvement",
                "mismatch_tags": ["branch_layout"],
                "match_before": 80.0,
                "match_after": 80.0,
            },
        ]
        results = search(
            entries,
            target="func_C",
            query="counter type uint16",
            tags=["stack_layout"],
            top_k=2,
        )
        self.assertEqual(results[0]["target"], "func_A")
        self.assertEqual(results[0]["match_after"], 77.0)
        self.assertIn("stack_layout", results[0]["knowledge_reasons"][1])

    def test_compact_result_is_context_friendly(self) -> None:
        results = compact([{
            "target": "func_A",
            "hypothesis": "Use uint16",
            "lesson": "Improved",
            "decision": "compare-ran",
            "mismatch_tags": ["load_store_width"],
            "match_before": 70.0,
            "match_after": 77.0,
            "first_mismatch_after": "0x1000",
            "knowledge_score": 12.0,
            "knowledge_reasons": ["tags:load_store_width"],
            "source_change": "local type",
        }])
        self.assertEqual(results[0]["target"], "func_A")
        self.assertNotIn("source_change", results[0])


if __name__ == "__main__":
    unittest.main()
