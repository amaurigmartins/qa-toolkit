"""Deploy and toggle repository-scoped Git and Codex hook dispatchers."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from qa_toolkit.filesystem import atomic_bytes
from qa_toolkit.models import Hook, Profile

CODEX_EVENTS = (
    "SessionStart",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "Stop",
    "SessionEnd",
)


class HookDeploymentError(RuntimeError):
    """Report a foreign, modified, or malformed repository hook path."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _link(source: Path, destination: Path) -> str:
    return os.path.relpath(source, destination.parent)


def _dispatcher_path(target: Path, kind: str, event: str) -> Path:
    if kind == "git":
        return target / ".git" / "hooks" / event
    return target / ".codex" / "hooks" / event


def _relative(target: Path, path: Path) -> str:
    return path.relative_to(target).as_posix()


def _snapshot_foreign(target: Path, path: Path, backup_root: Path) -> dict[str, Any]:
    relative = _relative(target, path)
    identity = hashlib.sha256(relative.encode()).hexdigest()[:16]
    if path.is_symlink():
        return {"path": relative, "kind": "symlink", "target": os.readlink(path)}
    if not path.is_file():
        raise HookDeploymentError(f"refusing non-regular foreign hook path: {relative}")
    backup = backup_root / identity
    atomic_bytes(backup, path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    return {
        "path": relative,
        "kind": "file",
        "backup": backup.relative_to(target / ".git" / "qat").as_posix(),
        "digest": _digest(path),
        "mode": stat.S_IMODE(path.stat().st_mode),
    }


def _restore_foreign(target: Path, item: dict[str, Any]) -> None:
    path = target / str(item["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if item["kind"] == "symlink":
        path.symlink_to(str(item["target"]))
        return
    backup = target / ".git" / "qat" / str(item["backup"])
    atomic_bytes(path, backup.read_bytes(), int(item["mode"]))


def _owned_link_current(target: Path, item: dict[str, Any]) -> bool:
    path = target / str(item["path"])
    return path.is_symlink() and os.readlink(path) == item["target"]


def _definition(events: set[str]) -> bytes:
    timeouts = {
        "SessionStart": 5,
        "PreToolUse": 5,
        "PermissionRequest": 5,
        "PostToolUse": 3600,
        "Stop": 3600,
        "SessionEnd": 3,
    }
    matchers = {
        "PreToolUse": "^(Bash|apply_patch)$",
        "PermissionRequest": "*",
        "PostToolUse": "^(Bash|apply_patch)$",
        "SessionEnd": "^other$",
    }
    hooks: dict[str, list[dict[str, object]]] = {}
    for event in CODEX_EVENTS:
        if event not in events:
            continue
        item: dict[str, object] = {
            "hooks": [
                {
                    "type": "command",
                    "command": f"./.codex/hooks/{event}",
                    "timeout": timeouts[event],
                }
            ]
        }
        if event in matchers:
            item["matcher"] = matchers[event]
        hooks[event] = [item]
    return (json.dumps({"hooks": hooks}, indent=2) + "\n").encode()


def _expected_dispatchers(target: Path, root: Path, profile: Profile) -> list[dict[str, Any]]:
    if not profile.hooks:
        return []
    dispatcher = root / "bin" / "qat-hook-dispatch"
    if not dispatcher.is_file() or not os.access(dispatcher, os.X_OK):
        raise HookDeploymentError("central qat-hook-dispatch is unavailable")
    records = []
    for kind, event in sorted({(hook.kind, hook.event) for hook in profile.hooks}):
        destination = _dispatcher_path(target, kind, event)
        records.append(
            {
                "kind": kind,
                "event": event,
                "path": _relative(target, destination),
                "target": _link(dispatcher, destination),
            }
        )
    return records


def _entry_record(target: Path, root: Path, hook: Hook) -> dict[str, Any]:
    base = target / ".git" / "qat" / "hooks" / hook.kind / hook.event
    available = base / "available" / hook.entry.name
    enabled = base / "enabled" / hook.entry.name
    source = root / hook.entry
    return {
        "kind": hook.kind,
        "event": hook.event,
        "name": hook.entry.name,
        "source": hook.entry.as_posix(),
        "source_digest": _digest(source),
        "available": available.relative_to(target / ".git" / "qat").as_posix(),
        "available_target": _link(source, available),
        "enabled": enabled.relative_to(target / ".git" / "qat").as_posix(),
        "enabled_target": f"../available/{hook.entry.name}",
        "default_enabled": hook.enabled,
    }


def _validate_previous(target: Path, previous: dict[str, Any], hard_reset: bool) -> None:
    if hard_reset:
        return
    modified = [
        str(item["path"])
        for item in previous.get("dispatchers", [])
        if not _owned_link_current(target, item)
    ]
    definition = previous.get("definition")
    if isinstance(definition, dict):
        path = target / str(definition["path"])
        if not path.is_file() or path.is_symlink() or _digest(path) != definition["digest"]:
            modified.append(str(definition["path"]))
    if modified:
        raise HookDeploymentError(
            "modified owned hook paths require --hard-reset: " + ", ".join(sorted(modified))
        )


def _enabled_before(target: Path, previous: dict[str, Any]) -> set[tuple[str, str, str]]:
    result = set()
    state = target / ".git" / "qat"
    for item in previous.get("entries", []):
        enabled = state / str(item["enabled"])
        if enabled.is_symlink() and os.readlink(enabled) == item["enabled_target"]:
            result.add((str(item["kind"]), str(item["event"]), str(item["name"])))
    return result


def reconcile_hooks(
    target: Path,
    root: Path,
    profile: Profile,
    *,
    previous: dict[str, Any] | None = None,
    adopt: bool = False,
    hard_reset: bool = False,
) -> dict[str, Any]:
    """Install or reconcile selected hook entries while preserving hot-toggle state."""
    previous = previous or {}
    _validate_previous(target, previous, hard_reset)
    expected_dispatchers = _expected_dispatchers(target, root, profile)
    previous_dispatchers = {str(item["path"]): item for item in previous.get("dispatchers", [])}
    expected_paths = {str(item["path"]) for item in expected_dispatchers}
    adopted = {str(item["path"]): item for item in previous.get("adopted", [])}
    backup_root = target / ".git" / "qat" / "hook-backups"

    candidates = [target / str(item["path"]) for item in expected_dispatchers]
    codex_events = {hook.event for hook in profile.hooks if hook.kind == "codex"}
    definition_path = target / ".codex" / "hooks.json"
    if codex_events:
        candidates.append(definition_path)
    for path in candidates:
        relative = _relative(target, path)
        if relative in previous_dispatchers or (
            isinstance(previous.get("definition"), dict)
            and relative == previous["definition"].get("path")
        ):
            continue
        if path.exists() or path.is_symlink():
            if not adopt:
                raise HookDeploymentError(f"refusing to replace foreign hook path: {relative}")
            adopted[relative] = _snapshot_foreign(target, path, backup_root)

    for path_string in previous_dispatchers:
        if path_string in expected_paths:
            continue
        destination = target / path_string
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        if path_string in adopted:
            _restore_foreign(target, adopted.pop(path_string))

    for item in expected_dispatchers:
        destination = target / str(item["path"])
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(str(item["target"]))

    old_definition = previous.get("definition")
    if codex_events:
        content = _definition(codex_events)
        if definition_path.exists() or definition_path.is_symlink():
            definition_path.unlink()
        atomic_bytes(definition_path, content)
        definition: dict[str, Any] | None = {
            "path": ".codex/hooks.json",
            "digest": hashlib.sha256(content).hexdigest(),
        }
    else:
        if isinstance(old_definition, dict):
            old_path = target / str(old_definition["path"])
            if old_path.exists() or old_path.is_symlink():
                old_path.unlink()
            if str(old_definition["path"]) in adopted:
                _restore_foreign(target, adopted.pop(str(old_definition["path"])))
        definition = None

    old_enabled = _enabled_before(target, previous)
    entries = [_entry_record(target, root, hook) for hook in profile.hooks]
    hook_state = target / ".git" / "qat" / "hooks"
    if hook_state.exists():
        shutil.rmtree(hook_state)
    for item in entries:
        available = target / ".git" / "qat" / str(item["available"])
        enabled = target / ".git" / "qat" / str(item["enabled"])
        available.parent.mkdir(parents=True, exist_ok=True)
        available.symlink_to(str(item["available_target"]))
        identity = (str(item["kind"]), str(item["event"]), str(item["name"]))
        selected = identity in old_enabled if previous.get("entries") else item["default_enabled"]
        if selected:
            enabled.parent.mkdir(parents=True, exist_ok=True)
            enabled.symlink_to(str(item["enabled_target"]))

    return {
        "schema_version": 1,
        "dispatchers": expected_dispatchers,
        "definition": definition,
        "entries": entries,
        "adopted": [adopted[path] for path in sorted(adopted)],
    }


def hook_status(target: Path, root: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Report dispatcher identity and the local enabled state of every entry."""
    state = target / ".git" / "qat"
    dispatchers = [
        {**item, "current": _owned_link_current(target, item)}
        for item in record.get("dispatchers", [])
    ]
    definition = record.get("definition")
    definition_current = True
    if isinstance(definition, dict):
        path = target / str(definition["path"])
        definition_current = (
            path.is_file() and not path.is_symlink() and _digest(path) == definition["digest"]
        )
    entries = []
    for item in record.get("entries", []):
        source = root / str(item["source"])
        available = state / str(item["available"])
        enabled = state / str(item["enabled"])
        available_current = (
            source.is_file()
            and _digest(source) == item["source_digest"]
            and available.is_symlink()
            and os.readlink(available) == item["available_target"]
        )
        enabled_value = enabled.is_symlink() and os.readlink(enabled) == item["enabled_target"]
        malformed_enabled = enabled.exists() and not enabled_value
        entries.append(
            {
                "kind": item["kind"],
                "event": item["event"],
                "name": item["name"],
                "available_current": available_current,
                "enabled": enabled_value,
                "current": available_current and not malformed_enabled,
            }
        )
    current = definition_current and all(item["current"] for item in dispatchers + entries)
    return {
        "current": current,
        "definition_current": definition_current,
        "dispatchers": dispatchers,
        "entries": entries,
    }


def set_enabled(
    target: Path,
    record: dict[str, Any],
    enabled_value: bool,
    *,
    kind: str | None = None,
    event: str | None = None,
    name: str | None = None,
) -> tuple[str, ...]:
    """Toggle only selected local enabled links without changing central scripts."""
    state = target / ".git" / "qat"
    selected = [
        item
        for item in record.get("entries", [])
        if (kind is None or item["kind"] == kind)
        and (event is None or item["event"] == event)
        and (name is None or item["name"] == name)
    ]
    if not selected:
        raise HookDeploymentError("no selected profile hook matches the requested filters")
    changed = []
    for item in selected:
        path = state / str(item["enabled"])
        identity = f"{item['kind']}:{item['event']}:{item['name']}"
        if enabled_value:
            if path.exists() and not path.is_symlink():
                raise HookDeploymentError(f"refusing malformed enabled hook entry: {identity}")
            if path.is_symlink() and os.readlink(path) != item["enabled_target"]:
                raise HookDeploymentError(f"refusing modified enabled hook entry: {identity}")
            if not path.is_symlink():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(str(item["enabled_target"]))
        elif path.is_symlink():
            if os.readlink(path) != item["enabled_target"]:
                raise HookDeploymentError(f"refusing modified enabled hook entry: {identity}")
            path.unlink()
        elif path.exists():
            raise HookDeploymentError(f"refusing malformed enabled hook entry: {identity}")
        changed.append(identity)
    return tuple(changed)


def remove_hooks(
    target: Path,
    record: dict[str, Any],
    *,
    backup: Path | None,
    hard_reset: bool,
) -> None:
    """Remove owned dispatchers and restore explicitly adopted foreign hooks."""
    if backup is None:
        _validate_previous(target, record, hard_reset)
    owned_paths = [Path(str(item["path"])) for item in record.get("dispatchers", [])]
    definition = record.get("definition")
    if isinstance(definition, dict):
        owned_paths.append(Path(str(definition["path"])))
    if backup is not None:
        for relative in owned_paths:
            source = target / relative
            if not source.exists() and not source.is_symlink():
                continue
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                destination.symlink_to(os.readlink(source))
            else:
                shutil.copy2(source, destination)
    for relative in reversed(owned_paths):
        path = target / relative
        if path.exists() or path.is_symlink():
            path.unlink()
    for item in record.get("adopted", []):
        _restore_foreign(target, item)
    for directory in (target / ".codex" / "hooks", target / ".codex"):
        with contextlib.suppress(OSError):
            directory.rmdir()
