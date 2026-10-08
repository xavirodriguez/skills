from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parse_compare import parse_compare


class ParseCompareTests(unittest.TestCase):
    def test_classifies_common_mismatch_families(self) -> None:
        result = parse_compare(
            "match: 82%\n"
            "first mismatch at 0x08001234: expected load word, actual load byte\n"
            "register allocation differs\n"
        )
        self.assertEqual(result["first_mismatch"], "0x08001234")
        self.assertIn("load_store_width", result["mismatch_tags"])
        self.assertIn("register_allocation", result["mismatch_tags"])

    def test_parses_compare_target_json(self) -> None:
        result = parse_compare(
            json.dumps({
                "status": "compare-ran",
                "target": "FS_LoadOverlay",
                "name": "FS_LoadOverlay",
                "function_entry": "0x02042540",
                "function_size": 0x30,
                "match_percent": 82.38,
                "exact_match": False,
                "translation_unit": "overlay.o",
            })
        )
        self.assertEqual(result["match_percent"], 82.38)
        self.assertFalse(result["exact_match"])
        self.assertTrue(result["compare_data_available"])
        self.assertEqual(result["address"], "0x02042540")
        self.assertEqual(result["size"], 0x30)

    def test_structured_missing_match_is_not_zero(self) -> None:
        result = parse_compare(
            json.dumps({
                "status": "compare-incomplete",
                "target": "broken",
                "reason": "no authoritative match value",
            })
        )
        self.assertIsNone(result.get("match_percent"))

    def test_unknown_mismatch_has_fallback_tag(self) -> None:
        result = parse_compare("match: 50%\nfirst mismatch at 0x1000: opaque difference\n")
        self.assertEqual(result["mismatch_tags"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
