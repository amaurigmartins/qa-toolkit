"""Small profile and repository deployment command surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.config import profile_summary
from qa_toolkit.deployment import DeploymentError, enroll, status, sync, unenroll, validate_profile
from qa_toolkit.hook_deployment import HookDeploymentError
from qa_toolkit.models import ConfigurationError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-repo")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    profile = subparsers.add_parser("profile-validate")
    profile.add_argument("profile")
    for operation in ("enroll", "status"):
        command = subparsers.add_parser(operation)
        command.add_argument("target", type=Path)
        if operation == "enroll":
            command.add_argument("--adopt-hooks", action="store_true")
    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("target", type=Path)
    sync_parser.add_argument("--hard-reset", action="store_true")
    sync_parser.add_argument("--adopt-hooks", action="store_true")
    unenroll_parser = subparsers.add_parser("unenroll")
    unenroll_parser.add_argument("target", type=Path)
    unenroll_parser.add_argument("--backup", type=Path)
    unenroll_parser.add_argument("--hard-reset", action="store_true")
    unenroll_parser.add_argument("--purge-config", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Run one profile or repository deployment operation."""
    options = _parser().parse_args(arguments)
    try:
        if options.operation == "profile-validate":
            print(profile_summary(validate_profile(options.profile)))
        elif options.operation == "enroll":
            print(
                json.dumps(
                    enroll(options.target, adopt_hooks=options.adopt_hooks),
                    sort_keys=True,
                )
            )
        elif options.operation == "sync":
            print(
                json.dumps(
                    sync(
                        options.target,
                        hard_reset=options.hard_reset,
                        adopt_hooks=options.adopt_hooks,
                    ),
                    sort_keys=True,
                )
            )
        elif options.operation == "status":
            result = status(options.target)
            print(json.dumps(result, sort_keys=True))
            if not result["current"]:
                raise SystemExit(1)
        else:
            unenroll(
                options.target,
                backup=options.backup,
                hard_reset=options.hard_reset,
                purge_config=options.purge_config,
            )
    except (DeploymentError, HookDeploymentError, ConfigurationError) as error:
        print(f"qat-{options.operation}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
