"""Resolve and execute repository quality gates once in declared order."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from qa_toolkit.config import digest_consumer, digest_profile, load_consumer, load_profile
from qa_toolkit.deployment import DeploymentError, resolve_target, status
from qa_toolkit.models import ConsumerGate, Gate
from qa_toolkit.paths import payload_root, toolkit_root
from qa_toolkit.registry import executable_path, select_tools

NormalizedResult = Literal["pass", "finding", "execution-error", "not-run"]


@dataclass(frozen=True)
class PlannedGate:
    """One fully resolved gate ready for direct execution."""

    identifier: str
    phase: str
    argv: tuple[str, ...]
    timeout: int
    severity: str
    finding_exit_codes: tuple[int, ...]
    execution_error_exit_codes: tuple[int, ...]
    execution_owner: str
    rule_source: str


class RunnerError(RuntimeError):
    """Report invalid planning or execution state."""


def _matches(triggers: tuple[str, ...], changed: tuple[str, ...]) -> bool:
    if not changed:
        return True
    return any(fnmatch.fnmatch(path, pattern) for path in changed for pattern in triggers)


def _target_python(target: Path, consumer_project: Path | None, root: Path) -> Path:
    candidates = []
    if consumer_project is not None:
        candidates.append(target / consumer_project / ".venv" / "bin" / "python")
    candidates.append(target / ".venv" / "bin" / "python")
    candidates.append(payload_root(root) / "python" / "bin" / "python")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RunnerError("cannot resolve target or central Python executable")


def _resolve_argument(argument: str, target: Path, root: Path, target_python: Path) -> str:
    if argument == "{target}":
        return str(target)
    if argument == "{target-python}":
        return str(target_python)
    if argument == "{qat-python}":
        return str(payload_root(root) / "python" / "bin" / "python")
    match = re.fullmatch(r"\{tool:([a-z0-9][a-z0-9.-]*)\}", argument)
    if match:
        tool = select_tools([match.group(1)], root)[0]
        executable = executable_path(tool, root)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RunnerError(f"selected tool is unavailable: {tool.tool_id}")
        return str(executable)
    if "{" in argument or "}" in argument:
        raise RunnerError(f"unsupported argument placeholder: {argument}")
    return argument


def _planned(
    gate: Gate | ConsumerGate,
    *,
    owner: str,
    source: Path,
    target: Path,
    root: Path,
    target_python: Path,
) -> PlannedGate:
    return PlannedGate(
        identifier=gate.identifier,
        phase=gate.phase,
        argv=tuple(_resolve_argument(item, target, root, target_python) for item in gate.argv),
        timeout=gate.timeout,
        severity=gate.severity,
        finding_exit_codes=gate.finding_exit_codes,
        execution_error_exit_codes=gate.execution_error_exit_codes,
        execution_owner=owner,
        rule_source=str(source),
    )


def resolve_plan(
    target: Path,
    root: Path,
    mode: Literal["check", "sentinel", "advisory"],
    *,
    variant: str | None,
    include_advisory: bool,
    changed: tuple[str, ...],
) -> tuple[PlannedGate, ...]:
    """Resolve the complete selected order before executing any command."""
    deployment = status(target, root)
    if not deployment["current"]:
        raise RunnerError("repository deployment is stale; run qat repo sync")
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    target_python = _target_python(target, consumer.python_project, root)
    phases = ("check",) if mode in {"check", "advisory"} else ("check", "sentinel")
    selected: list[PlannedGate] = []
    seen: set[str] = set()
    for phase in phases:
        sources: tuple[tuple[Gate | ConsumerGate, str, Path], ...] = tuple(
            (gate, "central", profile.source) for gate in profile.gates if gate.phase == phase
        ) + tuple(
            (gate, "consumer", consumer.source) for gate in consumer.gates if gate.phase == phase
        )
        for gate, owner, source in sources:
            if gate.identifier in seen:
                raise RunnerError(f"duplicate resolved gate ID: {gate.identifier}")
            seen.add(gate.identifier)
            if mode == "advisory" and gate.severity != "advisory":
                continue
            if mode != "advisory" and gate.severity == "advisory" and not include_advisory:
                continue
            if gate.variants and variant not in gate.variants:
                continue
            if not _matches(gate.triggers, changed):
                continue
            selected.append(
                _planned(
                    gate,
                    owner=owner,
                    source=source,
                    target=target,
                    root=root,
                    target_python=target_python,
                )
            )
    return tuple(selected)


def _git_facts(repository: Path) -> tuple[str, bool, str]:
    revision = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    ).stdout.strip()
    worktree = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1", "-z"],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
    ).stdout
    return revision, bool(worktree), hashlib.sha256(worktree).hexdigest()


def _classification(gate: PlannedGate, exit_code: int) -> NormalizedResult:
    if exit_code == 0:
        return "pass"
    if exit_code in gate.finding_exit_codes:
        return "finding"
    return "execution-error"


def execute(
    target_value: Path,
    mode: Literal["check", "sentinel", "advisory"],
    *,
    variant: str | None = None,
    include_advisory: bool = False,
    changed: tuple[str, ...] = (),
    root: Path | None = None,
) -> tuple[int, Path]:
    """Execute a resolved plan and retain complete output below the target Git directory."""
    root = (root or toolkit_root()).resolve()
    target = resolve_target(target_value)
    plan = resolve_plan(
        target,
        root,
        mode,
        variant=variant,
        include_advisory=include_advisory,
        changed=changed,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:12]}"
    run_directory = target / ".git" / "qat" / "evidence" / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    toolkit_revision, toolkit_dirty, toolkit_fingerprint = _git_facts(root)
    target_revision, target_dirty, target_fingerprint = _git_facts(target)
    results: list[dict[str, object]] = []
    blocking_finding = False
    execution_error = False
    stop = False
    for index, gate in enumerate(plan, start=1):
        stdout_path = run_directory / f"{index:03d}-{gate.identifier}.stdout"
        stderr_path = run_directory / f"{index:03d}-{gate.identifier}.stderr"
        if stop:
            result: NormalizedResult = "not-run"
            exit_code: int | None = None
            stdout = b""
            stderr = b""
        else:
            try:
                completed = subprocess.run(
                    list(gate.argv),
                    cwd=target,
                    check=False,
                    capture_output=True,
                    timeout=gate.timeout,
                    shell=False,
                )
                exit_code = completed.returncode
                stdout = completed.stdout
                stderr = completed.stderr
                result = _classification(gate, exit_code)
            except (OSError, subprocess.TimeoutExpired) as error:
                exit_code = None
                stdout = b""
                stderr = f"{error}\n".encode()
                result = "execution-error"
            if result == "execution-error":
                execution_error = True
                stop = True
            elif result == "finding" and gate.severity == "blocking":
                blocking_finding = True
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        print(f"[{result.upper()}] {gate.identifier}")
        results.append(
            {
                "id": gate.identifier,
                "phase": gate.phase,
                "argv": list(gate.argv),
                "severity": gate.severity,
                "execution_owner": gate.execution_owner,
                "rule_source": gate.rule_source,
                "result": result,
                "exit_code": exit_code,
                "stdout": stdout_path.name,
                "stderr": stderr_path.name,
            }
        )
    exit_code = 2 if execution_error else 1 if blocking_finding else 0
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "mode": mode,
        "variant": variant,
        "include_advisory": include_advisory,
        "toolkit_revision": toolkit_revision,
        "toolkit_dirty": toolkit_dirty,
        "toolkit_worktree_fingerprint": toolkit_fingerprint,
        "target_revision": target_revision,
        "target_dirty": target_dirty,
        "target_worktree_fingerprint": target_fingerprint,
        "profile": profile.name,
        "profile_digest": digest_profile(profile),
        "consumer_digest": digest_consumer(consumer),
        "planned_order": [gate.identifier for gate in plan],
        "plan": [
            {
                "id": gate.identifier,
                "phase": gate.phase,
                "argv": list(gate.argv),
                "severity": gate.severity,
                "execution_owner": gate.execution_owner,
                "rule_source": gate.rule_source,
            }
            for gate in plan
        ],
        "results": results,
        "exit_code": exit_code,
    }
    (run_directory / "summary.json").write_text(
        f"{json.dumps(summary, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    print(f"evidence: {run_directory}")
    return exit_code, run_directory


def guarded_execute(*args: object, **kwargs: object) -> tuple[int, Path | None]:
    """Convert configuration and planning failures to command exit 2."""
    try:
        return execute(*args, **kwargs)  # type: ignore[arg-type]
    except (DeploymentError, RunnerError, OSError, subprocess.CalledProcessError) as error:
        print(f"qat: {error}", file=sys.stderr)
        return 2, None
