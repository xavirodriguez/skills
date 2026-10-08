from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compare_target import build_report_args, find_target, function_rows
from source_edit import main as source_edit_main, sha256_bytes


class SourceEditTests(unittest.TestCase):
    def test_replace_text_is_single_and_hash_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "test.cpp"
            old = root / "old.txt"
            new = root / "new.txt"
            target.write_text(
                "int value = 1;\nint other = 2;\n",
                encoding="utf-8",
            )
            old.write_text("int value = 1;", encoding="utf-8")
            new.write_text("int value = 3;", encoding="utf-8")
            expected = hashlib.sha256(target.read_bytes()).hexdigest()

            argv = sys.argv[:]
            try:
                sys.argv = [
                    "source_edit.py",
                    "--project",
                    str(root),
                    "replace-text",
                    "--path",
                    "test.cpp",
                    "--old-file",
                    "old.txt",
                    "--new-file",
                    "new.txt",
                    "--expected-sha256",
                    expected,
                ]
                self.assertEqual(source_edit_main(), 0)
            finally:
                sys.argv = argv

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "int value = 3;\nint other = 2;\n",
            )

    def test_replace_text_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "test.cpp"
            old = root / "old.txt"
            new = root / "new.txt"
            target.write_text("abc\n", encoding="utf-8")
            old.write_text("abc", encoding="utf-8")
            new.write_text("xyz", encoding="utf-8")
            argv = sys.argv[:]
            try:
                sys.argv = [
                    "source_edit.py",
                    "--project",
                    str(root),
                    "replace-text",
                    "--path",
                    "test.cpp",
                    "--old-file",
                    "old.txt",
                    "--new-file",
                    "new.txt",
                    "--expected-sha256",
                    sha256_bytes(b"wrong"),
                ]
                self.assertEqual(source_edit_main(), 3)
            finally:
                sys.argv = argv
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "abc\n",
            )


class CompareTargetTests(unittest.TestCase):
    def test_build_report_args_are_non_interactive_report_mode(self) -> None:
        args = build_report_args(
            Path("objdiff-cli.exe"),
            Path("project"),
            Path("report.json"),
        )
        self.assertEqual(
            args[1:],
            ["report", "generate", "-p", "project", "-o", "report.json", "-f", "json"],
        )

    def test_find_target_by_name_and_address(self) -> None:
        report = {
            "units": [{
                "name": "_dsd_gap@main_30.o",
                "functions": [{
                    "name": "FS_LoadOverlay",
                    "address": "0x02042540",
                    "size": 0x30,
                    "fuzzy_match_percent": 82.38,
                }],
            }],
        }
        rows = function_rows(report)
        self.assertEqual(
            find_target(rows, "FS_LoadOverlay")["match_percent"],
            82.38,
        )
        target = find_target(rows, "FS_LoadOverlay|0x02042540")
        self.assertEqual(target["size"], 0x30)
        self.assertEqual(target["function_entry"], "0x02042540")
        self.assertEqual(target["function_size"], 0x30)
        self.assertEqual(target["translation_unit"], "_dsd_gap@main_30.o")

    def test_missing_match_percent_is_not_zero(self) -> None:
        rows = function_rows({
            "units": [{
                "functions": [{
                    "name": "incomplete",
                    "address": "0x200",
                    "size": 32,
                }],
            }],
        })
        self.assertIsNone(rows[0]["match_percent"])
        self.assertFalse(rows[0]["match_available"])

    def test_complete_is_authoritative_100(self) -> None:
        rows = function_rows({
            "units": [{
                "functions": [{
                    "name": "done",
                    "address": "0x100",
                    "size": 12,
                    "fuzzy_match_percent": 99.1,
                    "complete": True,
                }],
            }],
        })
        self.assertEqual(rows[0]["match_percent"], 100.0)
        self.assertTrue(rows[0]["complete"])


if __name__ == "__main__":
    unittest.main()
