"""Closed repository-local state for deterministic work packages."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from qa_toolkit.commit_policy import structural_findings
from qa_toolkit.config import load_consumer
from qa_toolkit.deployment import resolve_target
from qa_toolkit.filesystem import atomic_bytes
from qa_toolkit.strict_json import strict_json_loads

SCHEMA_VERSION = 1
TEMPLATE_NAMES = frozenset({"plan", "breakdown", "reconcile", "cleanup", "release"})
MAX_MARKDOWN_BYTES = 1_048_576
MAX_JSON_BYTES = 262_144

_WORK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TASK_ID = re.compile(r"^C[0-9]{2}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PHASES = frozenset(
    {"accepted", "staged", "executing", "publishing", "complete", "cleanup", "retired"}
)
_KINDS = frozenset({"feature", "refactor", "release"})
_PROOFS = frozenset({"check", "sentinel"})
_FILES = ("PLAN.md", "TASK.md", "result.json", "state.json")
_IMMUTABLE = (
    "repository",
    "issue",
    "remote",
    "work_id",
    "kind",
    "branch",
    "base_branch",
    "base_sha",
)


class WorkError(RuntimeError):
    """Report a malformed state boundary or unsafe work transition."""


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    """One exact validation invocation and retained local output."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> ValidationRecord:
        """Parse a closed validation record."""
        _exact(raw, {"argv", "exit_code", "stdout", "stderr"}, "validation record")
        commands = _commands([raw.get("argv")])
        code = raw.get("exit_code")
        if not isinstance(code, int) or isinstance(code, bool) or code < 0:
            raise WorkError("validation exit_code must be a non-negative integer")
        return cls(
            commands[0],
            code,
            _relative_file(raw.get("stdout"), "stdout"),
            _relative_file(raw.get("stderr"), "stderr"),
        )

    def as_dict(self) -> dict[str, object]:
        """Return the exact JSON representation."""
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class WorkResult:
    """Result of the current task, separate from human plan prose."""

    work_id: str
    task_id: str
    commands: tuple[ValidationRecord, ...]
    changed_paths: tuple[str, ...]
    evidence_references: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> WorkResult:
        """Parse a closed result object."""
        _exact(
            raw,
            {
                "schema_version",
                "work_id",
                "task_id",
                "commands",
                "changed_paths",
                "evidence_references",
            },
            "work result",
        )
        _schema(raw.get("schema_version"), "work result")
        records = raw.get("commands")
        if not isinstance(records, list):
            raise WorkError("work result commands must be an array")
        return cls(
            work_id=_match(raw.get("work_id"), "work_id", _WORK_ID),
            task_id=_match(raw.get("task_id"), "task_id", _TASK_ID),
            commands=tuple(
                ValidationRecord.parse(_object(item, "validation record")) for item in records
            ),
            changed_paths=_paths(raw.get("changed_paths"), allow_empty=True),
            evidence_references=_strings(raw.get("evidence_references"), "evidence_references"),
        )

    def as_dict(self) -> dict[str, object]:
        """Return the exact JSON representation."""
        return {
            "schema_version": self.schema_version,
            "work_id": self.work_id,
            "task_id": self.task_id,
            "commands": [item.as_dict() for item in self.commands],
            "changed_paths": list(self.changed_paths),
            "evidence_references": list(self.evidence_references),
        }


@dataclass(frozen=True, slots=True)
class WorkState:
    """Authoritative identity and transition state for one work package."""

    repository: str
    issue: int
    pull_request: int | None
    remote: str
    work_id: str
    kind: str
    phase: str
    branch: str
    base_branch: str
    base_sha: str
    plan_revision: int
    current_task: str
    task_title: str
    expected_parent: str
    final_subject: str
    allowed_paths: tuple[str, ...]
    validation_argv: tuple[tuple[str, ...], ...]
    quality_proof: str
    retire_after_finish: bool
    provisional_sha: str | None
    final_sha: str | None
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> WorkState:
        """Parse one closed state object without consulting human prose."""
        fields = {
            "schema_version",
            "repository",
            "issue",
            "pull_request",
            "remote",
            "work_id",
            "kind",
            "phase",
            "branch",
            "base_branch",
            "base_sha",
            "plan_revision",
            "current_task",
            "task_title",
            "expected_parent",
            "final_subject",
            "allowed_paths",
            "validation_argv",
            "quality_proof",
            "retire_after_finish",
            "provisional_sha",
            "final_sha",
        }
        _exact(raw, fields, "work state")
        _schema(raw.get("schema_version"), "work state")
        subject = _text(raw.get("final_subject"), "final_subject", 100)
        if structural_findings(subject):
            raise WorkError("final_subject must satisfy the managed commit-message policy")
        state = cls(
            repository=_match(raw.get("repository"), "repository", _REPOSITORY),
            issue=_positive(raw.get("issue"), "issue"),
            pull_request=_optional_positive(raw.get("pull_request"), "pull_request"),
            remote=_match(raw.get("remote"), "remote", _REMOTE),
            work_id=_match(raw.get("work_id"), "work_id", _WORK_ID),
            kind=_choice(raw.get("kind"), "kind", _KINDS),
            phase=_choice(raw.get("phase"), "phase", _PHASES),
            branch=_branch(raw.get("branch"), "branch"),
            base_branch=_branch(raw.get("base_branch"), "base_branch"),
            base_sha=_match(raw.get("base_sha"), "base_sha", _SHA),
            plan_revision=_positive(raw.get("plan_revision"), "plan_revision"),
            current_task=_match(raw.get("current_task"), "current_task", _TASK_ID),
            task_title=_text(raw.get("task_title"), "task_title", 120),
            expected_parent=_match(raw.get("expected_parent"), "expected_parent", _SHA),
            final_subject=subject,
            allowed_paths=_paths(raw.get("allowed_paths")),
            validation_argv=_commands(raw.get("validation_argv")),
            quality_proof=_choice(raw.get("quality_proof"), "quality_proof", _PROOFS),
            retire_after_finish=_boolean(raw.get("retire_after_finish"), "retire_after_finish"),
            provisional_sha=_optional_sha(raw.get("provisional_sha"), "provisional_sha"),
            final_sha=_optional_sha(raw.get("final_sha"), "final_sha"),
        )
        _quality_command(state.validation_argv, state.quality_proof)
        if state.retire_after_finish and state.quality_proof != "sentinel":
            raise WorkError("retirement tasks require Sentinel proof")
        if state.phase not in {"accepted", "cleanup"} and state.provisional_sha is None:
            raise WorkError(f"work phase {state.phase} requires provisional_sha")
        if state.phase in {"publishing", "complete", "retired"} and state.final_sha is None:
            raise WorkError(f"work phase {state.phase} requires final_sha")
        if state.phase not in {"accepted", "cleanup", "staged"} and state.pull_request is None:
            raise WorkError(f"work phase {state.phase} requires pull_request")
        return state

    def as_dict(self) -> dict[str, object]:
        """Return the exact JSON representation."""
        return {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "issue": self.issue,
            "pull_request": self.pull_request,
            "remote": self.remote,
            "work_id": self.work_id,
            "kind": self.kind,
            "phase": self.phase,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "plan_revision": self.plan_revision,
            "current_task": self.current_task,
            "task_title": self.task_title,
            "expected_parent": self.expected_parent,
            "final_subject": self.final_subject,
            "allowed_paths": list(self.allowed_paths),
            "validation_argv": [list(item) for item in self.validation_argv],
            "quality_proof": self.quality_proof,
            "retire_after_finish": self.retire_after_finish,
            "provisional_sha": self.provisional_sha,
            "final_sha": self.final_sha,
        }


@dataclass(frozen=True, slots=True)
class WorkPackage:
    """Validated local files for one work package."""

    root: Path
    plan: str
    task: str
    state: WorkState
    result: WorkResult

    @classmethod
    def load(cls, target_value: Path, work_id: str) -> WorkPackage:
        """Load one package from the enrolled target's configured local state."""
        target = enrolled_target(target_value)
        root = package_root(target, work_id)
        _artifact_directory(root)
        plan = _read_text(root / "PLAN.md", MAX_MARKDOWN_BYTES, "plan")
        task = _read_text(root / "TASK.md", MAX_MARKDOWN_BYTES, "task")
        state = WorkState.parse(_json_object(root / "state.json", "work state"))
        result = WorkResult.parse(_json_object(root / "result.json", "work result"))
        if state.work_id != work_id or result.work_id != work_id:
            raise WorkError("work identity does not match its directory")
        if result.task_id != state.current_task:
            raise WorkError("work result task does not match current_task")
        return cls(root, plan, task, state, result)


def enrolled_target(value: Path) -> Path:
    """Require one enrolled target with repository-local state."""
    target = resolve_target(value)
    deployment = target / ".git" / "qat" / "deployment.json"
    if deployment.is_symlink() or not deployment.is_file():
        raise WorkError("work package requires an enrolled repository")
    return target


def package_root(target: Path, work_id: str) -> Path:
    """Resolve the configured local directory for one bounded work identifier."""
    identifier = _match(work_id, "work_id", _WORK_ID)
    consumer = load_consumer(target)
    root = target / consumer.work_state_directory / identifier
    state_root = (target / ".git" / "qat").resolve()
    try:
        root.resolve(strict=False).relative_to(state_root)
    except ValueError as error:
        raise WorkError("work state directory must remain below .git/qat") from error
    _no_symlink_components(state_root, root)
    return root


def canonical_json(value: Mapping[str, object]) -> bytes:
    """Encode one state object deterministically."""
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_package(root: Path, plan: str, task: str, state: WorkState, result: WorkResult) -> None:
    """Atomically write the four fixed local package files."""
    root.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "PLAN.md": plan.encode(),
        "TASK.md": task.encode(),
        "state.json": canonical_json(state.as_dict()),
        "result.json": canonical_json(result.as_dict()),
    }.items():
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise WorkError(f"refusing substituted work file: {path}")
        atomic_bytes(path, content)


def write_state(root: Path, state: WorkState) -> None:
    """Atomically replace only authoritative transition state."""
    path = root / "state.json"
    if path.is_symlink():
        raise WorkError("refusing symlinked work state")
    atomic_bytes(path, canonical_json(state.as_dict()))


def write_result(root: Path, result: WorkResult) -> None:
    """Atomically replace only structured task results."""
    path = root / "result.json"
    if path.is_symlink():
        raise WorkError("refusing symlinked work result")
    atomic_bytes(path, canonical_json(result.as_dict()))


def read_markdown(path: Path, label: str) -> str:
    """Read bounded human input that cannot supply transition fields."""
    value = _read_text(path, MAX_MARKDOWN_BYTES, label)
    if not value.strip():
        raise WorkError(f"{label} is empty")
    return value


def immutable_changes(before: WorkState, after: WorkState) -> tuple[str, ...]:
    """Return changed package identity fields."""
    return tuple(field for field in _IMMUTABLE if getattr(before, field) != getattr(after, field))


def _artifact_directory(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise WorkError(f"work-package directory is unavailable: {root}")
    if tuple(sorted(item.name for item in root.iterdir() if item.name != "evidence")) != tuple(
        sorted(_FILES)
    ):
        raise WorkError("work-package directory contains unexpected state files")


def _read_text(path: Path, maximum: int, label: str) -> str:
    if path.is_symlink():
        raise WorkError(f"refusing symlinked {label}")
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise WorkError(f"invalid or excessive {label}")
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        raise WorkError(f"cannot read {label}: {error}") from error


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        return _object(strict_json_loads(_read_text(path, MAX_JSON_BYTES, label)), label)
    except (json.JSONDecodeError, ValueError) as error:
        raise WorkError(f"invalid {label}: {error}") from error


def _no_symlink_components(base: Path, path: Path) -> None:
    try:
        relative = path.relative_to(base)
    except ValueError as error:
        raise WorkError("work path escapes local state") from error
    current = base
    for part in relative.parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise WorkError(f"refusing symlinked work path: {current}")


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise WorkError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _exact(raw: Mapping[str, object], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(raw))
    unknown = sorted(set(raw) - fields)
    if missing or unknown:
        detail = [f"missing {', '.join(missing)}" if missing else ""]
        detail.append(f"unknown {', '.join(unknown)}" if unknown else "")
        raise WorkError(f"{label} fields are invalid: {'; '.join(item for item in detail if item)}")


def _schema(value: object, label: str) -> None:
    if value != SCHEMA_VERSION or isinstance(value, bool):
        raise WorkError(f"{label} requires schema_version = {SCHEMA_VERSION}")


def _match(value: object, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise WorkError(f"invalid work {field}")
    return value


def _choice(value: object, field: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise WorkError(f"invalid work {field}")
    return value


def _positive(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WorkError(f"work {field} must be a positive integer")
    return value


def _optional_positive(value: object, field: str) -> int | None:
    return None if value is None else _positive(value, field)


def _optional_sha(value: object, field: str) -> str | None:
    return None if value is None else _match(value, field, _SHA)


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise WorkError(f"work {field} must be a boolean")
    return value


def _text(value: object, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise WorkError(f"invalid work {field}")
    return value


def _branch(value: object, field: str) -> str:
    branch = _text(value, field, 244)
    if (
        branch.startswith(("/", "."))
        or branch.endswith(("/", ".", ".lock"))
        or any(item in branch for item in ("..", "@{", "\\", "//"))
        or any(character in branch for character in " ~^:?*[")
    ):
        raise WorkError(f"invalid work {field}")
    return branch


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item or any(ord(character) < 32 for character in item)
        for item in value
    ):
        raise WorkError(f"work {field} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise WorkError(f"work {field} must not contain duplicates")
    return tuple(value)


def _relative_file(value: object, field: str) -> str:
    values = _paths([value])
    if values[0].endswith("/"):
        raise WorkError(f"work {field} must name a file")
    return values[0]


def _paths(value: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    paths = _strings(value, "paths")
    if not paths and not allow_empty:
        raise WorkError("work paths must not be empty")
    result = []
    for raw in paths:
        directory = raw.endswith("/")
        candidate = PurePosixPath(raw[:-1] if directory else raw)
        if (
            candidate.is_absolute()
            or not candidate.parts
            or any(part in {"", ".", ".."} for part in candidate.parts)
            or any(character in raw for character in "*?[\\")
        ):
            raise WorkError(f"work path must be a bounded literal: {raw}")
        canonical = candidate.as_posix() + ("/" if directory else "")
        if canonical != raw or candidate.parts[0] == ".git":
            raise WorkError(f"invalid work path: {raw}")
        if raw.startswith((".qat/", ".codex/hooks", ".agents/skills")):
            raise WorkError(f"work path is toolkit-owned: {raw}")
        result.append(raw)
    return tuple(result)


def _commands(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or not value:
        raise WorkError("validation_argv must be a non-empty array")
    commands = []
    for raw in value:
        if not isinstance(raw, list) or not raw or len(raw) > 64:
            raise WorkError("each validation command must be a non-empty argv array")
        command = []
        for argument in raw:
            if (
                not isinstance(argument, str)
                or not argument
                or len(argument) > 4096
                or any(character in argument for character in "\x00\r\n")
            ):
                raise WorkError("validation argv contains an invalid argument")
            command.append(argument)
        commands.append(tuple(command))
    return tuple(commands)


def _quality_command(commands: Sequence[Sequence[str]], proof: str) -> None:
    required = "sentinel" if proof == "sentinel" else "check"
    if not any(
        command[:2] == ("qat", required)
        or (command and Path(command[0]).name == f"qat-{required}")
        or any(
            tuple(command[index : index + 2]) == ("qat", required)
            for index in range(len(command) - 1)
        )
        for command in commands
    ):
        raise WorkError(f"{proof} proof requires a qat {required} validation")
