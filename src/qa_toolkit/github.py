"""Strict non-interactive use of the accepted central GitHub CLI."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qa_toolkit.paths import payload_root
from qa_toolkit.strict_json import (
    require_json_array as _array,
)
from qa_toolkit.strict_json import (
    require_json_boolean as _boolean,
)
from qa_toolkit.strict_json import (
    require_json_object as _object,
)
from qa_toolkit.strict_json import (
    require_json_string as _string,
)
from qa_toolkit.strict_json import (
    strict_json_loads,
)

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,243}$")
_URL_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/(issues|pull)/([1-9][0-9]*)$")
_MAX_OUTPUT = 4 * 1024 * 1024
_MAX_BODY_BYTES = 1_048_576
_TIMEOUT = 60
_SAFE_ENVIRONMENT_KEYS = frozenset(
    {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR", "USER", "XDG_CONFIG_HOME"}
)


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """One exact GitHub issue identity."""

    repository: str
    number: int
    state: str
    title: str
    url: str

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible issue record."""
        return {
            "repository": self.repository,
            "number": self.number,
            "state": self.state,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class GitHubPullRequest:
    """One exact GitHub pull-request identity and lifecycle state."""

    repository: str
    number: int
    state: str
    draft: bool
    head: str
    base: str
    title: str
    url: str
    closing_issues: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible pull-request record."""
        return {
            "repository": self.repository,
            "number": self.number,
            "state": self.state,
            "draft": self.draft,
            "head": self.head,
            "base": self.base,
            "title": self.title,
            "url": self.url,
            "closing_issues": list(self.closing_issues),
        }


@dataclass(frozen=True, slots=True)
class GitHubCheck:
    """One GitHub check state returned for a pull request."""

    name: str
    state: str
    bucket: str
    workflow: str
    link: str

    def as_dict(self) -> dict[str, str]:
        """Return a stable JSON-compatible check record."""
        return {
            "name": self.name,
            "state": self.state,
            "bucket": self.bucket,
            "workflow": self.workflow,
            "link": self.link,
        }


@dataclass(frozen=True, slots=True)
class GitHubClient:
    """Invoke one absolute ``gh`` executable without prompts or a shell."""

    executable: Path
    environment: dict[str, str]

    @classmethod
    def discover(cls) -> GitHubClient:
        """Discover ``gh`` and retain only required environment inputs."""
        path = payload_root() / "gh" / "bin" / "gh"
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError("the accepted central GitHub CLI is not installed")
        allowed = set(_SAFE_ENVIRONMENT_KEYS) | {
            "GH_CONFIG_DIR",
            "GH_ENTERPRISE_TOKEN",
            "GH_HOST",
            "GH_TOKEN",
            "GITHUB_ENTERPRISE_TOKEN",
            "GITHUB_TOKEN",
        }
        environment = {key: value for key, value in os.environ.items() if key in allowed}
        environment.update({"GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0", "NO_COLOR": "1"})
        return cls(path, environment)

    def repository(self, repository: str) -> str:
        """Require authentication and one unambiguous repository identity."""
        expected = _repository(repository)
        self._run(("auth", "status", "--hostname", "github.com"))
        document = self._run_json(
            ("repo", "view", expected, "--json", "nameWithOwner"),
            "GitHub repository",
        )
        actual = _string(document.get("nameWithOwner"), "GitHub repository.nameWithOwner")
        if actual.casefold() != expected.casefold():
            raise RuntimeError(f"GitHub repository identity mismatch: {actual}")
        return actual

    def issue(self, repository: str, number: int) -> GitHubIssue:
        """Read one exact issue."""
        repository = self.repository(repository)
        return self._issue(repository, number)

    def create_issue(self, repository: str, *, title: str, body_file: Path) -> GitHubIssue:
        """Create one issue only when no exact-title issue already exists."""
        title = _title(title)
        body = _body_file(body_file)
        repository = self.repository(repository)
        existing = self._issue_list(repository, title)
        if existing:
            raise RuntimeError("refusing duplicate exact-title GitHub issue")
        output = self._run(
            (
                "issue",
                "create",
                "--repo",
                repository,
                "--title",
                title,
                "--body-file",
                str(body),
            )
        ).stdout.strip()
        number = _created_number(output, repository, "issues")
        issue = self._issue(repository, number)
        if issue.title != title or issue.state != "OPEN":
            raise RuntimeError("created GitHub issue identity did not converge")
        return issue

    def update_issue(
        self, repository: str, number: int, *, title: str, body_file: Path
    ) -> GitHubIssue:
        """Update one exact open issue and verify its identity."""
        title = _title(title)
        body = _body_file(body_file)
        repository = self.repository(repository)
        issue = self._issue(repository, number)
        if issue.state != "OPEN":
            raise RuntimeError("managed work-package issue is not open")
        self._run(
            (
                "issue",
                "edit",
                str(number),
                "--repo",
                repository,
                "--title",
                title,
                "--body-file",
                str(body),
            )
        )
        updated = self._issue(repository, number)
        if updated.title != title:
            raise RuntimeError("updated GitHub issue title did not converge")
        return updated

    def pull_request(self, repository: str, number: int) -> GitHubPullRequest:
        """Read one exact pull request."""
        repository = self.repository(repository)
        return self._pull_request(repository, number)

    def create_pull_request(
        self,
        repository: str,
        *,
        head: str,
        base: str,
        title: str,
        body_file: Path,
    ) -> GitHubPullRequest:
        """Create one draft pull request after rejecting duplicate head branches."""
        head = _branch(head)
        base = _branch(base)
        title = _title(title)
        body = _body_file(body_file)
        repository = self.repository(repository)
        if self._pull_request_list(repository, head):
            raise RuntimeError("refusing duplicate GitHub pull request for head branch")
        output = self._run(
            (
                "pr",
                "create",
                "--repo",
                repository,
                "--head",
                head,
                "--base",
                base,
                "--title",
                title,
                "--body-file",
                str(body),
                "--draft",
            )
        ).stdout.strip()
        number = _created_number(output, repository, "pull")
        pull_request = self._pull_request(repository, number)
        if (
            pull_request.state != "OPEN"
            or not pull_request.draft
            or pull_request.head != head
            or pull_request.base != base
            or pull_request.title != title
        ):
            raise RuntimeError("created GitHub pull-request identity did not converge")
        return pull_request

    def update_pull_request(
        self, repository: str, number: int, *, title: str, body_file: Path
    ) -> GitHubPullRequest:
        """Update one exact open pull request and verify its title."""
        title = _title(title)
        body = _body_file(body_file)
        repository = self.repository(repository)
        pull_request = self._pull_request(repository, number)
        if pull_request.state != "OPEN":
            raise RuntimeError("managed pull request is not open")
        self._run(
            (
                "pr",
                "edit",
                str(number),
                "--repo",
                repository,
                "--title",
                title,
                "--body-file",
                str(body),
            )
        )
        updated = self._pull_request(repository, number)
        if updated.title != title:
            raise RuntimeError("updated GitHub pull-request title did not converge")
        return updated

    def checks(self, repository: str, number: int) -> tuple[GitHubCheck, ...]:
        """Read bounded CI states for one exact pull request."""
        repository = self.repository(repository)
        self._pull_request(repository, number)
        result = self._run(
            (
                "pr",
                "checks",
                str(number),
                "--repo",
                repository,
                "--json",
                "name,state,bucket,workflow,link",
            ),
            allowed_statuses=frozenset({0, 1, 8}),
        )
        records = _array(_json(result.stdout, "GitHub checks"), "GitHub checks")
        return tuple(_check(raw, index) for index, raw in enumerate(records))

    def comment(self, repository: str, number: int, *, body_file: Path) -> GitHubPullRequest:
        """Comment on one exact open pull request using a bounded body file."""
        body = _body_file(body_file)
        repository = self.repository(repository)
        pull_request = self._pull_request(repository, number)
        if pull_request.state != "OPEN":
            raise RuntimeError("cannot report to a closed pull request")
        self._run(
            (
                "pr",
                "comment",
                str(number),
                "--repo",
                repository,
                "--body-file",
                str(body),
            )
        )
        return self._pull_request(repository, number)

    def ready(self, repository: str, number: int) -> GitHubPullRequest:
        """Mark one exact draft pull request ready without merging it."""
        repository = self.repository(repository)
        pull_request = self._pull_request(repository, number)
        if pull_request.state != "OPEN" or not pull_request.draft:
            raise RuntimeError("pull request is not an open draft")
        self._run(("pr", "ready", str(number), "--repo", repository))
        ready = self._pull_request(repository, number)
        if ready.state != "OPEN" or ready.draft:
            raise RuntimeError("GitHub pull request did not become ready")
        return ready

    def _issue(self, repository: str, number: int) -> GitHubIssue:
        number = _positive_number(number, "issue")
        document = self._run_json(
            (
                "issue",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                "number,state,title,url",
            ),
            "GitHub issue",
        )
        return _issue_record(document, repository, number)

    def _issue_list(self, repository: str, title: str) -> tuple[GitHubIssue, ...]:
        value = self._run_json_value(
            (
                "issue",
                "list",
                "--repo",
                repository,
                "--state",
                "all",
                "--search",
                f'"{title}" in:title',
                "--limit",
                "100",
                "--json",
                "number,state,title,url",
            ),
            "GitHub issue list",
        )
        records = _array(value, "GitHub issue list")
        parsed = tuple(
            _issue_record(_object(raw, f"GitHub issue list[{index}]"), repository)
            for index, raw in enumerate(records)
        )
        return tuple(issue for issue in parsed if issue.title == title)

    def _pull_request(self, repository: str, number: int) -> GitHubPullRequest:
        number = _positive_number(number, "pull request")
        document = self._run_json(
            (
                "pr",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                "number,state,isDraft,headRefName,baseRefName,title,url,closingIssuesReferences",
            ),
            "GitHub pull request",
        )
        return _pull_request_record(document, repository, number)

    def _pull_request_list(self, repository: str, head: str) -> tuple[GitHubPullRequest, ...]:
        value = self._run_json_value(
            (
                "pr",
                "list",
                "--repo",
                repository,
                "--state",
                "all",
                "--head",
                head,
                "--limit",
                "100",
                "--json",
                "number,state,isDraft,headRefName,baseRefName,title,url,closingIssuesReferences",
            ),
            "GitHub pull-request list",
        )
        records = _array(value, "GitHub pull-request list")
        parsed = tuple(
            _pull_request_record(_object(raw, f"GitHub pull-request list[{index}]"), repository)
            for index, raw in enumerate(records)
        )
        return tuple(pull_request for pull_request in parsed if pull_request.head == head)

    def _run_json(self, argv: tuple[str, ...], label: str) -> dict[str, Any]:
        return _object(self._run_json_value(argv, label), label)

    def _run_json_value(self, argv: tuple[str, ...], label: str) -> object:
        return _json(self._run(argv).stdout, label)

    def _run(
        self,
        argv: tuple[str, ...],
        *,
        allowed_statuses: frozenset[int] = frozenset({0}),
    ) -> subprocess.CompletedProcess[str]:
        return _run_github_command(
            self.executable,
            self.environment,
            argv,
            allowed_statuses=allowed_statuses,
        )


def _run_github_command(
    executable: Path,
    environment: dict[str, str],
    argv: tuple[str, ...],
    *,
    allowed_statuses: frozenset[int],
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            (str(executable), *argv),
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=_TIMEOUT,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"GitHub CLI {' '.join(argv)} failed: {exc}") from exc
    if len(result.stdout.encode()) + len(result.stderr.encode()) > _MAX_OUTPUT:
        raise RuntimeError("GitHub CLI output exceeds its size limit")
    if result.returncode not in allowed_statuses:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise RuntimeError(f"GitHub CLI {' '.join(argv)} failed ({result.returncode}): {detail}")
    return result


def _json(content: str, label: str) -> object:
    try:
        return strict_json_loads(content)
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"malformed {label} JSON: {exc}") from exc


def _repository(value: str) -> str:
    if not isinstance(value, str) or _REPOSITORY_RE.fullmatch(value) is None:
        raise RuntimeError("invalid GitHub repository identity")
    owner, name = value.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise RuntimeError("invalid GitHub repository identity")
    return value


def _positive_number(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RuntimeError(f"invalid GitHub {label} number")
    return value


def _title(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or '"' in value
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeError("invalid GitHub title")
    return value


def _branch(value: str) -> str:
    if (
        not isinstance(value, str)
        or _BRANCH_RE.fullmatch(value) is None
        or value.endswith(("/", ".", ".lock"))
        or ".." in value
        or "//" in value
    ):
        raise RuntimeError("invalid GitHub branch")
    return value


def _body_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"GitHub body is not a regular non-symlink file: {path}")
    if path.stat().st_size > _MAX_BODY_BYTES:
        raise RuntimeError(f"GitHub body exceeds {_MAX_BODY_BYTES} bytes")
    try:
        path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"cannot read UTF-8 GitHub body: {exc}") from exc
    return path.resolve(strict=True)


def _created_number(url: str, repository: str, kind: str) -> int:
    match = _URL_RE.fullmatch(url)
    if match is None:
        raise RuntimeError("GitHub create returned a malformed URL")
    actual_repository, actual_kind, raw_number = match.groups()
    if actual_repository.casefold() != repository.casefold() or actual_kind != kind:
        raise RuntimeError("GitHub create returned a mismatched identity")
    return int(raw_number)


def _issue_record(
    document: dict[str, Any], repository: str, expected_number: int | None = None
) -> GitHubIssue:
    number = _positive_number(document.get("number"), "issue")
    if expected_number is not None and number != expected_number:
        raise RuntimeError("GitHub returned a different issue number")
    state = _choice(document.get("state"), "GitHub issue.state", {"OPEN", "CLOSED"})
    title = _title(_string(document.get("title"), "GitHub issue.title"))
    url = _string(document.get("url"), "GitHub issue.url")
    if _created_number(url, repository, "issues") != number:
        raise RuntimeError("GitHub issue URL identity mismatch")
    return GitHubIssue(repository, number, state, title, url)


def _pull_request_record(
    document: dict[str, Any], repository: str, expected_number: int | None = None
) -> GitHubPullRequest:
    number = _positive_number(document.get("number"), "pull request")
    if expected_number is not None and number != expected_number:
        raise RuntimeError("GitHub returned a different pull-request number")
    state = _choice(
        document.get("state"), "GitHub pull request.state", {"OPEN", "CLOSED", "MERGED"}
    )
    draft = _boolean(document.get("isDraft"), "GitHub pull request.isDraft")
    head = _branch(_string(document.get("headRefName"), "GitHub pull request.headRefName"))
    base = _branch(_string(document.get("baseRefName"), "GitHub pull request.baseRefName"))
    title = _title(_string(document.get("title"), "GitHub pull request.title"))
    url = _string(document.get("url"), "GitHub pull request.url")
    if _created_number(url, repository, "pull") != number:
        raise RuntimeError("GitHub pull-request URL identity mismatch")
    raw_closing = _array(
        document.get("closingIssuesReferences"),
        "GitHub pull request.closingIssuesReferences",
    )
    closing = tuple(
        _positive_number(
            _object(raw, f"GitHub closing issue[{index}]").get("number"),
            "closing issue",
        )
        for index, raw in enumerate(raw_closing)
    )
    if len(set(closing)) != len(closing):
        raise RuntimeError("GitHub pull request returned duplicate closing issues")
    return GitHubPullRequest(repository, number, state, draft, head, base, title, url, closing)


def _check(value: object, index: int) -> GitHubCheck:
    label = f"GitHub check[{index}]"
    document = _object(value, label)
    bucket = _choice(
        document.get("bucket"), f"{label}.bucket", {"pass", "fail", "pending", "skipping", "cancel"}
    )
    return GitHubCheck(
        name=_string(document.get("name"), f"{label}.name"),
        state=_string(document.get("state"), f"{label}.state"),
        bucket=bucket,
        workflow=_string(document.get("workflow"), f"{label}.workflow"),
        link=_string(document.get("link"), f"{label}.link"),
    )


def _choice(value: object, label: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise RuntimeError(f"{label} has an invalid value")
    return value
