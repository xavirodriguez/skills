#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from candidate_gate import gate


class CandidateGateTests(unittest.TestCase):
    def test_unmarked_reference_blocks_unit_by_default(self) -> None:
        objdiff = {
            "units": [{
                "name": "TouchControl",
                "target_path": "src/Main/Player/TouchControl.cpp",
                "metadata": {"complete": False},
            }]
        }
        reference = {
            "functions": [{
                "name": "func_02001000",
                "source_file": "D:/ref/ph/src/Main/Player/TouchControl.cpp",
                "status": "unmarked",
            }]
        }
        result = gate(objdiff, reference)
        self.assertEqual(result["candidates"][0]["action"], "skip_unit_by_default")
        self.assertEqual(result["reference_blocked_units"], 1)

    def test_nonmatching_reference_allows_codegen_work(self) -> None:
        objdiff = {
            "units": [{
                "name": "TouchControl",
                "target_path": "src/Main/Player/TouchControl.cpp",
                "metadata": {"complete": False},
            }]
        }
        reference = {
            "functions": [{
                "name": "func_02001000",
                "source_file": "D:/ref/ph/src/Main/Player/TouchControl.cpp",
                "status": "known_nonmatching",
            }]
        }
        result = gate(objdiff, reference)
        self.assertEqual(
            result["candidates"][0]["action"],
            "inspect_reference_nonmatching",
        )
        self.assertEqual(result["reference_blocked_units"], 0)


if __name__ == "__main__":
    unittest.main()
