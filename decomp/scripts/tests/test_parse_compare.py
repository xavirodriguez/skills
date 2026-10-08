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

    def test_unknown_mismatch_has_fallback_tag(self) -> None:
        result = parse_compare("match: 50%\nfirst mismatch at 0x1000: opaque difference\n")
        self.assertEqual(result["mismatch_tags"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
