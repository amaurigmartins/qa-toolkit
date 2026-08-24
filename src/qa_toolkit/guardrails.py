"""Evaluate bounded repository-local protected-path mutations."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_PATCH_HEADER = re.compile(r"^\*\*\* (?:Add|Delete|Update) File: (.+)$")
_PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$")
_MUTATING_PROGRAMS = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "dd",
        "install",
        "ln",
        "mkdir",
        "mv",
        "rm",
        "rmdir",
        "tee",
        "touch",
        "truncate",
    }
)
_GIT_READ_ONLY = frozenset(
    {
        "blame",
        "branch",
        "diff",
        "for-each-ref",
        "grep",
        "log",
        "ls-files",
        "ls-tree",
        "merge-base",
        "name-rev",
        "rev-list",
        "rev-parse",
        "show",
        "status",
        "tag",
    }
)
_SHELL_OPERATORS = frozenset({";", "&&", "||", "|", "&"})
_REDIRECTIONS = frozenset({">", ">>", "<>", "&>"})


@dataclass(frozen=True, slots=True)
class GuardrailDecision:
    """One allow or deny result with a concise denial reason."""

    denied: bool
    reason: str | None = None


def _validated_path(raw: str) -> PurePosixPath:
    if not raw or "\0" in raw or "\n" in raw or "\r" in raw or "\\" in raw:
        raise ValueError("hook path is malformed")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("hook path escapes the repository")
    return path


def _repository_path(raw: str, cwd: Path, target: Path) -> str | None:
    if not raw or raw.startswith("-") or any(marker in raw for marker in ("$", "`", "*", "?", "[")):
        return None
    path = Path(raw)
    candidate = path if path.is_absolute() else cwd / path
    normalized = Path(os.path.normpath(candidate))
    try:
        return normalized.relative_to(target).as_posix()
    except ValueError:
        return None


def _matches(path: str, protected: tuple[str, ...]) -> bool:
    return any(
        path == pattern.rstrip("/")
        or fnmatch.fnmatchcase(path, pattern)
        or (pattern.endswith("/**") and (path == pattern[:-3] or path.startswith(pattern[:-2])))
        for pattern in protected
    )


def _symlinked(target: Path, relative: str) -> bool:
    current = target
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        if current.is_symlink():
            return True
    return False


def extract_apply_patch_paths(command: str, cwd: Path, target: Path) -> tuple[str, ...]:
    """Extract every file touched by one exact apply_patch document."""
    if len(command.encode()) > 1_048_576:
        raise ValueError("apply_patch input exceeds one MiB")
    lines = command.splitlines()
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise ValueError("apply_patch input lacks exact boundary markers")
    paths = []
    for line in lines[1:-1]:
        match = _PATCH_HEADER.fullmatch(line) or _PATCH_MOVE.fullmatch(line)
        if match is None:
            continue
        path = _validated_path(match.group(1))
        candidate = Path(os.path.normpath(cwd / Path(*path.parts)))
        try:
            relative = candidate.relative_to(target).as_posix()
        except ValueError as error:
            raise ValueError("apply_patch path escapes the repository") from error
        if _symlinked(target, relative):
            raise ValueError(f"apply_patch path crosses a symlink: {relative}")
        try:
            candidate.resolve(strict=False).relative_to(target)
        except ValueError as error:
            raise ValueError(
                f"apply_patch path resolves outside the repository: {relative}"
            ) from error
        paths.append(relative)
    if not paths:
        raise ValueError("apply_patch input contains no file operation")
    return tuple(dict.fromkeys(paths))


def _tokens(command: str) -> tuple[str, ...]:
    if not command or len(command.encode()) > 1_048_576 or "\0" in command:
        raise ValueError("Bash input must be a bounded command")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return tuple(lexer)


def _segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    result: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SHELL_OPERATORS:
            if current:
                result.append(tuple(current))
                current = []
        else:
            current.append(token)
    if current:
        result.append(tuple(current))
    return tuple(result)


def _program(segment: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    index = 0
    while index < len(segment) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", segment[index]):
        index += 1
    if index < len(segment) and Path(segment[index]).name == "env":
        index += 1
        while index < len(segment) and (
            segment[index].startswith("-")
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", segment[index])
        ):
            index += 1
    if index >= len(segment):
        return "", ()
    return Path(segment[index]).name, segment[index + 1 :]


def _mutating(program: str, arguments: tuple[str, ...]) -> bool:
    if program in _MUTATING_PROGRAMS:
        return True
    if program in {"sed", "perl"}:
        return any(argument == "-i" or argument.startswith("-i") for argument in arguments)
    if program == "git":
        subcommand = next((item for item in arguments if not item.startswith("-")), "")
        return subcommand not in _GIT_READ_ONLY
    return any(argument in _REDIRECTIONS for argument in arguments)


def _bash_paths(
    command: str, cwd: Path, target: Path, protected: tuple[str, ...]
) -> tuple[str, ...]:
    found = []
    for segment in _segments(_tokens(command)):
        program, arguments = _program(segment)
        if not _mutating(program, arguments):
            continue
        for index, argument in enumerate(arguments):
            if argument in _REDIRECTIONS and index + 1 < len(arguments):
                candidate = _repository_path(arguments[index + 1], cwd, target)
            else:
                candidate = _repository_path(argument, cwd, target)
            if candidate is not None and (
                _matches(candidate, protected) or _symlinked(target, candidate)
            ):
                found.append(candidate)
        if (
            program == "git"
            and not found
            and any(item in {".", "-A", "--all", "--hard"} for item in arguments)
        ):
            found.append("repository-wide Git mutation")
    return tuple(dict.fromkeys(found))


def evaluate(
    tool_name: str,
    tool_input: dict[str, object],
    *,
    cwd: Path,
    target: Path,
    protected: tuple[str, ...],
) -> GuardrailDecision:
    """Deny only bounded mutations of protected repository paths."""
    if tool_name not in {"Bash", "apply_patch"}:
        return GuardrailDecision(False)
    command = tool_input.get("command")
    if not isinstance(command, str):
        return GuardrailDecision(True, "tool input has no bounded command")
    try:
        if tool_name == "apply_patch":
            paths = tuple(
                path
                for path in extract_apply_patch_paths(command, cwd, target)
                if _matches(path, protected)
            )
        else:
            paths = _bash_paths(command, cwd, target, protected)
    except (OSError, ValueError) as error:
        return GuardrailDecision(True, f"cannot prove protected paths are untouched: {error}")
    if paths:
        return GuardrailDecision(True, "protected repository mutation: " + ", ".join(paths))
    return GuardrailDecision(False)
