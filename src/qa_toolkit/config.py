"""Load explicit toolkit profiles and consumer declarations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, Literal, overload

from qa_toolkit.models import (
    ConfigurationError,
    ConfigurationLink,
    Consumer,
    ConsumerGate,
    Gate,
    Hook,
    MypySettings,
    Profile,
    PydoclintSettings,
    PylintSettings,
    PythonException,
    PythonSettings,
    PythonTool,
    RuffSettings,
    RuffThresholds,
    closed_keys,
    relative_path,
    string,
    string_list,
)
from qa_toolkit.paths import toolkit_root
from qa_toolkit.registry import load_registry

_RUFF_SELECTOR = re.compile(r"[A-Z]+[0-9]*")
_PYLINT_RULE = re.compile(r"[a-z][a-z0-9-]*")
_PYTHON_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_GIT_HOOK_EVENTS = frozenset({"commit-msg", "pre-commit", "pre-push"})
_CODEX_HOOK_EVENTS = frozenset(
    {"SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop", "SessionEnd"}
)


def _document(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path}: expected a table")
    return value


def _schema(value: dict[str, Any], path: Path) -> None:
    if value.get("schema_version") != 1:
        raise ConfigurationError(f"{path}: schema_version must be 1")


def _table_array(value: object, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigurationError(f"{context}: expected an array of tables")
    return value


def _positive_integer(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{context}: expected a positive integer")
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{context}: expected a boolean")
    return value


def _unique_strings(value: object, context: str) -> tuple[str, ...]:
    values = string_list(value if value is not None else [], context)
    if len(values) != len(set(values)):
        raise ConfigurationError(f"{context}: duplicate values")
    return values


def _python_paths(value: object, context: str) -> tuple[str, ...]:
    paths = _unique_strings(value, context)
    for item in paths:
        path = PurePosixPath(item)
        if (
            path.is_absolute()
            or item != path.as_posix()
            or any(part in {"", ".."} for part in path.parts)
            or any(character in item for character in "*?[]\\")
        ):
            raise ConfigurationError(f"{context}: expected bounded repository paths")
    return paths


def _ruff_settings(value: object, context: str) -> RuffSettings:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{context}: expected a table")
    closed_keys(
        value,
        {"extend_select", "enforce", "paths", "known_first_party", "thresholds"},
        context,
    )
    extend = _unique_strings(value.get("extend_select"), f"{context}.extend_select")
    enforce = _unique_strings(value.get("enforce"), f"{context}.enforce")
    invalid = [item for item in (*extend, *enforce) if _RUFF_SELECTOR.fullmatch(item) is None]
    if invalid:
        raise ConfigurationError(f"{context}: invalid Ruff selectors: {', '.join(invalid)}")
    modules = _unique_strings(value.get("known_first_party"), f"{context}.known_first_party")
    invalid_modules = [item for item in modules if _PYTHON_MODULE.fullmatch(item) is None]
    if invalid_modules:
        raise ConfigurationError(f"{context}: invalid Python modules: {', '.join(invalid_modules)}")
    thresholds_raw = value.get("thresholds", {})
    if not isinstance(thresholds_raw, dict):
        raise ConfigurationError(f"{context}.thresholds: expected a table")
    closed_keys(
        thresholds_raw,
        {"max_complexity", "max_args", "max_returns"},
        f"{context}.thresholds",
    )
    return RuffSettings(
        extend_select=extend,
        enforce=enforce,
        paths=_python_paths(value.get("paths"), f"{context}.paths"),
        known_first_party=modules,
        thresholds=RuffThresholds(
            **{
                key: _positive_integer(thresholds_raw[key], f"{context}.thresholds.{key}")
                if key in thresholds_raw
                else None
                for key in ("max_complexity", "max_args", "max_returns")
            }
        ),
    )


def _pylint_settings(value: object, context: str) -> PylintSettings:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{context}: expected a table")
    closed_keys(value, {"enable", "paths", "min_similarity_lines"}, context)
    enabled = _unique_strings(value.get("enable"), f"{context}.enable")
    invalid = [item for item in enabled if _PYLINT_RULE.fullmatch(item) is None]
    if invalid:
        raise ConfigurationError(f"{context}: invalid Pylint rules: {', '.join(invalid)}")
    return PylintSettings(
        enable=enabled,
        paths=_python_paths(value.get("paths"), f"{context}.paths"),
        min_similarity_lines=(
            _positive_integer(value["min_similarity_lines"], f"{context}.min_similarity_lines")
            if "min_similarity_lines" in value
            else None
        ),
    )


def _mypy_settings(value: object, context: str) -> MypySettings:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{context}: expected a table")
    closed_keys(
        value,
        {"plugins", "mypy_path", "explicit_package_bases", "namespace_packages"},
        context,
    )
    plugins = _unique_strings(value.get("plugins"), f"{context}.plugins")
    invalid = [item for item in plugins if _PYTHON_MODULE.fullmatch(item) is None]
    if invalid:
        raise ConfigurationError(f"{context}: invalid MyPy plugins: {', '.join(invalid)}")
    return MypySettings(
        plugins=plugins,
        mypy_path=_python_paths(value.get("mypy_path"), f"{context}.mypy_path"),
        explicit_package_bases=(
            _boolean(value["explicit_package_bases"], f"{context}.explicit_package_bases")
            if "explicit_package_bases" in value
            else None
        ),
        namespace_packages=(
            _boolean(value["namespace_packages"], f"{context}.namespace_packages")
            if "namespace_packages" in value
            else None
        ),
    )


def _pydoclint_settings(value: object, context: str) -> PydoclintSettings:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{context}: expected a table")
    closed_keys(
        value,
        {"paths", "skip_checking_short_docstrings", "check_class_attributes"},
        context,
    )
    return PydoclintSettings(
        paths=_python_paths(value.get("paths"), f"{context}.paths"),
        skip_checking_short_docstrings=(
            _boolean(
                value["skip_checking_short_docstrings"],
                f"{context}.skip_checking_short_docstrings",
            )
            if "skip_checking_short_docstrings" in value
            else None
        ),
        check_class_attributes=(
            _boolean(value["check_class_attributes"], f"{context}.check_class_attributes")
            if "check_class_attributes" in value
            else None
        ),
    )


def _python_exceptions(value: object, context: str) -> tuple[PythonException, ...]:
    entries = _table_array(value, context)
    result: list[PythonException] = []
    for index, raw in enumerate(entries):
        item_context = f"{context}[{index}]"
        closed_keys(raw, {"tool", "rule", "path", "reason"}, item_context)
        try:
            tool = PythonTool(string(raw, "tool", item_context))
        except ValueError as error:
            raise ConfigurationError(f"{item_context}.tool: unsupported tool") from error
        rule = string(raw, "rule", item_context)
        if _RUFF_SELECTOR.fullmatch(rule) is None:
            raise ConfigurationError(f"{item_context}.rule: invalid Ruff rule code")
        path = string(raw, "path", item_context)
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
            raise ConfigurationError(f"{item_context}.path: expected a bounded repository glob")
        reason = string(raw, "reason", item_context).strip()
        if not reason:
            raise ConfigurationError(f"{item_context}.reason: expected a non-empty reason")
        result.append(PythonException(tool, rule, path, reason))
    identities = {(item.tool, item.rule, item.path) for item in result}
    if len(identities) != len(result):
        raise ConfigurationError(f"{context}: duplicate tool, rule, and path")
    return tuple(sorted(result))


def _exit_codes(value: object, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in value
    ):
        raise ConfigurationError(f"{context}: expected positive integer exit codes")
    result = tuple(value)
    if len(result) != len(set(result)):
        raise ConfigurationError(f"{context}: duplicate exit code")
    return result


@overload
def _gate(raw: dict[str, Any], context: str, *, consumer: Literal[True]) -> ConsumerGate: ...


@overload
def _gate(raw: dict[str, Any], context: str, *, consumer: Literal[False]) -> Gate: ...


def _gate(raw: dict[str, Any], context: str, *, consumer: bool) -> Gate | ConsumerGate:
    closed_keys(
        raw,
        {
            "id",
            "phase",
            "argv",
            "triggers",
            "timeout",
            "severity",
            "variants",
            "finding_exit_codes",
            "execution_error_exit_codes",
            *(("before",) if consumer else ()),
        },
        context,
    )
    phase = string(raw, "phase", context)
    if phase not in {"check", "sentinel"}:
        raise ConfigurationError(f"{context}.phase: expected check or sentinel")
    severity = string(raw, "severity", context)
    if severity not in {"blocking", "advisory"}:
        raise ConfigurationError(f"{context}.severity: expected blocking or advisory")
    identifier = string(raw, "id", context)
    argv = string_list(raw.get("argv"), f"{context}.argv")
    triggers = string_list(raw.get("triggers"), f"{context}.triggers")
    timeout = _positive_integer(raw.get("timeout"), f"{context}.timeout")
    variants = string_list(raw.get("variants"), f"{context}.variants")
    finding_exits = _exit_codes(raw.get("finding_exit_codes"), f"{context}.finding_exit_codes")
    error_exits = _exit_codes(
        raw.get("execution_error_exit_codes"), f"{context}.execution_error_exit_codes"
    )
    overlap = set(finding_exits) & set(error_exits)
    if overlap:
        raise ConfigurationError(f"{context}: exit classifications overlap")
    if consumer:
        before = string(raw, "before", context) if "before" in raw else None
        return ConsumerGate(
            identifier,
            phase,
            argv,
            triggers,
            timeout,
            severity,
            variants,
            finding_exits,
            error_exits,
            before,
        )
    return Gate(
        identifier,
        phase,
        argv,
        triggers,
        timeout,
        severity,
        variants,
        finding_exits,
        error_exits,
    )


def load_profile(name: str, root: Path | None = None) -> Profile:
    """Load one closed, explicit repository profile."""
    repository = root or toolkit_root()
    path = repository / "profiles" / f"{name}.toml"
    value = _document(path)
    _schema(value, path)
    closed_keys(
        value,
        {"schema_version", "name", "tools", "configurations", "gates", "hooks", "skills"},
        str(path),
    )
    declared_name = string(value, "name", str(path))
    if declared_name != name:
        raise ConfigurationError(f"{path}: name must match the file name")
    tools = string_list(value.get("tools"), f"{path}.tools")
    if len(tools) != len(set(tools)):
        raise ConfigurationError(f"{path}.tools: duplicate tool ID")
    known_tools = {tool.tool_id for tool in load_registry(repository)}
    unknown_tools = set(tools) - known_tools
    if unknown_tools:
        raise ConfigurationError(f"{path}.tools: unknown tools: {', '.join(sorted(unknown_tools))}")

    configurations: list[ConfigurationLink] = []
    for index, raw in enumerate(
        _table_array(value.get("configurations"), f"{path}.configurations")
    ):
        context = f"{path}.configurations[{index}]"
        closed_keys(raw, {"id", "source", "destination", "mode"}, context)
        mode = string(raw, "mode", context)
        if mode not in {"symlink", "copy"}:
            raise ConfigurationError(f"{context}.mode: expected symlink or copy")
        source = relative_path(string(raw, "source", context), f"{context}.source")
        destination = relative_path(string(raw, "destination", context), f"{context}.destination")
        if destination.parts[0] != ".qat":
            raise ConfigurationError(f"{context}.destination: managed configuration must use .qat/")
        if not (repository / source).is_file():
            raise ConfigurationError(f"{context}.source: central file does not exist")
        configurations.append(
            ConfigurationLink(string(raw, "id", context), source, destination, mode)
        )
    identifiers = [item.identifier for item in configurations]
    if len(identifiers) != len(set(identifiers)):
        raise ConfigurationError(f"{path}.configurations: duplicate ID")
    destinations = [item.destination for item in configurations]
    if len(destinations) != len(set(destinations)):
        raise ConfigurationError(f"{path}.configurations: duplicate destination")

    gates = tuple(
        _gate(raw, f"{path}.gates[{index}]", consumer=False)
        for index, raw in enumerate(_table_array(value.get("gates"), f"{path}.gates"))
    )
    gate_ids = [item.identifier for item in gates]
    if len(gate_ids) != len(set(gate_ids)):
        raise ConfigurationError(f"{path}.gates: duplicate ID")

    hooks: list[Hook] = []
    for index, raw in enumerate(_table_array(value.get("hooks"), f"{path}.hooks")):
        context = f"{path}.hooks[{index}]"
        closed_keys(raw, {"kind", "event", "entry", "enabled"}, context)
        kind = string(raw, "kind", context)
        if kind not in {"git", "codex"}:
            raise ConfigurationError(f"{context}.kind: expected git or codex")
        event = string(raw, "event", context)
        events = _GIT_HOOK_EVENTS if kind == "git" else _CODEX_HOOK_EVENTS
        if event not in events:
            raise ConfigurationError(f"{context}.event: unsupported {kind} event")
        entry = relative_path(string(raw, "entry", context), f"{context}.entry")
        expected = Path("library") / f"{kind}-hooks" / event
        if expected not in entry.parents:
            raise ConfigurationError(
                f"{context}.entry: expected a script below {expected.as_posix()}"
            )
        source = repository / entry
        if not source.is_file() or source.is_symlink():
            raise ConfigurationError(f"{context}.entry: central hook does not exist")
        if not os.access(source, os.X_OK):
            raise ConfigurationError(f"{context}.entry: central hook is not executable")
        enabled = _boolean(raw.get("enabled", True), f"{context}.enabled")
        hooks.append(Hook(kind, event, entry, enabled))
    hook_ids = [(item.kind, item.event, item.entry.name) for item in hooks]
    if len(hook_ids) != len(set(hook_ids)):
        raise ConfigurationError(f"{path}.hooks: duplicate kind, event, and entry name")

    skills = tuple(
        relative_path(item, f"{path}.skills")
        for item in string_list(value.get("skills"), f"{path}.skills")
    )
    if len({item.name for item in skills}) != len(skills):
        raise ConfigurationError(f"{path}.skills: duplicate deployed skill name")
    for skill in skills:
        source = repository / skill
        if Path("library/skills") not in skill.parents:
            raise ConfigurationError(f"{path}.skills: expected a library/skills directory")
        if not source.is_dir() or source.is_symlink():
            raise ConfigurationError(f"{path}.skills: central skill does not exist: {skill}")
        entry = source / "SKILL.md"
        if not entry.is_file() or entry.is_symlink():
            raise ConfigurationError(f"{path}.skills: skill has no ordinary SKILL.md: {skill}")

    return Profile(declared_name, tools, tuple(configurations), gates, tuple(hooks), skills, path)


def _optional_path(value: object, context: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{context}: expected a non-empty relative path")
    if value == "." and context.endswith(".python.project"):
        return Path(".")
    return relative_path(value, context)


def load_consumer(target: Path) -> Consumer:
    """Load one tracked consumer `.qat.toml` declaration."""
    path = target / ".qat.toml"
    value = _document(path)
    _schema(value, path)
    closed_keys(
        value,
        {
            "schema_version",
            "profile",
            "native_configurations",
            "vocabulary",
            "ast_grep",
            "python",
            "gates",
            "protected_paths",
            "work",
        },
        str(path),
    )
    native = tuple(
        relative_path(item, f"{path}.native_configurations")
        for item in string_list(
            value.get("native_configurations", []), f"{path}.native_configurations"
        )
    )
    protected = tuple(
        relative_path(item, f"{path}.protected_paths")
        for item in string_list(value.get("protected_paths", []), f"{path}.protected_paths")
    )

    vocabulary = value.get("vocabulary", {})
    if not isinstance(vocabulary, dict):
        raise ConfigurationError(f"{path}.vocabulary: expected a table")
    closed_keys(vocabulary, {"file", "additions", "allowances"}, f"{path}.vocabulary")
    additions = string_list(vocabulary.get("additions", []), f"{path}.vocabulary.additions")
    allowances = string_list(vocabulary.get("allowances", []), f"{path}.vocabulary.allowances")

    ast_grep = value.get("ast_grep", {})
    if not isinstance(ast_grep, dict):
        raise ConfigurationError(f"{path}.ast_grep: expected a table")
    closed_keys(ast_grep, {"config", "tests"}, f"{path}.ast_grep")

    python = value.get("python", {})
    if not isinstance(python, dict):
        raise ConfigurationError(f"{path}.python: expected a table")
    closed_keys(
        python,
        {"project", "ruff", "mypy", "pylint", "pydoclint", "exceptions"},
        f"{path}.python",
    )
    python_settings = PythonSettings(
        project=_optional_path(python.get("project"), f"{path}.python.project"),
        ruff=_ruff_settings(python["ruff"], f"{path}.python.ruff") if "ruff" in python else None,
        mypy=(_mypy_settings(python["mypy"], f"{path}.python.mypy") if "mypy" in python else None),
        pylint=(
            _pylint_settings(python["pylint"], f"{path}.python.pylint")
            if "pylint" in python
            else None
        ),
        pydoclint=(
            _pydoclint_settings(python["pydoclint"], f"{path}.python.pydoclint")
            if "pydoclint" in python
            else None
        ),
        exceptions=_python_exceptions(python.get("exceptions", []), f"{path}.python.exceptions"),
    )

    gates = tuple(
        _gate(raw, f"{path}.gates[{index}]", consumer=True)
        for index, raw in enumerate(_table_array(value.get("gates", []), f"{path}.gates"))
    )
    gate_ids = [item.identifier for item in gates]
    if len(gate_ids) != len(set(gate_ids)):
        raise ConfigurationError(f"{path}.gates: duplicate ID")

    work = value.get("work")
    if not isinstance(work, dict):
        raise ConfigurationError(f"{path}.work: expected a table")
    closed_keys(work, {"state_directory", "require_allowed_paths"}, f"{path}.work")
    require_allowed = work.get("require_allowed_paths")
    if not isinstance(require_allowed, bool):
        raise ConfigurationError(f"{path}.work.require_allowed_paths: expected a boolean")
    work_state = relative_path(
        string(work, "state_directory", f"{path}.work"), f"{path}.work.state_directory"
    )
    if work_state.parts[:2] != (".git", "qat") or len(work_state.parts) < 3:
        raise ConfigurationError(
            f"{path}.work.state_directory: expected a directory below .git/qat"
        )

    return Consumer(
        profile=string(value, "profile", str(path)),
        native_configurations=native,
        vocabulary_file=_optional_path(vocabulary.get("file"), f"{path}.vocabulary.file"),
        vocabulary_additions=additions,
        vocabulary_allowances=allowances,
        ast_grep_config=_optional_path(ast_grep.get("config"), f"{path}.ast_grep.config"),
        ast_grep_tests=_optional_path(ast_grep.get("tests"), f"{path}.ast_grep.tests"),
        python=python_settings,
        gates=gates,
        protected_paths=protected,
        work_state_directory=work_state,
        work_require_allowed_paths=require_allowed,
        source=path,
    )


def digest_profile(profile: Profile) -> str:
    """Return the digest of the exact tracked profile bytes."""
    return hashlib.sha256(profile.source.read_bytes()).hexdigest()


def digest_consumer(consumer: Consumer) -> str:
    """Return the digest of the declaration and every declared rule input."""
    target = consumer.source.parent
    selected = [consumer.source.relative_to(target), *consumer.native_configurations]
    selected.extend(
        path
        for path in (
            consumer.vocabulary_file,
            consumer.ast_grep_config,
            consumer.ast_grep_tests,
            (
                (consumer.python.project or Path(".")) / "pyproject.toml"
                if (target / (consumer.python.project or Path(".")) / "pyproject.toml").is_file()
                else None
            ),
        )
        if path is not None
    )
    for gate in consumer.gates:
        command = Path(gate.argv[0])
        if not command.is_absolute() and len(command.parts) > 1 and (target / command).exists():
            selected.append(command)
    hasher = hashlib.sha256()
    files: set[Path] = set()
    for relative in selected:
        path = target / relative
        if path.is_dir():
            files.update(
                item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
            )
        elif path.is_file():
            files.add(path)
    for path in sorted(files):
        relative_bytes = path.relative_to(target).as_posix().encode()
        hasher.update(len(relative_bytes).to_bytes(8, "big"))
        hasher.update(relative_bytes)
        content = path.read_bytes()
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return hasher.hexdigest()


def profile_summary(profile: Profile) -> str:
    """Serialise stable profile facts for command output."""
    return json.dumps(
        {
            "name": profile.name,
            "tools": list(profile.tools),
            "configurations": [item.identifier for item in profile.configurations],
            "gates": [item.identifier for item in profile.gates],
            "hooks": [f"{item.kind}:{item.event}" for item in profile.hooks],
            "skills": [str(item) for item in profile.skills],
            "digest": digest_profile(profile),
        },
        sort_keys=True,
    )
