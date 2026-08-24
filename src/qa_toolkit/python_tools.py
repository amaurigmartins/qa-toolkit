"""Resolve central Python tools against one repository's typed settings."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qa_toolkit.deployment import tracked_regular_files
from qa_toolkit.models import (
    Consumer,
    Gate,
    PydoclintSettings,
    PylintSettings,
    PythonTool,
    RuffThresholds,
)


class PythonToolError(RuntimeError):
    """Report a Python setting that weakens or duplicates central ownership."""


@dataclass(frozen=True)
class PythonResolution:
    """Generated Python configurations, paths, and conditional gates."""

    configurations: dict[str, Path]
    digests: dict[str, str]
    paths: dict[str, tuple[str, ...]]
    gates: tuple[Gate, ...]
    environment: dict[str, str]


_OWNED_EXECUTABLES = frozenset(
    {
        "ast-grep",
        "coverage",
        "grain",
        "lint-imports",
        "mypy",
        "pydoclint",
        "pylint",
        "pytest",
        "ruff",
        "slop",
        "vulture",
    }
)
_CONFIG_NAMES = ("ruff", "mypy", "pylint", "pydoclint", "coverage", "vulture", "grain")


def _validate_scope(consumer: Consumer, target: Path) -> None:
    tracked = tracked_regular_files(target)
    overlays = (consumer.python.ruff, consumer.python.pylint, consumer.python.pydoclint)
    selected_paths = tuple(path for overlay in overlays if overlay for path in overlay.paths)
    missing = sorted(
        {
            path
            for path in selected_paths
            if path != "."
            and not any(item == path or item.startswith(f"{path}/") for item in tracked)
        }
    )
    if missing:
        raise PythonToolError("Python paths match no tracked input: " + ", ".join(missing))
    unmatched = sorted(
        {
            item.path
            for item in consumer.python.exceptions
            if not any(fnmatch.fnmatchcase(path, item.path) for path in tracked)
        }
    )
    if unmatched:
        raise PythonToolError(
            "Python exception paths match no tracked regular file: " + ", ".join(unmatched)
        )


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.setdefault(key, {})
    if not isinstance(value, dict):
        raise PythonToolError(f"central Python configuration {key} is not a table")
    return value


def _nested_table(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current = data
    for key in keys:
        current = _table(current, key)
    return current


def _string_list(data: dict[str, Any], key: str, context: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PythonToolError(f"{context} is not an array of strings")
    return value


def _stricter(value: int, table: dict[str, Any], key: str, label: str) -> None:
    central = table.get(key)
    if not isinstance(central, int) or isinstance(central, bool):
        raise PythonToolError(f"{label} has no central threshold")
    if value > central:
        raise PythonToolError(f"{label} threshold {value} is weaker than central {central}")
    table[key] = value


def _apply_thresholds(lint: dict[str, Any], thresholds: RuffThresholds) -> None:
    if thresholds.max_complexity is not None:
        _stricter(
            thresholds.max_complexity, _table(lint, "mccabe"), "max-complexity", "Ruff complexity"
        )
    pylint = _table(lint, "pylint")
    if thresholds.max_args is not None:
        _stricter(thresholds.max_args, pylint, "max-args", "Ruff arguments")
    if thresholds.max_returns is not None:
        _stricter(thresholds.max_returns, pylint, "max-returns", "Ruff returns")


def _ruff_active(rule: str, selected: list[str], ignored: list[str]) -> bool:
    return any(rule.startswith(item) for item in selected) and not any(
        rule.startswith(item) for item in ignored
    )


def _resolve_ruff(source: str, consumer: Consumer) -> str:
    data = tomllib.loads(source)
    lint = _table(data, "lint")
    selected = _string_list(lint, "select", "central Ruff select")
    ignored = _string_list(lint, "ignore", "central Ruff ignore")
    settings = consumer.python.ruff
    if settings is not None:
        repeated = sorted(set(settings.extend_select) & set(selected))
        if repeated:
            raise PythonToolError(
                "Ruff extend_select repeats central selectors: " + ", ".join(repeated)
            )
        unavailable = sorted(set(settings.enforce) - set(ignored))
        if unavailable:
            raise PythonToolError(
                "Ruff enforce may name only central ignored rules: " + ", ".join(unavailable)
            )
        lint["select"] = [*selected, *settings.extend_select]
        lint["ignore"] = [item for item in ignored if item not in settings.enforce]
        if settings.known_first_party:
            _table(lint, "isort")["known-first-party"] = list(settings.known_first_party)
        _apply_thresholds(lint, settings.thresholds)
    per_file = _table(lint, "per-file-ignores")
    active_select = _string_list(lint, "select", "resolved Ruff select")
    active_ignore = _string_list(lint, "ignore", "resolved Ruff ignore")
    for exception in consumer.python.exceptions:
        if exception.tool != PythonTool.RUFF:
            raise PythonToolError(f"unsupported Python exception tool: {exception.tool}")
        if not _ruff_active(exception.rule, active_select, active_ignore):
            raise PythonToolError(f"Ruff exception {exception.rule} is not active")
        existing = _string_list(per_file, exception.path, "central Ruff per-file ignores")
        per_file[exception.path] = [*existing, exception.rule]
    return _render_toml(data)


def _resolve_pylint(source: str, settings: PylintSettings | None) -> str:
    if settings is None:
        return source
    data = tomllib.loads(source)
    pylint = _nested_table(data, "tool", "pylint")
    messages = _table(pylint, "messages_control")
    enabled = _string_list(messages, "enable", "central Pylint enable")
    repeated = sorted(set(settings.enable) & set(enabled))
    if repeated:
        raise PythonToolError("Pylint enable repeats central rules: " + ", ".join(repeated))
    messages["enable"] = [*enabled, *settings.enable]
    if settings.min_similarity_lines is not None:
        _stricter(
            settings.min_similarity_lines,
            _table(pylint, "similarities"),
            "min-similarity-lines",
            "Pylint similarity",
        )
    return _render_toml(data)


def _resolve_pydoclint(source: str, settings: PydoclintSettings | None) -> str:
    if settings is None:
        return source
    data = tomllib.loads(source)
    values = _nested_table(data, "tool", "pydoclint")
    if settings.skip_checking_short_docstrings is not None:
        if settings.skip_checking_short_docstrings:
            raise PythonToolError(
                "Pydoclint short-docstring checking may only be tightened to false"
            )
        values["skip-checking-short-docstrings"] = False
    if settings.check_class_attributes is not None:
        if not settings.check_class_attributes:
            raise PythonToolError(
                "Pydoclint class-attribute checking may only be tightened to true"
            )
        values["check-class-attributes"] = True
    return _render_toml(data)


def _render_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    _render_table(lines, (), data, root=True)
    return "\n".join(lines).rstrip() + "\n"


def _render_table(
    lines: list[str], path: tuple[str, ...], data: dict[str, Any], *, root: bool = False
) -> None:
    scalars = [(key, value) for key, value in data.items() if not isinstance(value, dict)]
    children = [(key, value) for key, value in data.items() if isinstance(value, dict)]
    if not root:
        if lines and lines[-1]:
            lines.append("")
        lines.append("[" + ".".join(json.dumps(item) for item in path) + "]")
    for key, value in scalars:
        lines.append(f"{json.dumps(key)} = {_toml_value(value)}")
    for key, value in children:
        _render_table(lines, (*path, key), value)


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise PythonToolError(f"unsupported central TOML value: {value!r}")


def _atomic_configs(
    destination: Path, contents: dict[str, str]
) -> tuple[dict[str, Path], dict[str, str]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="python-", dir=destination.parent))
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    previous = destination.with_name(f"{destination.name}.previous")
    try:
        for name, content in contents.items():
            path = stage / f"{name}.toml"
            path.write_text(content, encoding="utf-8")
            paths[name] = destination / path.name
            digests[name] = hashlib.sha256(content.encode()).hexdigest()
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            os.replace(destination, previous)
        os.replace(stage, destination)
        if previous.exists():
            shutil.rmtree(previous)
        return paths, digests
    except Exception:
        if previous.exists() and not destination.exists():
            os.replace(previous, destination)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _import_linter_gate(target: Path, consumer: Consumer) -> tuple[Gate, str] | None:
    project = consumer.python.project or Path(".")
    relative = project / "pyproject.toml"
    path = target / relative
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise PythonToolError("refusing irregular Python project configuration")
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    tool = document.get("tool", {})
    if not isinstance(tool, dict):
        raise PythonToolError("Python project tool settings must be a table")
    if "importlinter" not in tool:
        return None
    settings = tool["importlinter"]
    if not isinstance(settings, dict) or not settings:
        raise PythonToolError("Import Linter settings must be a non-empty table")
    contracts = settings.get("contracts")
    if (
        not isinstance(contracts, list)
        or not contracts
        or not all(isinstance(item, dict) and item for item in contracts)
    ):
        raise PythonToolError("Import Linter settings require non-empty direction rules")
    if relative.as_posix() not in tracked_regular_files(target):
        raise PythonToolError("Import Linter settings must use a tracked pyproject.toml")
    digest = hashlib.sha256(
        json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        Gate(
            "python-import-directions",
            "check",
            ("{tool:import-linter}", "--config", relative.as_posix(), "--no-cache"),
            (relative.as_posix(), "**/*.py"),
            180,
            "blocking",
            (),
            (1,),
            (2,),
        ),
        digest,
    )


def _python_environment(target: Path, root: Path, consumer: Consumer) -> dict[str, str]:
    project = (target / (consumer.python.project or Path("."))).resolve()
    paths = [project, project / "src", root / "src"]
    for environment_root in (project / ".venv", target / ".venv"):
        paths.extend(sorted(environment_root.glob("lib/python*/site-packages")))
    existing = tuple(dict.fromkeys(path.resolve() for path in paths if path.exists()))
    cache = target / ".git" / "qat" / "cache"
    (cache / "coverage").mkdir(parents=True, exist_ok=True)
    (cache / "pylint").mkdir(parents=True, exist_ok=True)
    return {
        "COVERAGE_FILE": str(cache / "coverage" / ".coverage"),
        "PYLINTHOME": str(cache / "pylint"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(str(path) for path in existing),
    }


def resolve_python(target: Path, root: Path, consumer: Consumer) -> PythonResolution:
    """Validate and generate every selected Python tool input exactly once."""
    _validate_scope(consumer, target)
    central = root / "config" / "python"
    sources = {
        name: (central / f"{name}.toml").read_text(encoding="utf-8") for name in _CONFIG_NAMES
    }
    sources["ruff"] = _resolve_ruff(sources["ruff"], consumer)
    sources["pylint"] = _resolve_pylint(sources["pylint"], consumer.python.pylint)
    sources["pydoclint"] = _resolve_pydoclint(sources["pydoclint"], consumer.python.pydoclint)
    configurations, digests = _atomic_configs(target / ".qat/generated/python", sources)
    ruff = consumer.python.ruff
    project = (consumer.python.project or Path(".")).as_posix()
    paths = {
        "ruff": ruff.paths if ruff is not None and ruff.paths else (project,),
        "pylint": (
            consumer.python.pylint.paths
            if consumer.python.pylint is not None and consumer.python.pylint.paths
            else (str(Path(project) / "src"),)
        ),
        "pydoclint": (
            consumer.python.pydoclint.paths
            if consumer.python.pydoclint is not None and consumer.python.pydoclint.paths
            else (str(Path(project) / "src"),)
        ),
        "tests": (str(Path(project) / "tests"),),
    }
    extra: list[Gate] = []
    import_gate = _import_linter_gate(target, consumer)
    if import_gate is not None:
        gate, digest = import_gate
        extra.append(gate)
        digests["import-linter"] = digest
    return PythonResolution(
        configurations,
        digests,
        paths,
        tuple(extra),
        _python_environment(target, root, consumer),
    )


def owned_consumer_command(argv: tuple[str, ...]) -> str | None:
    """Return the centrally owned executable reached by a raw consumer argv."""
    if not argv:
        return None
    command = Path(argv[0]).name
    if command in _OWNED_EXECUTABLES:
        return command
    if command != "uv" or len(argv) < 3 or argv[1] != "run":
        return None
    index = 2
    options_with_values = {"--directory", "--group", "--project", "--python", "--with"}
    while index < len(argv):
        item = argv[index]
        if item == "--":
            index += 1
            break
        if not item.startswith("-"):
            break
        if item in options_with_values:
            index += 2
        else:
            index += 1
    if index < len(argv):
        candidate = Path(argv[index]).name
        if candidate in _OWNED_EXECUTABLES:
            return candidate
    return None
