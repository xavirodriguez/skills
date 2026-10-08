from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_candidate import make_prompt, safe_name


class PrepareCandidateTests(unittest.TestCase):
    def test_safe_name_is_stable(self) -> None:
        self.assertEqual(safe_name("MapBase::Trigger_vfunc_08"), "MapBase_Trigger_vfunc_08")

    def test_pack_inputs_are_json_serializable(self) -> None:
        candidate = {
            "name": "UpdateEnemy",
            "address": "0x1000",
            "size": 1024,
            "match_percent": 0,
            "p75_bytes": 800,
            "threshold_bytes": 800,
            "success_score": 85.0,
            "game_logic_score": 92.0,
            "scout": {"conditional_branches": 4, "back_edges": 1},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.json"
            path.write_text(json.dumps(candidate), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "UpdateEnemy")


    def test_prompt_uses_explicit_function_location_fields(self) -> None:
        prompt = make_prompt({
            "name": "UpdateEnemy",
            "function_entry": "0x1000",
            "function_size": 1024,
            "translation_unit": "Enemy.cpp",
            "match_percent": 0,
            "scout": {},
            "reference": {},
        })
        self.assertIn("function entry: 0x1000", prompt)
        self.assertIn("function size: 1024 bytes", prompt)
        self.assertIn("translation unit: Enemy.cpp", prompt)

    def test_candidate_preparation_has_no_objdiff_cli_dependency(self) -> None:
        source = Path(__file__).resolve().parents[1] / "prepare_candidate.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("objdiff-cli", text)
        self.assertNotIn("subprocess", text)
    def test_prompt_includes_prior_lesson_without_full_ledger(self) -> None:
        prompt = make_prompt(
            {
                "name": "UpdateEnemy",
                "address": "0x1000",
                "size": 1024,
                "match_percent": 0,
                "scout": {},
                "reference": {},
            },
            [
                {
                    "target": "InitEnemy",
                    "hypothesis": "Use uint16 for counter",
                    "lesson": "Match improved by +6.00 percentage points.",
                }
            ],
        )
        self.assertIn("Prior lessons from previous functions:", prompt)
        self.assertIn("Use uint16 for counter", prompt)
        self.assertNotIn('"source_change"', prompt)


if __name__ == "__main__":
    unittest.main()
