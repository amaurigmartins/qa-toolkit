"""Closed schema models for profiles and consumer declarations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any


class ConfigurationError(RuntimeError):
    """Report invalid tracked configuration."""


class PythonTool(StrEnum):
    """Python analyser that supports a bounded consumer exception."""

    RUFF = "ruff"


@dataclass(frozen=True)
class RuffThresholds:
    """Optional stricter Ruff limits selected by a repository."""

    max_complexity: int | None = None
    max_args: int | None = None
    max_returns: int | None = None


@dataclass(frozen=True)
class RuffSettings:
    """Typed additions to the central Ruff configuration."""

    extend_select: tuple[str, ...] = ()
    enforce: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    known_first_party: tuple[str, ...] = ()
    thresholds: RuffThresholds = RuffThresholds()


@dataclass(frozen=True)
class PylintSettings:
    """Typed additions to the central Pylint configuration."""

    enable: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    min_similarity_lines: int | None = None


@dataclass(frozen=True)
class PydoclintSettings:
    """Typed additions to the central Pydoclint configuration."""

    paths: tuple[str, ...] = ()
    skip_checking_short_docstrings: bool | None = None
    check_class_attributes: bool | None = None


@dataclass(frozen=True)
class MypySettings:
    """Typed additions to the central strict MyPy configuration."""

    plugins: tuple[str, ...] = ()
    mypy_path: tuple[str, ...] = ()
    explicit_package_bases: bool | None = None
    namespace_packages: bool | None = None


@dataclass(frozen=True, order=True)
class PythonException:
    """One rule, bounded path, and reason-bearing analyser exception."""

    tool: PythonTool
    rule: str
    path: str
    reason: str


@dataclass(frozen=True)
class PythonSettings:
    """Python project location and optional stricter tool settings."""

    project: Path | None = None
    ruff: RuffSettings | None = None
    mypy: MypySettings | None = None
    pylint: PylintSettings | None = None
    pydoclint: PydoclintSettings | None = None
    exceptions: tuple[PythonException, ...] = ()


def closed_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    """Reject keys outside a closed schema."""
    unknown = set(value) - allowed
    if unknown:
        raise ConfigurationError(f"{context}: unknown fields: {', '.join(sorted(unknown))}")


def string(value: dict[str, Any], key: str, context: str) -> str:
    """Read one required non-empty string."""
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ConfigurationError(f"{context}.{key}: expected a non-empty string")
    return result


def string_list(value: object, context: str) -> tuple[str, ...]:
    """Read a list of non-empty strings."""
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigurationError(f"{context}: expected an array of non-empty strings")
    return tuple(value)


def relative_path(value: str, context: str) -> Path:
    """Reject absolute paths and parent traversal."""
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise ConfigurationError(f"{context}: expected a bounded relative path")
    return Path(*posix.parts)


@dataclass(frozen=True)
class ConfigurationLink:
    """One centrally owned configuration deployment."""

    identifier: str
    source: Path
    destination: Path
    mode: str


@dataclass(frozen=True)
class Gate:
    """One ordered quality command."""

    identifier: str
    phase: str
    argv: tuple[str, ...]
    triggers: tuple[str, ...]
    timeout: int
    severity: str
    variants: tuple[str, ...]
    finding_exit_codes: tuple[int, ...]
    execution_error_exit_codes: tuple[int, ...]


@dataclass(frozen=True)
class Hook:
    """One repository hook entry selected by a profile."""

    kind: str
    event: str
    entry: Path
    enabled: bool


@dataclass(frozen=True)
class Profile:
    """One explicit repository profile."""

    name: str
    tools: tuple[str, ...]
    configurations: tuple[ConfigurationLink, ...]
    gates: tuple[Gate, ...]
    hooks: tuple[Hook, ...]
    skills: tuple[Path, ...]
    source: Path


@dataclass(frozen=True)
class ConsumerGate:
    """One additive repository-owned argument-array gate."""

    identifier: str
    phase: str
    argv: tuple[str, ...]
    triggers: tuple[str, ...]
    timeout: int
    severity: str
    variants: tuple[str, ...]
    finding_exit_codes: tuple[int, ...]
    execution_error_exit_codes: tuple[int, ...]
    before: str | None = None


@dataclass(frozen=True)
class Consumer:
    """Tracked repository selection and native settings."""

    profile: str
    native_configurations: tuple[Path, ...]
    vocabulary_file: Path | None
    vocabulary_additions: tuple[str, ...]
    vocabulary_allowances: tuple[str, ...]
    ast_grep_config: Path | None
    ast_grep_tests: Path | None
    python: PythonSettings
    gates: tuple[ConsumerGate, ...]
    protected_paths: tuple[Path, ...]
    work_state_directory: Path
    work_require_allowed_paths: bool
    source: Path
