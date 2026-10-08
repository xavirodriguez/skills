from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from session_policy import default_policy, is_allowed, load_policy, require_allowed


class SessionPolicyTests(unittest.TestCase):
    def test_target_match_allows_build_but_not_select(self) -> None:
        policy = default_policy("target-match")
        self.assertTrue(is_allowed(policy, "build"))
        self.assertTrue(is_allowed(policy, "compare"))
        self.assertFalse(is_allowed(policy, "select"))

    def test_existing_policy_overrides_implicit_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(
                json.dumps({
                    "format": "decomp-session-policy-v1",
                    "mode": "explain",
                    "permissions": {
                        "read": True,
                        "build": False,
                        "analyze": False,
                    },
                }),
                encoding="utf-8",
            )
            policy = load_policy(path)
            self.assertTrue(is_allowed(policy, "read"))
            self.assertFalse(is_allowed(policy, "build"))
            self.assertFalse(is_allowed(policy, "analyze"))


    def test_required_missing_policy_is_a_hard_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):
                require_allowed(
                    Path(tmp) / "missing.json",
                    "build",
                    require_file=True,
                )


if __name__ == "__main__":
    unittest.main()
