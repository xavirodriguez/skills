#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_match import build_process_args, capture_git_state, contains_nested_agent_invocation, derive_lesson


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


    def test_git_state_excludes_agent_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            (root / "source.cpp").write_text("int x = 1;\n", encoding="utf-8")
            subprocess.run(["git", "add", "source.cpp"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-m", "baseline"],
                cwd=root,
                check=True,
                capture_output=True,
            )

            (root / "source.cpp").write_text("int x = 2;\n", encoding="utf-8")
            (root / ".decomp-agent").mkdir()
            (root / ".decomp-agent" / "internal.json").write_text("{}", encoding="utf-8")
            subprocess.run(["git", "add", "source.cpp"], cwd=root, check=True, capture_output=True)

            state = capture_git_state(root)
            self.assertTrue(state["dirty"])
            self.assertTrue(any("source.cpp" in item for item in state["changed_files"]))
            self.assertFalse(any(".decomp-agent" in item for item in state["changed_files"]))
            self.assertIn("source.cpp", state["diff_stat"])


class RunMatchTelemetryTests(unittest.TestCase):
    def test_lesson_reports_match_delta(self) -> None:
        lesson = derive_lesson(
            {"match_percent": 70.0},
            {"match_percent": 78.5, "mismatch_tags": ["stack_layout"]},
            "compare-ran",
        )
        self.assertIn("+8.50", lesson)
        self.assertIn("stack_layout", lesson)

    def test_interactive_objdiff_is_rejected(self) -> None:
        code, log, elapsed, timed_out, transport = run(
            "objdiff-cli.exe diff -p . target",
            Path(".").resolve(),
            "powershell",
            10.0,
        )
        self.assertEqual(code, 5)
        self.assertTrue(transport)
        self.assertIn("interactive objdiff diff is forbidden", log)
        self.assertFalse(timed_out)
        self.assertEqual(elapsed, 0.0)

    def test_nested_agent_invocation_is_rejected(self) -> None:
        self.assertTrue(contains_nested_agent_invocation("codex.exe --help"))
        self.assertTrue(contains_nested_agent_invocation(r".\\opencode.exe run"))
        self.assertFalse(contains_nested_agent_invocation("ninja"))

    def test_timeout_command_uses_shell_contract(self) -> None:
        if sys.platform == "win32":
            command = "Start-Sleep -Seconds 2"
            shell = "powershell"
        else:
            command = f'"{sys.executable}" -c "import time; time.sleep(2)"'
            shell = "bash"

        from run_match import run

        code, log, _, timed_out, tool_transport = run(
            command,
            Path(".").resolve(),
            shell,
            timeout=0.1,
        )
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)
        self.assertFalse(tool_transport)
        self.assertIn("timeout=", log)


if __name__ == "__main__":
    unittest.main()
