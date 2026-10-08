from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_candidate import safe_name


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


if __name__ == "__main__":
    unittest.main()
