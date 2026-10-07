#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_match import build_process_args


class RunMatchShellTests(unittest.TestCase):
    def test_powershell_invocation(self) -> None:
        args = build_process_args("Get-Location", "powershell")
        self.assertEqual(args[:3], ["powershell.exe", "-NoProfile", "-Command"])

    def test_pwsh_invocation(self) -> None:
        args = build_process_args("Get-Location", "pwsh")
        self.assertEqual(args[:3], ["pwsh", "-NoProfile", "-Command"])

    def test_bash_invocation(self) -> None:
        args = build_process_args("pwd", "bash")
        self.assertEqual(args[:2], ["bash", "-lc"])

    def test_cmd_invocation(self) -> None:
        args = build_process_args("dir", "cmd")
        self.assertEqual(args[:3], ["cmd.exe", "/d", "/s"])


if __name__ == "__main__":
    unittest.main()
