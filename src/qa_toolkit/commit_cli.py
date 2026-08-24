"""Validate one commit message or a Git revision range."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.commit_policy import (
    COCOGITTO_ARGUMENTS,
    is_lifecycle_message,
    render,
    structural_findings,
    terminology_findings,
)
from qa_toolkit.config import load_consumer, load_profile
from qa_toolkit.deployment import DeploymentError, resolve_target, status
from qa_toolkit.models import ConfigurationError
from qa_toolkit.registry import RegistryError, executable_path, select_tools

MAX_MESSAGE_BYTES = 1_048_576


class CommitCheckError(RuntimeError):
    """Report invalid commit selection or tool execution."""


def _git(target: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(target), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise CommitCheckError(f"Git selection failed: {error}") from error
    return completed.stdout


def _message_file(target: Path, path: Path) -> tuple[tuple[str, str], ...]:
    selected = path if path.is_absolute() else target / path
    selected = selected.absolute()
    git = (target / ".git").resolve()
    if git not in selected.parents or selected.is_symlink() or not selected.is_file():
        raise CommitCheckError("commit message file must be a regular file below target .git")
    if selected.stat().st_size > MAX_MESSAGE_BYTES:
        raise CommitCheckError("commit message exceeds one MiB")
    return (("COMMIT_EDITMSG", selected.read_text(encoding="utf-8")),)


def _revisions(target: Path, selection: str, range_selection: bool) -> tuple[tuple[str, str], ...]:
    if not selection or len(selection) > 512 or any(ord(character) < 32 for character in selection):
        raise CommitCheckError("invalid commit selection")
    revisions = (
        _git(target, "rev-list", "--reverse", selection).splitlines()
        if range_selection
        else [_git(target, "rev-parse", "--verify", f"{selection}^{{commit}}").strip()]
    )
    return tuple(
        (revision, _git(target, "show", "-s", "--format=%B", revision)) for revision in revisions
    )


def _cog(target: Path, root: Path, message: str) -> int:
    tool = select_tools(["cocogitto"], root)[0]
    executable = executable_path(tool, root)
    temporary_root = target / ".git" / "qat" / "temporary"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cog-", dir=temporary_root) as raw:
        temporary = Path(raw)
        config = temporary / ".gitconfig"
        config.write_text(
            "[user]\n\tname = qa-toolkit\n\temail = qa-toolkit@example.invalid\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": str(config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "XDG_CONFIG_HOME": str(temporary),
            }
        )
        try:
            result = subprocess.run(
                [str(executable), *COCOGITTO_ARGUMENTS],
                cwd=target,
                env=environment,
                input=message,
                check=False,
                text=True,
                timeout=30,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CommitCheckError(f"cannot execute Cocogitto: {error}") from error
    if result.returncode not in {0, 1}:
        raise CommitCheckError(f"Cocogitto exited with unclassified status {result.returncode}")
    return result.returncode


def check_messages(target: Path, root: Path, messages: tuple[tuple[str, str], ...]) -> int:
    """Validate selected ordinary messages and skip Git lifecycle messages first."""
    failed = False
    for label, message in messages:
        if is_lifecycle_message(message):
            continue
        cog_exit = _cog(target, root, message)
        findings = (*structural_findings(message), *terminology_findings(target, message, root))
        if findings:
            print(render(findings, label), file=sys.stderr)
        failed = failed or cog_exit == 1 or any(item.severity == "error" for item in findings)
    return 1 if failed else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-commits")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--message-file", type=Path)
    selection.add_argument("--range")
    selection.add_argument("--commit")
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Validate selected commit messages through Cocogitto and the shared corpus."""
    options = _parser().parse_args(arguments)
    try:
        target = resolve_target(options.target)
        deployment = status(target)
        if not deployment["current"]:
            raise CommitCheckError("repository deployment is stale; run qat repo sync")
        root = Path(__file__).resolve().parents[2]
        profile = load_profile(load_consumer(target).profile, root)
        if "cocogitto" not in profile.tools:
            raise CommitCheckError("selected profile does not own Cocogitto")
        if options.message_file is not None:
            messages = _message_file(target, options.message_file)
        elif options.range is not None:
            messages = _revisions(target, options.range, True)
        else:
            messages = _revisions(target, options.commit, False)
        raise SystemExit(check_messages(target, root, messages))
    except (
        CommitCheckError,
        ConfigurationError,
        DeploymentError,
        OSError,
        RegistryError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"qat-commits: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
