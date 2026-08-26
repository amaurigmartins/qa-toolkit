"""Convenience dispatcher for the small ``qat-*`` utilities."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_MENU = """usage: qat <command> [arguments]

Quality gates:
  check | sentinel | advisory | commits

Central tools:
  tool list | status | fetch | update

Repositories:
  profile validate
  repo enroll | sync | status | unenroll

Hooks:
  hook enable | disable | status | dispatch

Text and evidence:
  corpus build
  evidence show | export

Work packages:
  work init | stage | bind | reconcile | finish | status
  work report | retire | release | template

Agent helpers:
  agent github | thread-name

Run `qat <command> --help` for command arguments."""


def _command_name(arguments: list[str]) -> tuple[str, list[str]]:
    """Translate a grouped command into its corresponding utility name."""
    if not arguments:
        raise ValueError(_MENU)

    group = arguments[0]
    if group in {"check", "sentinel", "advisory", "commits"}:
        return f"qat-{group}", arguments[1:]
    if len(arguments) < 2:
        raise ValueError(f"usage: qat {group} <operation> [arguments]")
    return f"qat-{group}-{arguments[1]}", arguments[2:]


def main() -> None:
    """Execute the selected utility without an intermediate shell."""
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(_MENU)
        return
    try:
        command, arguments = _command_name(sys.argv[1:])
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error

    root = Path(__file__).resolve().parents[2]
    local_command = root / "bin" / command
    executable = str(local_command) if local_command.is_file() else command
    os.execvp(executable, [executable, *arguments])


if __name__ == "__main__":
    main()
