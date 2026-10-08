from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge_batch import (
    choose_next,
    init_session,
    record_result,
)


def evaluation_for(*names: str) -> dict:
    candidates = [
        {
            "name": name,
            "address": f"0x{1000 + index:X}",
            "size": 512 + index * 64,
            "match_percent": 0.0,
            "success_score": 90.0 - index,
            "game_logic_score": 80.0,
            "complexity_score": 20.0 + index,
            "expected_value_score": 85.0 - index,
            "gates": {"zero_match": True},
            "match_kind": "zero_match_no_source",
        }
        for index, name in enumerate(names)
    ]
    return {
        "tier2": {"candidates": candidates},
        "tier1": {"candidates": candidates},
        "tier3": {"candidates": candidates},
    }


class ChallengeBatchTests(unittest.TestCase):
    def test_queue_persists_and_selects_expected_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A", "B"),
                tier="tier2",
                quota=0,
                max_stagnation=3,
                replace=True,
            )
            candidate = choose_next(session)
            self.assertEqual(candidate["name"], "A")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["format"], "decomp-challenge-session-v1")

    def test_no_progress_blocks_after_stagnation_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A"),
                tier="tier2",
                quota=0,
                max_stagnation=3,
                replace=True,
            )
            session["queue"][0]["status"] = "active"
            session["current_target"] = session["queue"][0]["key"]

            for _ in range(3):
                candidate = record_result(
                    session,
                    target="A",
                    match_before=50.0,
                    match_after=50.0,
                    exact=False,
                    mismatch="stack_layout",
                    lesson="No improvement",
                    infrastructure_blocker=False,
                )

            self.assertEqual(candidate["status"], "blocked")
            self.assertIsNone(session["current_target"])

    def test_progress_resets_stagnation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A", "B"),
                tier="tier2",
                quota=0,
                max_stagnation=3,
                replace=True,
            )
            session["queue"][0]["status"] = "active"
            session["current_target"] = session["queue"][0]["key"]

            record_result(
                session,
                target="A",
                match_before=50.0,
                match_after=60.0,
                exact=False,
                mismatch="stack_layout",
                lesson="Improved",
                infrastructure_blocker=False,
            )
            self.assertEqual(session["queue"][0]["stagnation"], 0)

            record_result(
                session,
                target="A",
                match_before=60.0,
                match_after=60.0,
                exact=False,
                mismatch="register_allocation",
                lesson="No improvement",
                infrastructure_blocker=False,
            )
            self.assertEqual(session["queue"][0]["stagnation"], 1)

    def test_exact_match_clears_current_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A", "B"),
                tier="tier2",
                quota=0,
                max_stagnation=3,
                replace=True,
            )
            session["queue"][0]["status"] = "active"
            session["current_target"] = session["queue"][0]["key"]

            candidate = record_result(
                session,
                target="A",
                match_before=91.0,
                match_after=100.0,
                exact=True,
                mismatch=None,
                lesson="Exact authoritative match.",
                infrastructure_blocker=False,
            )
            self.assertEqual(candidate["status"], "matched")
            self.assertEqual(session["matches_completed"], 1)
            self.assertIsNone(session["current_target"])


if __name__ == "__main__":
    unittest.main()
