#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_match import build_process_args, derive_lesson


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


class RunMatchTelemetryTests(unittest.TestCase):
    def test_lesson_reports_match_delta(self) -> None:
        lesson = derive_lesson(
            {"match_percent": 70.0},
            {"match_percent": 78.5, "mismatch_tags": ["stack_layout"]},
            "compare-ran",
        )
        self.assertIn("+8.50", lesson)
        self.assertIn("stack_layout", lesson)

    def test_timeout_command_uses_shell_contract(self) -> None:
        if sys.platform == "win32":
            command = "Start-Sleep -Seconds 2"
            shell = "powershell"
        else:
            command = f'"{sys.executable}" -c "import time; time.sleep(2)"'
            shell = "bash"

        from run_match import run

        code, log, _, timed_out = run(
            command,
            Path(".").resolve(),
            shell,
            timeout=0.1,
        )
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)
        self.assertIn("timeout=", log)


if __name__ == "__main__":
    unittest.main()
