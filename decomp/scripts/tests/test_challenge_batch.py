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
    load_session,
    record_integration,
    record_result,
)


def evaluation_for(*names: str) -> dict:
    candidates = [
        {
            "name": name,
            "address": f"0x{1000 + index:X}",
            "function_entry": f"0x{1000 + index:X}",
            "function_size": 512 + index * 64,
            "translation_unit": "overlay.o",
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
    def test_v1_session_migrates_without_losing_matched_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            path.write_text(json.dumps({
                "format": "decomp-challenge-session-v1",
                "matches_completed": 2,
                "queue": [{"name": "A", "status": "matched"}],
            }), encoding="utf-8")
            session = load_session(path)
            self.assertEqual(session["format"], "decomp-challenge-session-v2")
            self.assertEqual(session["function_matches_completed"], 2)
            self.assertEqual(session["integration_matches_completed"], 2)
            self.assertEqual(session["queue"][0]["integration"]["status"], "legacy-accepted")
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
            self.assertEqual(loaded["format"], "decomp-challenge-session-v2")

    def test_record_rejects_non_current_target(self) -> None:
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
            with self.assertRaises(ValueError):
                record_result(
                    session,
                    target="B",
                    match_before=0.0,
                    match_after=1.0,
                    exact=False,
                    mismatch="wrong target",
                    lesson="Must not advance manually.",
                    infrastructure_blocker=False,
                )

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

    def test_tool_transport_failure_does_not_consume_stagnation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A"),
                tier="tier2",
                quota=0,
                max_stagnation=1,
                replace=True,
            )
            session["queue"][0]["status"] = "active"
            session["current_target"] = session["queue"][0]["key"]

            for _ in range(5):
                candidate = record_result(
                    session,
                    target="A",
                    match_before=50.0,
                    match_after=50.0,
                    exact=False,
                    mismatch=None,
                    lesson="PowerShell transport failed",
                    infrastructure_blocker=False,
                    tool_transport_failure=True,
                )

            self.assertEqual(candidate["status"], "active")
            self.assertEqual(candidate["stagnation"], 0)
            self.assertEqual(candidate["attempts"], 0)
            self.assertEqual(candidate["tool_failures"], 5)
            self.assertFalse(session["halted"])
            self.assertEqual(
                session["history"][-1]["status"],
                "tool-transport-failure",
            )
            self.assertFalse(session["history"][-1]["counted_as_stagnation"])

    def test_exact_match_enters_integration_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = init_session(
                path,
                evaluation_for("A", "B"),
                tier="tier2",
                quota=1,
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
            self.assertEqual(candidate["status"], "integration-pending")
            self.assertEqual(session["current_target"], candidate["key"])
            self.assertEqual(session["phase"], "integration")
            self.assertEqual(session["matches_completed"], 0)
            self.assertEqual(session["function_matches_completed"], 1)

            integration = {
                "target": "A",
                "regions": {
                    "usa": {
                        "function": {"entry": "0x3E8", "size": 512},
                        "object": {"name": "overlay.o", "start": "0x3E8", "end": "0x800"},
                        "range": {"kind": "delink", "start": "0x3E8", "end": "0x800"},
                        "padding": {"before": [], "after": []},
                        "next_boundary": "0x801",
                        "evidence": ["xMAP", "link map"],
                        "verification": {"status": "pass", "function_match_percent": 100.0, "command": "ninja check"},
                    }
                },
            }
            result = record_integration(
                session,
                target="A",
                status="pass",
                evidence=integration,
                lesson="Object range verified.",
            )
            self.assertEqual(result["status"], "matched")
            self.assertIsNone(session["current_target"])
            self.assertEqual(session["matches_completed"], 1)
            self.assertTrue(session["halted"])
            self.assertEqual(session["stop_reason"], "quota-reached")

    def test_next_returns_same_target_while_integration_pending(self) -> None:
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
            session["queue"][0]["status"] = "integration-pending"
            session["current_target"] = session["queue"][0]["key"]
            session["phase"] = "integration"

            candidate = choose_next(session)
            self.assertEqual(candidate["name"], "A")
            self.assertEqual(candidate["status"], "integration-pending")

    def test_exact_match_keeps_target_for_integration(self) -> None:
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
            self.assertEqual(candidate["status"], "integration-pending")
            self.assertEqual(session["matches_completed"], 0)
            self.assertEqual(session["function_matches_completed"], 1)
            self.assertEqual(session["phase"], "integration")
            self.assertEqual(session["current_target"], candidate["key"])


if __name__ == "__main__":
    unittest.main()
