from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from candidate_gate import gate


class CandidateGateTests(unittest.TestCase):
    def test_reference_status_is_function_level(self) -> None:
        objdiff = {
            "units": [{
                "name": "TouchControl",
                "target_path": "src/Main/Player/TouchControl.cpp",
                "metadata": {"complete": False},
                "functions": [
                    {"name": "func_02001000", "size": 300, "address": "0x02001000", "fuzzy_match_percent": 0},
                    {"name": "func_02002000", "size": 300, "address": "0x02002000", "fuzzy_match_percent": 0},
                ],
            }]
        }
        reference = {
            "functions": [
                {
                    "name": "func_02001000",
                    "source_file": "D:/ref/ph/src/Main/Player/TouchControl.cpp",
                    "status": "known_nonmatching",
                },
                {
                    "name": "func_02002000",
                    "source_file": "D:/ref/ph/src/Main/Player/TouchControl.cpp",
                    "status": "unmarked",
                },
            ]
        }

        result = gate(objdiff, reference)
        actions = {item["name"]: item["action"] for item in result["functions"]}
        self.assertEqual(actions["func_02001000"], "reuse_reference_and_match")
        self.assertEqual(actions["func_02002000"], "reuse_reference_apparently_matching")
        self.assertEqual(result["summary"]["target_incomplete_functions"], 2)

    def test_complete_reference_does_not_block_target_function(self) -> None:
        objdiff = {
            "units": [{
                "name": "TouchControl",
                "metadata": {"complete": False},
                "functions": [
                    {"name": "func_02001000", "size": 300, "address": "0x02001000", "fuzzy_match_percent": 0},
                ],
            }]
        }
        reference = {
            "functions": [{
                "name": "func_02001000",
                "status": "unmarked",
                "reference_build_status": "complete",
            }]
        }

        result = gate(objdiff, reference)
        item = result["functions"][0]
        self.assertEqual(item["action"], "reuse_verified_reference")
        self.assertEqual(result["summary"]["new_target_analysis"], 0)


if __name__ == "__main__":
    unittest.main()
