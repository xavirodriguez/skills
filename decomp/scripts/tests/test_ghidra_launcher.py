from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghidra_launcher import launcher_info, script_runtime


class GhidraLauncherTests(unittest.TestCase):
    def test_detects_launchers_from_explicit_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            support = home / "support"
            support.mkdir()
            (support / "pyghidraRun.bat").write_text("@echo off\n", encoding="utf-8")
            (support / "analyzeHeadless.bat").write_text("@echo off\n", encoding="utf-8")

            result = launcher_info(home)
            self.assertEqual(result["ghidra_home"], str(home.resolve()))
            self.assertTrue(result["pyghidra_available"])
            self.assertTrue(result["headless_available"])

    def test_runtime_marker_selects_pyghidra(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "collector.py"
            script.write_text("# decomp-runtime: pyghidra\n", encoding="utf-8")
            self.assertEqual(script_runtime(script), "pyghidra")

    def test_plain_ghidra_script_uses_headless(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "collector.py"
            script.write_text("from ghidra.app.decompiler import DecompInterface\n", encoding="utf-8")
            self.assertEqual(script_runtime(script), "ghidra-headless")


if __name__ == "__main__":
    unittest.main()
