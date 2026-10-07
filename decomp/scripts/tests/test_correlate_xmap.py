#!/usr/bin/env python3
"""Unit tests for the XMAP/Ghidra correlation helper."""

from __future__ import annotations

import unittest

from correlate_xmap import correlate


class CorrelateXmapTests(unittest.TestCase):
    def test_exact_address_matches_function(self) -> None:
        xmap = {
            "file": "arm9.o.xMAP",
            "symbols": [
                {
                    "name": "Player_Update",
                    "address": "0x02012340",
                    "address_int": 0x02012340,
                    "kind": "probable_function",
                    "section": ".text",
                    "confidence": "medium",
                }
            ],
        }
        ghidra = {
            "program": {"name": "Zelda"},
            "functions": [
                {
                    "name": "FUN_02012340",
                    "entry": "02012340",
                    "body_min": "02012340",
                    "body_max": "02012400",
                }
            ],
            "symbols": [],
        }

        result = correlate(xmap, ghidra)

        self.assertEqual(result["statistics"]["correlations"], 1)
        self.assertEqual(result["correlations"][0]["xmap_name"], "Player_Update")
        self.assertEqual(result["correlations"][0]["ghidra_name"], "FUN_02012340")
        self.assertEqual(result["correlations"][0]["match"]["confidence"], "high")

    def test_unmatched_xmap_symbol_is_reported(self) -> None:
        xmap = {
            "symbols": [
                {
                    "name": "Missing_Function",
                    "address": "0x02020000",
                    "address_int": 0x02020000,
                }
            ]
        }
        ghidra = {
            "program": {"name": "Zelda"},
            "functions": [],
            "symbols": [],
        }

        result = correlate(xmap, ghidra)

        self.assertEqual(result["statistics"]["correlations"], 0)
        self.assertEqual(result["statistics"]["unmatched_xmap"], 1)
        self.assertEqual(
            result["unmatched_xmap"][0]["reason"],
            "no_ghidra_entry_at_address",
        )

    def test_explicit_offset_is_applied_without_auto_detection(self) -> None:
        xmap = {
            "symbols": [
                {
                    "name": "Offset_Function",
                    "address": "0x00001000",
                    "address_int": 0x1000,
                }
            ]
        }
        ghidra = {
            "program": {"name": "Zelda"},
            "functions": [
                {
                    "name": "FUN_02001000",
                    "entry": "02001000",
                }
            ],
            "symbols": [],
        }

        result = correlate(xmap, ghidra, 0x02000000)

        self.assertEqual(result["statistics"]["correlations"], 1)
        self.assertEqual(result["correlations"][0]["ghidra_name"], "FUN_02001000")
        self.assertFalse(result["policy"]["auto_address_delta"])

if __name__ == "__main__":
    unittest.main()
