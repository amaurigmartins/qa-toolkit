"""Exact Git transitions for repository-local structured work packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from qa_toolkit.work import (
    SCHEMA_VERSION,
    ValidationRecord,
    WorkError,
    WorkPackage,
    WorkResult,
    WorkState,
    enrolled_target,
    immutable_changes,
    package_root,
    read_markdown,
    write_package,
    write_result,
    write_state,
)

_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_BREAKING = re.compile(r"(?:^[a-z]+(?:\([^\r\n]+\))?!:|^BREAKING[ -]CHANGE:\s*)", re.MULTILINE)
_FEATURE = re.compile(r"^feat(?:\([^\r\n]+\))?!?: ")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_MAX_GIT_OUTPUT = 1_048_576
_MAX_VALIDATION_OUTPUT = 16 * 1024 * 1024
_VALIDATION_TIMEOUT = 3600


@dataclass(frozen=True, slots=True)
class WorkStatus:
    """Local and remote recovery view for one work package."""

    target: Path
    head: str
    branch: str
    remote_head: str | None
    completed_items: tuple[str, ...]
    state: WorkState

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible status."""
        return {
            "schema_version": SCHEMA_VERSION,
            "target": str(self.target),
            "head": self.head,
            "branch": self.branch,
            "remote_head": self.remote_head,
            "completed_items": list(self.completed_items),
            "state": self.state.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReleaseCalculation:
    """Deterministic SemVer decision from accepted commit messages."""

    base_version: str
    next_version: str
    bump: str
    breaking: bool

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible calculation."""
        return {
            "schema_version": SCHEMA_VERSION,
            "base_version": self.base_version,
            "next_version": self.next_version,
            "bump": self.bump,
            "breaking": self.breaking,
        }


def initialize(
    target_value: Path,
    *,
    work_id: str,
    repository: str,
    issue: int,
    pull_request: int | None,
    remote: str,
    kind: str,
    branch: str,
    base_branch: str,
    base_sha: str,
    plan_revision: int,
    task_id: str,
    task_title: str,
    expected_parent: str,
    final_subject: str,
    allowed_paths: Sequence[str],
    validation_argv: Sequence[Sequence[str]],
    quality_proof: str,
    plan_source: Path,
    task_source: Path,
    retire_after_finish: bool = False,
) -> WorkPackage:
    """Create or advance one local package without changing Git state."""
    target = enrolled_target(target_value)
    state = WorkState.parse(
        {
            "schema_version": SCHEMA_VERSION,
            "repository": repository,
            "issue": issue,
            "pull_request": pull_request,
            "remote": remote,
            "work_id": work_id,
            "kind": kind,
            "phase": "cleanup" if retire_after_finish else "accepted",
            "branch": branch,
            "base_branch": base_branch,
            "base_sha": base_sha,
            "plan_revision": plan_revision,
            "current_task": task_id,
            "task_title": task_title,
            "expected_parent": expected_parent,
            "final_subject": final_subject,
            "allowed_paths": list(allowed_paths),
            "validation_argv": [list(item) for item in validation_argv],
            "quality_proof": quality_proof,
            "retire_after_finish": retire_after_finish,
            "provisional_sha": None,
            "final_sha": None,
        }
    )
    if _changes(target):
        raise WorkError("work initialization requires a clean worktree")
    head = _head(target)
    root = package_root(target, work_id)
    if root.exists():
        previous = WorkPackage.load(target, work_id)
        if previous.state.phase != "complete":
            raise WorkError("one active task already exists for this work package")
        changed = immutable_changes(previous.state, state)
        if changed:
            raise WorkError("work identity changed: " + ", ".join(changed))
        if state.pull_request != previous.state.pull_request:
            raise WorkError("work pull-request identity changed")
        if state.plan_revision <= previous.state.plan_revision:
            raise WorkError("plan_revision must increase")
        if _branch(target) != state.branch or head != state.expected_parent:
            raise WorkError("next task must start at the exact workflow branch HEAD")
    elif head != state.base_sha or state.expected_parent != state.base_sha:
        raise WorkError("first task must use the exact current base revision")
    if state.current_task in _completed_items(target, state):
        raise WorkError(f"work item is already complete: {state.current_task}")
    plan = read_markdown(plan_source, "accepted plan")
    task = read_markdown(task_source, "current task")
    result = WorkResult(state.work_id, state.current_task, (), (), ())
    write_package(root, plan, task, state, result)
    return WorkPackage.load(target, work_id)


def stage(target_value: Path, work_id: str) -> WorkStatus:
    """Create and publish one empty provisional commit."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    state = package.state
    if state.phase not in {"accepted", "cleanup"}:
        raise WorkError(f"cannot stage from phase {state.phase}")
    if _head(target) != state.expected_parent or _changes(target):
        raise WorkError("staging requires the exact clean expected parent")
    current = _branch(target)
    if current != state.branch:
        if _local_branch(target, state.branch):
            raise WorkError(f"workflow branch already exists locally: {state.branch}")
        _git(target, ("switch", "-c", state.branch))
    remote_before = _remote_head(target, state.remote, state.branch)
    if remote_before not in {None, state.expected_parent}:
        raise WorkError("remote workflow branch moved away from the expected parent")
    _git(
        target,
        (
            "commit",
            "--allow-empty",
            "-m",
            _provisional_subject(state),
            "-m",
            _trailers(state),
        ),
    )
    provisional = _head(target)
    staged = replace(state, phase="staged", provisional_sha=provisional)
    write_state(package.root, staged)
    _publish_provisional(target, staged, remote_before)
    return status(target, work_id)


def bind(target_value: Path, work_id: str, pull_request: int) -> WorkStatus:
    """Bind one positive pull-request identity after the draft exists."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    state = package.state
    if state.phase != "staged":
        raise WorkError("pull-request binding requires a staged task")
    if state.pull_request not in {None, pull_request}:
        raise WorkError("work pull-request identity mismatch")
    _require_provisional(target, state)
    if _remote_head(target, state.remote, state.branch) != state.provisional_sha:
        raise WorkError("remote branch is not the exact provisional commit")
    bound = WorkState.parse(state.as_dict() | {"pull_request": pull_request})
    write_state(package.root, bound)
    return status(target, work_id)


def reconcile(target_value: Path, work_id: str, *, pull_request: int | None = None) -> WorkStatus:
    """Recover a staged or publishing task from exact local and remote Git state."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    state = package.state
    if pull_request is not None:
        if state.pull_request not in {None, pull_request}:
            raise WorkError("work pull-request identity mismatch")
        state = WorkState.parse(state.as_dict() | {"pull_request": pull_request})
        write_state(package.root, state)
    head = _head(target)
    remote = _remote_head(target, state.remote, state.branch)
    if state.phase == "staged" and head != state.provisional_sha:
        if _commit_subject(target, head) != state.final_subject or _parents(target, head) != (
            state.expected_parent,
        ):
            raise WorkError("local branch diverged from the staged task")
        state = WorkState.parse(state.as_dict() | {"phase": "publishing", "final_sha": head})
        write_state(package.root, state)
    if state.phase == "staged":
        _require_provisional(target, state)
        if remote in {None, state.expected_parent}:
            _publish_provisional(target, state, remote)
        elif remote != state.provisional_sha:
            raise WorkError("remote branch diverged from the provisional task")
    elif state.phase == "publishing":
        if head != state.final_sha or _commit_subject(target, head) != state.final_subject:
            raise WorkError("local final commit does not match publishing state")
        if remote == state.provisional_sha:
            _lease_publish(target, state, state.provisional_sha)
        elif remote != state.final_sha:
            raise WorkError("remote branch diverged during final publication")
        state = WorkState.parse(state.as_dict() | {"phase": "complete"})
        write_state(package.root, state)
    elif state.phase == "complete":
        if head != state.final_sha or remote != state.final_sha:
            raise WorkError("completed work does not match exact local and remote revisions")
    elif state.phase not in {"accepted", "cleanup"}:
        raise WorkError(f"cannot reconcile phase {state.phase}")
    return status(target, work_id)


def finish(target_value: Path, work_id: str) -> WorkStatus:
    """Validate, amend, and exact-lease publish one staged task."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    if package.state.phase == "publishing":
        return reconcile(target, work_id)
    state = package.state
    if state.phase != "staged" or state.pull_request is None:
        raise WorkError("finish requires a staged task bound to a draft pull request")
    _require_provisional(target, state)
    if _remote_head(target, state.remote, state.branch) != state.provisional_sha:
        raise WorkError("remote branch is not the exact provisional commit")
    if _index_changes(target):
        raise WorkError("finish requires an empty index before managed staging")
    changed = _changes(target)
    if not changed:
        raise WorkError("work item has no implementation changes")
    _validate_paths(target, changed, state.allowed_paths)
    before = _worktree_fingerprint(target)
    executing = WorkState.parse(state.as_dict() | {"phase": "executing"})
    write_state(package.root, executing)
    records, references = _validations(target, package, state.validation_argv)
    result = WorkResult(state.work_id, state.current_task, records, changed, references)
    write_result(package.root, result)
    if any(item.exit_code != 0 for item in records):
        write_state(package.root, state)
        failed = next(item for item in records if item.exit_code != 0)
        raise WorkError(
            f"validation {failed.argv!r} exited {failed.exit_code}; provisional commit preserved"
        )
    if _worktree_fingerprint(target) != before:
        write_state(package.root, state)
        raise WorkError("validation modified the worktree; provisional commit preserved")
    _git(target, ("add", "-A", "--", *changed))
    try:
        _git(
            target,
            ("commit", "--amend", "-m", state.final_subject, "-m", _trailers(state)),
        )
    except WorkError:
        _git(target, ("restore", "--staged", "--", *changed), check=False)
        write_state(package.root, state)
        raise
    final_sha = _head(target)
    publishing = WorkState.parse(state.as_dict() | {"phase": "publishing", "final_sha": final_sha})
    write_state(package.root, publishing)
    _lease_publish(target, publishing, state.provisional_sha)
    complete = WorkState.parse(publishing.as_dict() | {"phase": "complete"})
    write_state(package.root, complete)
    if _changes(target):
        raise WorkError("worktree is not clean after final publication")
    return status(target, work_id)


def retire(target_value: Path, work_id: str) -> str:
    """Remove only a completed package explicitly declared as final cleanup."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    state = package.state
    if state.phase != "complete" or not state.retire_after_finish:
        raise WorkError("retirement requires a completed cleanup task")
    if state.quality_proof != "sentinel" or _changes(target):
        raise WorkError("retirement requires Sentinel proof and a clean worktree")
    if (
        _head(target) != state.final_sha
        or _remote_head(target, state.remote, state.branch) != state.final_sha
    ):
        raise WorkError("retirement requires exact published final state")
    root = package.root
    if root.is_symlink() or root.parent.is_symlink():
        raise WorkError("refusing substituted work state")
    shutil.rmtree(root)
    return str(state.final_sha)


def status(target_value: Path, work_id: str) -> WorkStatus:
    """Read exact local, remote, and completed-task state."""
    target = enrolled_target(target_value)
    package = WorkPackage.load(target, work_id)
    return WorkStatus(
        target,
        _head(target),
        _branch(target),
        _remote_head(target, package.state.remote, package.state.branch),
        _completed_items(target, package.state),
        package.state,
    )


def report(target_value: Path, work_id: str) -> str:
    """Render a bounded factual report from structured state and results."""
    package = WorkPackage.load(target_value, work_id)
    state = package.state
    result = package.result
    lines = [
        f"## {state.work_id} {state.current_task}",
        "",
        f"- Phase: `{state.phase}`",
        f"- Task: {state.task_title}",
        f"- Branch: `{state.branch}`",
        f"- Expected parent: `{state.expected_parent}`",
        f"- Provisional revision: `{state.provisional_sha or 'not staged'}`",
        f"- Final revision: `{state.final_sha or 'not finished'}`",
        f"- Pull request: `#{state.pull_request}`"
        if state.pull_request
        else "- Pull request: unbound",
        f"- Changed paths: {', '.join(f'`{item}`' for item in result.changed_paths) or 'none'}",
        f"- Validation: {sum(item.exit_code == 0 for item in result.commands)}/"
        f"{len(result.commands)} passed",
    ]
    if result.evidence_references:
        lines.append("- Evidence: " + ", ".join(f"`{item}`" for item in result.evidence_references))
    return "\n".join(lines) + "\n"


def calculate_release(base_version: str, messages: Sequence[str]) -> ReleaseCalculation:
    """Calculate the required SemVer increment from commit messages."""
    match = _VERSION.fullmatch(base_version)
    if match is None:
        raise WorkError(f"invalid base version: {base_version}")
    if not messages or any(not item.strip() for item in messages):
        raise WorkError("release calculation requires non-empty commit messages")
    major, minor, patch = (int(item) for item in match.groups())
    breaking = any(_BREAKING.search(item) is not None for item in messages)
    feature = any(_FEATURE.match(item.splitlines()[0]) is not None for item in messages)
    if major == 0:
        bump = "minor" if breaking else "patch"
    elif breaking:
        bump = "major"
    elif feature:
        bump = "minor"
    else:
        bump = "patch"
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return ReleaseCalculation(base_version, f"{major}.{minor}.{patch}", bump, breaking)


def parse_validation(values: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """Parse repeated JSON argv values without shell interpretation."""
    parsed = []
    for value in values:
        try:
            item = json.loads(value)
        except json.JSONDecodeError as error:
            raise WorkError(f"invalid validation argv JSON: {error}") from error
        if not isinstance(item, list) or any(not isinstance(argument, str) for argument in item):
            raise WorkError("each validation value must be an argv string array")
        parsed.append(tuple(item))
    return tuple(parsed)


def _git(
    target: Path,
    argv: tuple[str, ...],
    *,
    check: bool = True,
    timeout: int = 30,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        result = subprocess.run(
            ("git", *argv),
            cwd=target,
            env=environment,
            capture_output=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WorkError(f"Git {' '.join(argv)} failed: {error}") from error
    if len(result.stdout) + len(result.stderr) > _MAX_GIT_OUTPUT:
        raise WorkError(f"Git {' '.join(argv)} produced excessive output")
    if check and result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise WorkError(f"Git {' '.join(argv)} failed: {detail or result.returncode}")
    return result


def _git_text(target: Path, argv: tuple[str, ...]) -> str:
    try:
        return _git(target, argv).stdout.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise WorkError(f"Git {' '.join(argv)} returned non-UTF-8 output") from error


def _head(target: Path) -> str:
    value = _git_text(target, ("rev-parse", "--verify", "HEAD")).strip()
    if _SHA.fullmatch(value) is None:
        raise WorkError("Git returned an invalid HEAD revision")
    return value


def _branch(target: Path) -> str:
    value = _git_text(target, ("symbolic-ref", "--quiet", "--short", "HEAD")).strip()
    if not value:
        raise WorkError("work packages require an attached branch")
    return value


def _local_branch(target: Path, branch: str) -> bool:
    result = _git(target, ("show-ref", "--verify", "--quiet", f"refs/heads/{branch}"), check=False)
    if result.returncode not in {0, 1}:
        raise WorkError("cannot inspect local workflow branch")
    return result.returncode == 0


def _remote_head(target: Path, remote: str, branch: str) -> str | None:
    value = _git_text(target, ("ls-remote", "--heads", remote, f"refs/heads/{branch}"))
    if not value:
        return None
    records = value.splitlines()
    if len(records) != 1:
        raise WorkError("Git returned ambiguous remote branch state")
    fields = records[0].split("\t")
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}" or _SHA.fullmatch(fields[0]) is None:
        raise WorkError("Git returned malformed remote branch state")
    return fields[0]


def _changes(target: Path) -> tuple[str, ...]:
    raw = _git(target, ("status", "--porcelain=v1", "-z", "--untracked-files=all")).stdout
    records = [item for item in raw.split(b"\0") if item]
    result: set[str] = set()
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4 or record[2:3] != b" ":
            raise WorkError("Git returned malformed worktree status")
        status_code = record[:2].decode("ascii", errors="strict")
        result.add(_git_path(record[3:]))
        if "R" in status_code or "C" in status_code:
            index += 1
            if index >= len(records):
                raise WorkError("Git returned incomplete rename status")
            result.add(_git_path(records[index]))
        index += 1
    return tuple(sorted(result))


def _index_changes(target: Path) -> tuple[str, ...]:
    raw = _git(target, ("diff", "--cached", "--name-only", "-z")).stdout
    return tuple(sorted(_git_path(item) for item in raw.split(b"\0") if item))


def _git_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise WorkError("Git returned a non-UTF-8 path") from error
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise WorkError("Git returned an unsafe path")
    return value


def _worktree_fingerprint(target: Path) -> str:
    status = _git(target, ("status", "--porcelain=v1", "-z", "--untracked-files=all")).stdout
    hasher = hashlib.sha256(status)
    for relative in _changes(target):
        path = target / relative
        hasher.update(relative.encode("utf-8"))
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            hasher.update(b"\0missing")
            continue
        hasher.update(mode.to_bytes(8, "big"))
        if stat.S_ISLNK(mode):
            hasher.update(os.readlink(path).encode("utf-8"))
        elif stat.S_ISREG(mode):
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
    return hasher.hexdigest()


def _validate_paths(target: Path, changed: Sequence[str], allowed: Sequence[str]) -> None:
    for path in changed:
        if not any(
            path == item or (item.endswith("/") and path.startswith(item)) for item in allowed
        ):
            raise WorkError(f"changed path is outside the task allowance: {path}")
        current = target
        for part in PurePosixPath(path).parts:
            current /= part
            try:
                mode = os.lstat(current).st_mode
            except FileNotFoundError:
                break
            if stat.S_ISLNK(mode):
                raise WorkError(f"refusing changed path through a symlink: {path}")


def _validations(
    target: Path,
    package: WorkPackage,
    commands: Sequence[Sequence[str]],
) -> tuple[tuple[ValidationRecord, ...], tuple[str, ...]]:
    records = []
    references = []
    evidence_directory = package.root / "evidence" / package.state.current_task
    evidence_directory.mkdir(parents=True, exist_ok=True)
    before_runs = _evidence_runs(target)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for index, command in enumerate(commands, 1):
        stdout = evidence_directory / f"{index:03d}.stdout"
        stderr = evidence_directory / f"{index:03d}.stderr"
        try:
            completed = subprocess.run(
                tuple(command),
                cwd=target,
                env=environment,
                capture_output=True,
                check=False,
                timeout=_VALIDATION_TIMEOUT,
                shell=False,
            )
            if len(completed.stdout) + len(completed.stderr) > _MAX_VALIDATION_OUTPUT:
                raise WorkError(f"validation {tuple(command)!r} produced excessive output")
            stdout.write_bytes(completed.stdout)
            stderr.write_bytes(completed.stderr)
            records.append(
                ValidationRecord(
                    tuple(command),
                    completed.returncode,
                    stdout.relative_to(package.root).as_posix(),
                    stderr.relative_to(package.root).as_posix(),
                )
            )
        except (OSError, subprocess.SubprocessError) as error:
            stdout.write_bytes(b"")
            stderr.write_text(f"{error}\n", encoding="utf-8")
            records.append(
                ValidationRecord(
                    tuple(command),
                    2,
                    stdout.relative_to(package.root).as_posix(),
                    stderr.relative_to(package.root).as_posix(),
                )
            )
        if records[-1].exit_code != 0:
            break
    for run in sorted(_evidence_runs(target) - before_runs):
        references.append(run.relative_to(target / ".git" / "qat").as_posix())
    return tuple(records), tuple(references)


def _evidence_runs(target: Path) -> set[Path]:
    root = target / ".git" / "qat" / "evidence"
    if not root.is_dir():
        return set()
    return {item for item in root.iterdir() if (item / "summary.json").is_file()}


def _provisional_subject(state: WorkState) -> str:
    return f"chore(work): stage {state.work_id} {state.current_task}"


def _trailers(state: WorkState) -> str:
    return f"Work-Package: {state.repository}#{state.issue}\nWork-Item: {state.current_task}"


def _commit_subject(target: Path, revision: str) -> str:
    return _git_text(target, ("show", "-s", "--format=%s", revision)).strip()


def _parents(target: Path, revision: str) -> tuple[str, ...]:
    return tuple(_git_text(target, ("show", "-s", "--format=%P", revision)).split())


def _require_provisional(target: Path, state: WorkState) -> None:
    if (
        state.provisional_sha is None
        or _head(target) != state.provisional_sha
        or _commit_subject(target, state.provisional_sha) != _provisional_subject(state)
        or _parents(target, state.provisional_sha) != (state.expected_parent,)
    ):
        raise WorkError("HEAD is not the exact provisional task commit")


def _publish_provisional(target: Path, state: WorkState, previous: str | None) -> None:
    ref = f"refs/heads/{state.branch}"
    if previous is None:
        _git(target, ("push", "--set-upstream", state.remote, f"HEAD:{ref}"), timeout=120)
    else:
        _git(target, ("push", state.remote, f"HEAD:{ref}"), timeout=120)


def _lease_publish(target: Path, state: WorkState, previous: str | None) -> None:
    if previous is None:
        raise WorkError("final publication requires an observed provisional revision")
    ref = f"refs/heads/{state.branch}"
    _git(
        target,
        (
            "push",
            f"--force-with-lease={ref}:{previous}",
            state.remote,
            f"HEAD:{ref}",
        ),
        timeout=120,
    )


def _completed_items(target: Path, state: WorkState) -> tuple[str, ...]:
    revisions = _git_text(target, ("log", "--format=%H")).splitlines()
    package = f"Work-Package: {state.repository}#{state.issue}"
    completed = set()
    for revision in revisions:
        message = _git_text(target, ("show", "-s", "--format=%B", revision))
        lines = message.splitlines()
        if package not in lines or lines[0].startswith("chore(work): stage "):
            continue
        tasks = [
            line.removeprefix("Work-Item: ") for line in lines if line.startswith("Work-Item: ")
        ]
        if len(tasks) != 1 or re.fullmatch(r"C[0-9]{2}", tasks[0]) is None:
            raise WorkError(f"commit {revision} has malformed work trailers")
        completed.add(tasks[0])
    return tuple(sorted(completed))
