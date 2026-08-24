"""Closed schema models for profiles and consumer declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class ConfigurationError(RuntimeError):
    """Report invalid tracked configuration."""


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


@dataclass(frozen=True)
class Hook:
    """One repository hook entry selected by a profile."""

    kind: str
    event: str
    entry: Path


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
    python_project: Path | None
    gates: tuple[ConsumerGate, ...]
    protected_paths: tuple[Path, ...]
    work_state_directory: Path
    work_require_allowed_paths: bool
    source: Path
