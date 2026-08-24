"""Repository-local agent helpers for GitHub records and deterministic thread names."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.github import GitHubClient

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TASK = re.compile(r"^C[0-9]{2}$")


def thread_name(repository: str, issue: int, task: str, title: str) -> str:
    """Return one bounded repository-qualified user-visible thread name."""
    if _REPOSITORY.fullmatch(repository) is None or issue < 1 or _TASK.fullmatch(task) is None:
        raise ValueError("invalid thread identity")
    repository_name = repository.split("/", 1)[1]
    value = f"[{repository_name}#{issue} {task}] {title}"
    if not title.strip() or len(value) > 200 or any(ord(item) < 32 for item in value):
        raise ValueError("invalid thread title")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-agent")
    operations = parser.add_subparsers(dest="operation", required=True)
    thread = operations.add_parser("thread-name")
    thread.add_argument("--repository", required=True)
    thread.add_argument("--issue", type=int, required=True)
    thread.add_argument("--task", required=True)
    thread.add_argument("--title", required=True)
    github = operations.add_parser("github")
    github.add_argument(
        "command",
        choices=(
            "repository",
            "issue-view",
            "issue-create",
            "issue-update",
            "pr-view",
            "pr-create",
            "pr-update",
            "pr-checks",
            "pr-comment",
            "pr-ready",
        ),
    )
    github.add_argument("--repository", required=True)
    github.add_argument("--number", type=int)
    github.add_argument("--title")
    github.add_argument("--body-file", type=Path)
    github.add_argument("--head")
    github.add_argument("--base")
    return parser


def _number(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"--{name.replace('_', '-')} is required")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"--{name.replace('_', '-')} is required")
    return value


def _path(value: object, name: str) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"--{name.replace('_', '-')} is required")
    return value


def _github(options: argparse.Namespace) -> object:
    client = GitHubClient.discover()
    repository = options.repository
    command = options.command
    if command == "repository":
        return {"repository": client.repository(repository)}
    if command == "issue-view":
        return client.issue(repository, _number(options.number, "number")).as_dict()
    if command == "issue-create":
        return client.create_issue(
            repository,
            title=_string(options.title, "title"),
            body_file=_path(options.body_file, "body_file"),
        ).as_dict()
    if command == "issue-update":
        return client.update_issue(
            repository,
            _number(options.number, "number"),
            title=_string(options.title, "title"),
            body_file=_path(options.body_file, "body_file"),
        ).as_dict()
    if command == "pr-view":
        return client.pull_request(repository, _number(options.number, "number")).as_dict()
    if command == "pr-create":
        return client.create_pull_request(
            repository,
            head=_string(options.head, "head"),
            base=_string(options.base, "base"),
            title=_string(options.title, "title"),
            body_file=_path(options.body_file, "body_file"),
        ).as_dict()
    if command == "pr-update":
        return client.update_pull_request(
            repository,
            _number(options.number, "number"),
            title=_string(options.title, "title"),
            body_file=_path(options.body_file, "body_file"),
        ).as_dict()
    if command == "pr-checks":
        return [
            item.as_dict() for item in client.checks(repository, _number(options.number, "number"))
        ]
    if command == "pr-comment":
        return client.comment(
            repository,
            _number(options.number, "number"),
            body_file=_path(options.body_file, "body_file"),
        ).as_dict()
    return client.ready(repository, _number(options.number, "number")).as_dict()


def main(arguments: Sequence[str] | None = None) -> None:
    """Run one bounded agent helper without implicit remote mutations."""
    options = _parser().parse_args(arguments)
    try:
        if options.operation == "thread-name":
            result: object = {
                "name": thread_name(options.repository, options.issue, options.task, options.title)
            }
        else:
            result = _github(options)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        print(f"qat-agent-{options.operation}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
