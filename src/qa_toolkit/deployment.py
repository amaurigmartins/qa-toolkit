"""Deploy repository profiles through exact local ownership records."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from qa_toolkit.config import digest_consumer, digest_profile, load_consumer, load_profile
from qa_toolkit.filesystem import atomic_bytes
from qa_toolkit.hook_deployment import (
    HookDeploymentError,
    hook_status,
    reconcile_hooks,
    remove_hooks,
)
from qa_toolkit.models import ConfigurationError, ConfigurationLink, Consumer, Profile
from qa_toolkit.paths import toolkit_root


class DeploymentError(RuntimeError):
    """Report unsafe or inconsistent deployment state."""


def _git(
    target: Path, arguments: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(target), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DeploymentError(f"Git command failed: {error}") from error
    if check and result.returncode != 0:
        raise DeploymentError((result.stderr or result.stdout).strip())
    return result


def git_bytes(target: Path, *arguments: str) -> bytes:
    """Run one bounded Git inspection and return its raw output."""
    try:
        return subprocess.run(
            ["git", "-C", str(target), *arguments],
            check=True,
            capture_output=True,
            timeout=30,
            shell=False,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise DeploymentError(f"Git inspection failed: {error}") from error


def resolve_target(value: Path) -> Path:
    """Resolve one ordinary Git worktree root."""
    target = Path(_git(value.resolve(), ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    if not (target / ".git").is_dir():
        raise DeploymentError("qa-toolkit currently requires an ordinary Git worktree")
    return target


def tracked_entries(target: Path) -> tuple[tuple[str, str], ...]:
    """Return tracked Git modes and paths without interpreting shell text."""
    try:
        output = git_bytes(target, "ls-files", "--cached", "--stage", "-z")
    except DeploymentError as error:
        raise DeploymentError(f"cannot list tracked repository inputs: {error}") from error
    result: list[tuple[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        mode = metadata.split(b" ", maxsplit=1)[0].decode("ascii")
        result.append((mode, raw_path.decode("utf-8")))
    return tuple(result)


def tracked_regular_files(target: Path) -> tuple[str, ...]:
    """Return tracked paths that currently resolve to ordinary files."""
    result = []
    for mode, path in tracked_entries(target):
        candidate = target / path
        if mode in {"100644", "100755"} and candidate.is_file() and not candidate.is_symlink():
            result.append(path)
    return tuple(sorted(result))


def _tracked(target: Path, path: Path) -> bool:
    result = _git(target, ["ls-files", "--error-unmatch", "--", path.as_posix()], check=False)
    if result.returncode == 0:
        return True
    return bool(_git(target, ["ls-files", "--", path.as_posix()], check=False).stdout.strip())


def _validate_consumer_paths(target: Path, consumer: Consumer) -> None:
    paths = [Path(".qat.toml"), *consumer.native_configurations]
    paths.extend(
        path
        for path in (
            consumer.vocabulary_file,
            consumer.ast_grep_config,
            consumer.ast_grep_tests,
            consumer.python.project,
        )
        if path is not None
    )
    for path in paths:
        if not (target / path).exists():
            raise DeploymentError(f"declared consumer path does not exist: {path}")
        if not _tracked(target, path):
            raise DeploymentError(f"declared consumer path is not tracked: {path}")
    for gate in consumer.gates:
        executable = Path(gate.argv[0])
        if (
            len(executable.parts) > 1
            and not executable.is_absolute()
            and not _tracked(target, executable)
        ):
            raise DeploymentError(f"consumer gate executable is not tracked: {executable}")


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _revision(repository: Path) -> str:
    value = _git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    if len(value) != 40:
        raise DeploymentError(f"cannot resolve exact revision for {repository}")
    return value


def _state(target: Path) -> Path:
    return target / ".git" / "qat"


def _record_path(target: Path) -> Path:
    return _state(target) / "deployment.json"


def _atomic_text(path: Path, content: str) -> None:
    atomic_bytes(path, content.encode())


def _relative_link(source: Path, destination: Path) -> str:
    return os.path.relpath(source, destination.parent)


def _exclude(target: Path, required: tuple[str, ...]) -> dict[str, Any]:
    path = target / ".git" / "info" / "exclude"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = set(before.splitlines())
    owned = tuple(line for line in required if line not in existing)
    after = before
    for line in owned:
        separator = "" if not after or after.endswith("\n") else "\n"
        after = f"{after}{separator}{line}\n"
    _atomic_text(path, after)
    return {
        "path": ".git/info/exclude",
        "lines": list(required),
        "owned": list(owned),
        "before": before,
        "after": after,
    }


def _exclude_lines(profile: Profile) -> tuple[str, ...]:
    lines = [".qat/"]
    if any(hook.kind == "codex" for hook in profile.hooks):
        lines.extend((".codex/hooks.json", ".codex/hooks/"))
    return tuple(lines)


def _reconcile_exclude(
    target: Path, previous: dict[str, Any], required: tuple[str, ...]
) -> dict[str, Any]:
    path = target / ".git" / "info" / "exclude"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    old_owned = previous.get("owned", [])
    if isinstance(old_owned, bool):
        old_owned = [previous.get("line", ".qat/")] if old_owned else []
    owned = [str(line) for line in old_owned]
    lines = current.splitlines(keepends=True)
    for line in tuple(owned):
        if line not in required:
            lines = [item for item in lines if item.rstrip("\r\n") != line]
            owned.remove(line)
    current = "".join(lines)
    present = set(current.splitlines())
    for line in required:
        if line in present:
            continue
        separator = "" if not current or current.endswith("\n") else "\n"
        current = f"{current}{separator}{line}\n"
        owned.append(line)
        present.add(line)
    _atomic_text(path, current)
    return {
        "path": ".git/info/exclude",
        "lines": list(required),
        "owned": owned,
        "before": previous.get("before", ""),
        "after": current,
    }


def _deploy_configuration(
    root: Path, target: Path, configuration: ConfigurationLink, base_directory: Path
) -> dict[str, Any]:
    source = root / configuration.source
    destination = target / configuration.destination
    if destination.exists() or destination.is_symlink():
        raise DeploymentError(f"refusing to replace foreign path: {configuration.destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if configuration.mode == "symlink":
        link = _relative_link(source, destination)
        destination.symlink_to(link)
        return {
            "id": configuration.identifier,
            "path": configuration.destination.as_posix(),
            "kind": "symlink",
            "target": link,
            "digest": _digest(source),
        }
    content = source.read_bytes()
    atomic_bytes(destination, content)
    base = base_directory / configuration.identifier
    atomic_bytes(base, content)
    return {
        "id": configuration.identifier,
        "path": configuration.destination.as_posix(),
        "kind": "copy",
        "target": None,
        "digest": _digest_bytes(content),
        "source_digest": _digest_bytes(content),
        "base": base.relative_to(_state(target)).as_posix(),
    }


def enroll(
    target_value: Path,
    root: Path | None = None,
    *,
    adopt_hooks: bool = False,
) -> dict[str, Any]:
    """Deploy the selected profile into one repository."""
    root = (root or toolkit_root()).resolve()
    target = resolve_target(target_value)
    if _record_path(target).exists():
        raise DeploymentError("repository is already enrolled")
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    _validate_consumer_paths(target, consumer)
    for configuration in profile.configurations:
        destination = target / configuration.destination
        if destination.exists() or destination.is_symlink():
            raise DeploymentError(f"refusing to replace foreign path: {configuration.destination}")

    state = _state(target)
    base_directory = state / "base"
    base_directory.mkdir(parents=True, exist_ok=True)
    exclude = _exclude(target, _exclude_lines(profile))
    owned: list[dict[str, Any]] = []
    hooks: dict[str, Any] = {}
    try:
        for configuration in profile.configurations:
            owned.append(_deploy_configuration(root, target, configuration, base_directory))
        hooks = reconcile_hooks(target, root, profile, adopt=adopt_hooks)
        record = {
            "schema_version": 1,
            "toolkit_root": str(root),
            "toolkit_revision": _revision(root),
            "target_root": str(target),
            "target_revision": _revision(target),
            "profile": profile.name,
            "profile_digest": digest_profile(profile),
            "consumer_digest": digest_consumer(consumer),
            "owned": owned,
            "hooks": hooks,
            "exclude": exclude,
        }
        _atomic_text(_record_path(target), f"{json.dumps(record, indent=2, sort_keys=True)}\n")
        return record
    except Exception:
        if hooks:
            remove_hooks(target, hooks, backup=None, hard_reset=True)
        for item in reversed(owned):
            path = target / item["path"]
            if path.exists() or path.is_symlink():
                path.unlink()
        if exclude["owned"]:
            _atomic_text(target / ".git/info/exclude", str(exclude["before"]))
        if state.exists():
            shutil.rmtree(state)
        raise


def _load_record(target: Path) -> dict[str, Any]:
    try:
        value = json.loads(_record_path(target).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentError(
            "repository is not enrolled or its deployment record is invalid"
        ) from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise DeploymentError("unsupported deployment record")
    if value.get("target_root") != str(target):
        raise DeploymentError("deployment record belongs to another repository")
    return value


def _owned_current(target: Path, item: dict[str, Any]) -> tuple[bool, str]:
    path = target / item["path"]
    if item["kind"] == "symlink":
        if not path.is_symlink():
            return False, "missing-or-replaced"
        current = os.readlink(path) == item["target"]
        return current, "current" if current else "modified"
    if not path.is_file() or path.is_symlink():
        return False, "missing-or-replaced"
    current = _digest(path) == item["digest"]
    return current, "current" if current else "modified"


def status(target_value: Path, root: Path | None = None) -> dict[str, Any]:
    """Compare a repository with its current profile and ownership record."""
    root = (root or toolkit_root()).resolve()
    target = resolve_target(target_value)
    record = _load_record(target)
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    paths = []
    current = True
    configurations = {item.destination.as_posix(): item for item in profile.configurations}
    for item in record["owned"]:
        valid, detail = _owned_current(target, item)
        configuration = configurations.get(item["path"])
        central_current = configuration is not None and item.get(
            "source_digest", item["digest"]
        ) == _digest(root / configuration.source)
        valid = valid and central_current
        if not central_current:
            detail = "central-source-changed"
        paths.append({"path": item["path"], "current": valid, "detail": detail})
        current = current and valid
    hooks = hook_status(target, root, record.get("hooks", {}))
    current = current and hooks["current"]
    profile_current = record["profile_digest"] == digest_profile(profile)
    consumer_current = record["consumer_digest"] == digest_consumer(consumer)
    toolkit_current = record["toolkit_revision"] == _revision(root)
    return {
        "enrolled": True,
        "current": current and profile_current and consumer_current and toolkit_current,
        "profile": profile.name,
        "profile_current": profile_current,
        "consumer_current": consumer_current,
        "toolkit_current": toolkit_current,
        "paths": paths,
        "hooks": hooks,
    }


def _merge_copy(local: bytes, base: bytes, incoming: bytes, directory: Path) -> bytes | None:
    directory.mkdir(parents=True, exist_ok=True)
    local_path = directory / "local"
    base_path = directory / "base"
    incoming_path = directory / "incoming"
    local_path.write_bytes(local)
    base_path.write_bytes(base)
    incoming_path.write_bytes(incoming)
    result = subprocess.run(
        ["git", "merge-file", "-p", str(local_path), str(base_path), str(incoming_path)],
        check=False,
        capture_output=True,
        timeout=30,
        shell=False,
    )
    (directory / "merge").write_bytes(result.stdout)
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 1:
        return None
    raise DeploymentError(f"git merge-file failed with exit {result.returncode}")


def sync(
    target_value: Path,
    root: Path | None = None,
    *,
    hard_reset: bool = False,
    adopt_hooks: bool = False,
) -> dict[str, Any]:
    """Reconcile managed paths without rewriting native consumer configuration."""
    root = (root or toolkit_root()).resolve()
    target = resolve_target(target_value)
    old = _load_record(target)
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    _validate_consumer_paths(target, consumer)
    old_by_path = {item["path"]: item for item in old["owned"]}
    new_by_path = {item.destination.as_posix(): item for item in profile.configurations}
    conflicts = _state(target) / "conflicts"
    if conflicts.exists():
        shutil.rmtree(conflicts)

    planned: dict[str, tuple[str, bytes | str, str]] = {}
    next_records: dict[str, dict[str, Any]] = {}
    for path_string, configuration in new_by_path.items():
        source = root / configuration.source
        destination = target / configuration.destination
        previous = old_by_path.get(path_string)
        if configuration.mode == "symlink":
            link = _relative_link(source, destination)
            if previous is None and (destination.exists() or destination.is_symlink()):
                raise DeploymentError(f"refusing to replace foreign path: {path_string}")
            if previous is not None and not hard_reset:
                valid, _ = _owned_current(target, previous)
                if not valid:
                    raise DeploymentError(
                        f"modified managed path requires --hard-reset: {path_string}"
                    )
            planned[path_string] = ("symlink", link, configuration.identifier)
            next_records[path_string] = {
                "id": configuration.identifier,
                "path": path_string,
                "kind": "symlink",
                "target": link,
                "digest": _digest(source),
            }
            continue

        incoming = source.read_bytes()
        if previous is None:
            if destination.exists() or destination.is_symlink():
                raise DeploymentError(f"refusing to replace foreign path: {path_string}")
            merged = incoming
        elif hard_reset:
            merged = incoming
        else:
            if not destination.is_file() or destination.is_symlink():
                raise DeploymentError(f"modified managed path requires --hard-reset: {path_string}")
            local = destination.read_bytes()
            base = target / ".git" / "qat" / previous["base"]
            base_content = base.read_bytes()
            if local == base_content:
                merged = incoming
            elif incoming == base_content:
                merged = local
            else:
                result = _merge_copy(
                    local, base_content, incoming, conflicts / configuration.identifier
                )
                if result is None:
                    raise DeploymentError(
                        f"configuration conflict; target unchanged; inspect "
                        f"{conflicts / configuration.identifier}"
                    )
                merged = result
        planned[path_string] = ("copy", merged, configuration.identifier)
        next_records[path_string] = {
            "id": configuration.identifier,
            "path": path_string,
            "kind": "copy",
            "target": None,
            "digest": _digest_bytes(merged),
            "source_digest": _digest_bytes(incoming),
            "base": f"base/{configuration.identifier}",
        }

    for path_string, item in old_by_path.items():
        if path_string in new_by_path or hard_reset:
            continue
        valid, _ = _owned_current(target, item)
        if not valid:
            raise DeploymentError(f"modified removed path requires --hard-reset: {path_string}")

    for path_string in old_by_path.keys() - new_by_path.keys():
        path = target / path_string
        if path.exists() or path.is_symlink():
            path.unlink()
    for path_string, (kind, value, identifier) in planned.items():
        destination = target / path_string
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if kind == "symlink":
            destination.symlink_to(str(value))
        else:
            content = value if isinstance(value, bytes) else value.encode()
            atomic_bytes(destination, content)
            central = (root / new_by_path[path_string].source).read_bytes()
            atomic_bytes(_state(target) / "base" / identifier, central)

    hooks = reconcile_hooks(
        target,
        root,
        profile,
        previous=old.get("hooks", {}),
        adopt=adopt_hooks,
        hard_reset=hard_reset,
    )
    exclude = _reconcile_exclude(target, old["exclude"], _exclude_lines(profile))

    record = {
        **old,
        "toolkit_root": str(root),
        "toolkit_revision": _revision(root),
        "target_revision": _revision(target),
        "profile": profile.name,
        "profile_digest": digest_profile(profile),
        "consumer_digest": digest_consumer(consumer),
        "owned": [next_records[path] for path in new_by_path],
        "hooks": hooks,
        "exclude": exclude,
    }
    _atomic_text(_record_path(target), f"{json.dumps(record, indent=2, sort_keys=True)}\n")
    return record


def _backup_path(target: Path, path: Path, backup: Path) -> None:
    destination = backup / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = target / path
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_file():
        shutil.copy2(source, destination)


def unenroll(
    target_value: Path,
    *,
    backup: Path | None = None,
    hard_reset: bool = False,
    purge_config: bool = False,
) -> None:
    """Remove only recorded deployment paths and exact local exclude entries."""
    if purge_config:
        raise DeploymentError(
            "automatic purge of repository-owned configuration is intentionally unsupported"
        )
    target = resolve_target(target_value)
    record = _load_record(target)
    modified: list[Path] = []
    for item in record["owned"]:
        valid, _ = _owned_current(target, item)
        if not valid:
            modified.append(Path(item["path"]))
    if modified and backup is None and not hard_reset:
        raise DeploymentError(
            "modified managed paths require --backup PATH or --hard-reset: "
            + ", ".join(path.as_posix() for path in modified)
        )
    if backup is not None:
        backup = backup.resolve()
        if backup == target or target in backup.parents:
            raise DeploymentError("backup path must be outside the target repository")
        for path in modified:
            _backup_path(target, path, backup)

    try:
        remove_hooks(
            target,
            record.get("hooks", {}),
            backup=backup,
            hard_reset=hard_reset,
        )
    except HookDeploymentError as error:
        raise DeploymentError(str(error)) from error

    for item in reversed(record["owned"]):
        path = target / item["path"]
        if path.exists() or path.is_symlink():
            path.unlink()
        parent = path.parent
        while parent != target and parent.name != ".git":
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    exclude = record["exclude"]
    exclude_path = target / exclude["path"]
    owned_excludes = exclude.get("owned", [])
    if isinstance(owned_excludes, bool):
        owned_excludes = [exclude.get("line", ".qat/")] if owned_excludes else []
    if owned_excludes:
        current = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        lines = current.splitlines(keepends=True)
        remaining = [line for line in lines if line.rstrip("\r\n") not in set(owned_excludes)]
        _atomic_text(exclude_path, "".join(remaining))
    shutil.rmtree(_state(target))


def validate_profile(name: str, root: Path | None = None) -> Profile:
    """Validate one profile and return it for display."""
    try:
        return load_profile(name, root)
    except ConfigurationError as error:
        raise DeploymentError(str(error)) from error
