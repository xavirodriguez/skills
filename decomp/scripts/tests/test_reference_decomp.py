#!/usr/bin/env python3
"""Tests for the reference decompilation indexer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyze_reference_project import analyze


SOURCE = """
ARM void func_02001000() {
}

ARM void func_02001010() {
}

// non-matching
ARM void func_02001020() {
}

// non-matching (equivalent)
THUMB void func_02001030() {
}

// non-matching (regalloc)
ARM void func_02001040() {
}
"""


class ReferenceDecompilerTests(unittest.TestCase):
    def test_status_markers_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            (src / "sample.cpp").write_text(SOURCE, encoding="utf-8")

            result = analyze(root, None)
            by_address = {
                item["address"]: item
                for item in result["functions"]
                if item["address"] is not None
            }

            self.assertEqual(by_address["0x00001000"]["status"], "unmarked")
            self.assertEqual(
                by_address["0x00001000"]["recommended_action"],
                "skip_by_default",
            )
            self.assertEqual(
                by_address["0x00001020"]["status"],
                "known_nonmatching",
            )
            self.assertEqual(
                by_address["0x00001030"]["status"],
                "known_nonmatching_equivalent",
            )
            self.assertEqual(
                by_address["0x00001030"]["recommended_action"],
                "reuse_reference_fix_codegen",
            )
            self.assertEqual(
                by_address["0x00001040"]["status_reason"],
                "regalloc",
            )

    def test_xmap_exact_address_is_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            (src / "sample.cpp").write_text(
                "ARM void func_02001000() {}\n",
                encoding="utf-8",
            )
            xmap = {
                "symbols": [
                    {
                        "name": "func_02001000",
                        "address": "0x02001000",
                        "address_int": 0x02001000,
                    }
                ]
            }

            result = analyze(root, xmap)

            self.assertEqual(len(result["xmap_matches"]), 1)
            self.assertEqual(
                result["xmap_matches"][0]["identity"],
                "exact_address",
            )
            self.assertEqual(
                result["xmap_matches"][0]["reference_recommended_action"],
                "skip_by_default",
            )


if __name__ == "__main__":
    unittest.main()
