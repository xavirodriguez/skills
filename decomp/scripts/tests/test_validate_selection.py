from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_selection import validate


def write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SelectionValidationTests(unittest.TestCase):
    def test_accepts_matching_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.json"
            scout = root / "scout.json"
            selection = root / "selection.json"
            report_hash = write(report, '{"version": 2}')
            scout_hash = write(scout, '{"candidates": []}')
            selection.write_text(json.dumps({
                "format": "decomp-challenge-v2",
                "provenance": {
                    "format": "decomp-selection-provenance-v1",
                    "report": {"sha256": report_hash},
                    "scout": {"sha256": scout_hash},
                },
            }), encoding="utf-8")
            result = validate(json.loads(selection.read_text(encoding="utf-8")), report=report, scout=scout, reference=None)
            self.assertEqual(result["status"], "valid")

    def test_rejects_stale_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.json"
            scout = root / "scout.json"
            report_hash = write(report, '{"version": 2}')
            write(scout, '{"candidates": []}')
            selection = {
                "format": "decomp-challenge-v2",
                "provenance": {
                    "format": "decomp-selection-provenance-v1",
                    "report": {"sha256": report_hash},
                    "scout": {"sha256": hashlib.sha256(scout.read_bytes()).hexdigest()},
                },
            }
            report.write_text('{"version": 3}', encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(selection, report=report, scout=scout, reference=None)

    def test_rejects_legacy_selection_without_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "report.json"
            report.write_text('{}', encoding="utf-8")
            with self.assertRaises(ValueError):
                validate({"format": "decomp-challenge-v2"}, report=report, scout=None, reference=None)


if __name__ == "__main__":
    unittest.main()
