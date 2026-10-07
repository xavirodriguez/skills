#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preflight import command_path, project_checks


class PreflightTests(unittest.TestCase):
    def test_command_path_tries_aliases_in_order(self) -> None:
        with patch("preflight.shutil.which", side_effect=[None, "C:/Python/python.exe"]):
            self.assertEqual(command_path("missing", "python"), "C:/Python/python.exe")

    def test_project_checks_reports_ph_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "objdiff.json").write_text("{}", encoding="utf-8")
            (root / "build.ninja").write_text("", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "configure.py").write_text("", encoding="utf-8")
            result = project_checks(root, None, None)
            self.assertTrue(result["objdiff_json"]["exists"])
            self.assertTrue(result["build_ninja"]["exists"])
            self.assertTrue(result["configure_py"]["exists"])


if __name__ == "__main__":
    unittest.main()
