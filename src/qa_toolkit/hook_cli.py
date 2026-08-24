"""Small command surface for repository hook state and dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from qa_toolkit.deployment import DeploymentError, resolve_target
from qa_toolkit.guardrail_state import GuardrailStateError, breaker_status, proof_status
from qa_toolkit.hook_deployment import HookDeploymentError, hook_status, set_enabled
from qa_toolkit.hook_dispatch import dispatch, invocation_context


def _load(target: Path) -> tuple[Path, dict[str, object]]:
    path = target / ".git" / "qat" / "deployment.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HookDeploymentError("repository is not enrolled") from error
    if not isinstance(record, dict) or not isinstance(record.get("hooks"), dict):
        raise HookDeploymentError("repository hook deployment is unavailable")
    return Path(str(record["toolkit_root"])), cast(dict[str, Any], record["hooks"])


def _filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kind", choices=("git", "codex"))
    parser.add_argument("--event")
    parser.add_argument("--entry")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-hook")
    operations = parser.add_subparsers(dest="operation", required=True)
    for operation in ("enable", "disable"):
        command = operations.add_parser(operation)
        command.add_argument("target", type=Path)
        _filters(command)
    status = operations.add_parser("status")
    status.add_argument("target", type=Path)
    run = operations.add_parser("dispatch")
    run.add_argument("--invoked-as")
    run.add_argument("--target", type=Path)
    run.add_argument("--kind", choices=("git", "codex"))
    run.add_argument("--event")
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Toggle, inspect, or run one repository hook event."""
    options = _parser().parse_args(arguments)
    try:
        if options.operation == "dispatch":
            target, kind, event = invocation_context(
                options.invoked_as,
                options.target,
                options.kind,
                options.event,
            )
            hook_arguments = tuple(options.arguments)
            if hook_arguments[:1] == ("--",):
                hook_arguments = hook_arguments[1:]
            raise SystemExit(dispatch(target, kind, event, hook_arguments))
        target = resolve_target(options.target)
        root, record = _load(target)
        if options.operation == "status":
            result = hook_status(target, root, record)
            result["breaker"] = breaker_status(target, root)
            result["proof"] = proof_status(target, root)
            print(json.dumps(result, sort_keys=True))
            if not result["current"]:
                raise SystemExit(1)
            return
        changed = set_enabled(
            target,
            record,
            options.operation == "enable",
            kind=options.kind,
            event=options.event,
            name=options.entry,
        )
        print("\n".join(changed))
    except (
        DeploymentError,
        GuardrailStateError,
        HookDeploymentError,
        OSError,
        ValueError,
    ) as error:
        print(f"qat-hook-{options.operation}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
