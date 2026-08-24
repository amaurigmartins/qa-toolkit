"""Run enabled repository hook entries in lexical order."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from qa_toolkit.hook_deployment import HookDeploymentError

MAX_CODEX_INPUT = 1_048_576


def invocation_context(
    invoked_as: str | None,
    target: Path | None,
    kind: str | None,
    event: str | None,
) -> tuple[Path, str, str]:
    """Resolve an installed dispatcher path or an explicit test invocation."""
    if target is not None or kind is not None or event is not None:
        if target is None or kind not in {"git", "codex"} or event is None:
            raise HookDeploymentError("explicit dispatch requires target, kind, and event")
        return target.resolve(), kind, event
    if invoked_as is None:
        raise HookDeploymentError("dispatch requires an installed path or explicit context")
    path = Path(invoked_as)
    if not path.is_absolute():
        path = (Path.cwd() / path).absolute()
    if path.parent.name != "hooks" or path.parent.parent.name not in {".git", ".codex"}:
        raise HookDeploymentError("dispatcher path is outside .git/hooks or .codex/hooks")
    selected_kind = "git" if path.parent.parent.name == ".git" else "codex"
    return path.parent.parent.parent.resolve(), selected_kind, path.name


def _record(target: Path) -> tuple[Path, dict[str, Any]]:
    path = target / ".git" / "qat" / "deployment.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HookDeploymentError("repository hook deployment record is unavailable") from error
    if not isinstance(value, dict) or value.get("target_root") != str(target):
        raise HookDeploymentError("repository hook deployment record has the wrong target")
    root = Path(str(value.get("toolkit_root", "")))
    if not root.is_absolute() or not root.is_dir():
        raise HookDeploymentError("repository hook deployment has an invalid toolkit root")
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        raise HookDeploymentError("repository hook deployment is unavailable")
    return root, hooks


def _selected_entries(
    target: Path, root: Path, record: dict[str, Any], kind: str, event: str
) -> tuple[Path, ...]:
    state = target / ".git" / "qat"
    expected = {
        str(item["name"]): item
        for item in record.get("entries", [])
        if item.get("kind") == kind and item.get("event") == event
    }
    directory = state / "hooks" / kind / event / "enabled"
    if not directory.is_dir() or directory.is_symlink():
        return ()
    selected: list[Path] = []
    for item in sorted(directory.iterdir(), key=lambda path: path.name):
        declared = expected.get(item.name)
        if declared is None or not item.is_symlink():
            continue
        if os.readlink(item) != declared["enabled_target"]:
            raise HookDeploymentError(f"modified enabled hook entry: {kind}:{event}:{item.name}")
        available = state / str(declared["available"])
        source = root / str(declared["source"])
        if (
            not available.is_symlink()
            or os.readlink(available) != declared["available_target"]
            or not source.is_file()
            or not os.access(source, os.X_OK)
        ):
            raise HookDeploymentError(f"unavailable hook entry: {kind}:{event}:{item.name}")
        selected.append(source)
    return tuple(selected)


def _environment(target: Path, root: Path, kind: str, event: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QAT_EVENT": event,
            "QAT_KIND": kind,
            "QAT_ROOT": str(root),
            "QAT_TARGET": str(target),
        }
    )
    return environment


def _merge_responses(event: str, responses: list[dict[str, object]]) -> dict[str, object] | None:
    if not responses:
        return None
    decisive = [response for response in responses if _decisive(response)]
    if decisive:
        return decisive[0]
    contexts = []
    messages = []
    for response in responses:
        output = response.get("hookSpecificOutput")
        if isinstance(output, dict) and isinstance(output.get("additionalContext"), str):
            contexts.append(output["additionalContext"])
        if isinstance(response.get("systemMessage"), str):
            messages.append(str(response["systemMessage"]))
    if contexts:
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": "\n".join(contexts),
            }
        }
    if messages:
        return {"systemMessage": "\n".join(messages)}
    return responses[0] if len(responses) == 1 else None


def _decisive(response: dict[str, object]) -> bool:
    if response.get("decision") == "block":
        return True
    output = response.get("hookSpecificOutput")
    return isinstance(output, dict) and (
        output.get("permissionDecision") == "deny" or isinstance(output.get("decision"), dict)
    )


def dispatch(
    target: Path,
    kind: str,
    event: str,
    arguments: tuple[str, ...],
    *,
    codex_input: bytes | None = None,
) -> int:
    """Execute the currently enabled scripts for one installed event."""
    root, record = _record(target)
    dispatcher = next(
        (
            item
            for item in record.get("dispatchers", [])
            if item.get("kind") == kind and item.get("event") == event
        ),
        None,
    )
    if dispatcher is None:
        raise HookDeploymentError(f"event is not selected by the profile: {kind}:{event}")
    entries = _selected_entries(target, root, record, kind, event)
    environment = _environment(target, root, kind, event)
    if kind == "git":
        for entry in entries:
            completed = subprocess.run(
                [str(entry), *arguments],
                cwd=target,
                env=environment,
                check=False,
                timeout=3600,
                shell=False,
            )
            if completed.returncode != 0:
                return completed.returncode
        return 0

    payload = codex_input if codex_input is not None else sys.stdin.buffer.read(MAX_CODEX_INPUT + 1)
    if len(payload) > MAX_CODEX_INPUT:
        raise HookDeploymentError("Codex hook input exceeds one MiB")
    responses: list[dict[str, object]] = []
    for entry in entries:
        completed = subprocess.run(
            [str(entry), *arguments],
            cwd=target,
            env=environment,
            input=payload,
            capture_output=True,
            check=False,
            timeout=3600,
            shell=False,
        )
        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr[:4096])
        if completed.returncode != 0:
            return completed.returncode
        if completed.stdout.strip():
            try:
                response = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise HookDeploymentError(f"{entry.name} emitted invalid JSON") from error
            if not isinstance(response, dict):
                raise HookDeploymentError(f"{entry.name} emitted a non-object response")
            responses.append(response)
    response = _merge_responses(event, responses)
    if response is not None:
        print(json.dumps(response, separators=(",", ":")))
    return 0
