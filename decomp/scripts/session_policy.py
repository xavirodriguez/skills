#!/usr/bin/env python3
"""Create and enforce decompilation session action policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALL_ACTIONS = ("read", "analyze", "edit", "build", "compare", "select")

MODE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "explain": {
        "read": True, "analyze": False, "edit": False,
        "build": False, "compare": False, "select": False,
    },
    "inspect": {
        "read": True, "analyze": True, "edit": False,
        "build": False, "compare": False, "select": False,
    },
    "analyze": {
        "read": True, "analyze": True, "edit": False,
        "build": False, "compare": False, "select": False,
    },
    "target-match": {
        "read": True, "analyze": True, "edit": True,
        "build": True, "compare": True, "select": False,
    },
    "select": {
        "read": True, "analyze": True, "edit": False,
        "build": True, "compare": True, "select": True,
    },
    "challenge": {
        "read": True, "analyze": True, "edit": True,
        "build": True, "compare": True, "select": True,
    },
}


def default_policy(mode: str) -> dict[str, Any]:
    if mode not in MODE_PERMISSIONS:
        raise ValueError(f"Unsupported mode: {mode}")
    return {
        "format": "decomp-session-policy-v1",
        "mode": mode,
        "permissions": MODE_PERMISSIONS[mode].copy(),
    }


def load_policy(path: Path, *, require_file: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if require_file:
            raise PermissionError(f"Required session policy does not exist: {path}")
        return {
            "format": "decomp-session-policy-v1",
            "mode": "unspecified",
            "permissions": {action: True for action in ALL_ACTIONS},
            "source": "implicit-default",
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Policy must be a JSON object: {path}")

    raw_permissions = payload.get("permissions", {})
    if not isinstance(raw_permissions, dict):
        raise ValueError(f"Policy permissions must be an object: {path}")

    permissions = {
        action: bool(raw_permissions.get(action, True))
        for action in ALL_ACTIONS
    }
    return {
        **payload,
        "permissions": permissions,
        "source": str(path),
    }


def is_allowed(policy: dict[str, Any], action: str) -> bool:
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unsupported action: {action}")
    return bool(policy.get("permissions", {}).get(action, True))


def require_allowed(
    policy_path: Path,
    action: str,
    *,
    require_file: bool = False,
) -> dict[str, Any]:
    policy = load_policy(policy_path, require_file=require_file)
    if not is_allowed(policy, action):
        mode = policy.get("mode", "unspecified")
        raise PermissionError(
            f"Session policy denies '{action}' (mode={mode}, policy={policy_path})."
        )
    return policy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create a policy for a workflow mode.")
    init_parser.add_argument(
        "--mode",
        choices=tuple(MODE_PERMISSIONS),
        required=True,
    )
    init_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )
    init_parser.add_argument("--force", action="store_true")

    check_parser = sub.add_parser("check", help="Check whether an action is allowed.")
    check_parser.add_argument("action", choices=ALL_ACTIONS)
    check_parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )

    show_parser = sub.add_parser("show", help="Print the resolved policy.")
    show_parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".decomp-agent/session-policy.json"),
    )

    args = parser.parse_args()

    if args.command == "init":
        if args.output.exists() and not args.force:
            parser.error(f"Policy exists: {args.output}; use --force to replace it.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(default_policy(args.mode), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(str(args.output))
        return 0

    try:
        policy = load_policy(args.policy)
        if args.command == "check":
            if not is_allowed(policy, args.action):
                print(
                    f"DENY action={args.action} mode={policy.get('mode', 'unspecified')}",
                )
                return 3
            print(
                f"ALLOW action={args.action} mode={policy.get('mode', 'unspecified')}",
            )
            return 0
        print(json.dumps(policy, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, PermissionError) as exc:
        print(str(exc))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
