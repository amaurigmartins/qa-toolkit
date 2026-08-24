"""Run the owned terminology and prose tools against tracked reader text."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from qa_toolkit.acronyms import (
    GLOBAL_ACRONYMS,
    AcronymOccurrence,
    established_acronyms,
    unresolved_first_uses,
)
from qa_toolkit.corpus import CorpusError, build_corpus, load_corpus
from qa_toolkit.deployment import DeploymentError, resolve_target, tracked_regular_files
from qa_toolkit.documenter import documenter_markdown_view
from qa_toolkit.julia_docstrings import julia_docstring_view
from qa_toolkit.latex import latex_prose_view_with_map
from qa_toolkit.registry import RegistryError, executable_path, select_tools
from qa_toolkit.source_decisions import classify_source

_PROSE_SUFFIXES = frozenset({".jl", ".markdown", ".md", ".py", ".tex"})
_SPELLING_SUFFIXES = _PROSE_SUFFIXES
_LICENSE_NAMES = frozenset({"copying", "license", "notice"})
_DIRECTIVE = re.compile(r"(?i)(?:<!--|#=?|%)\s*vale\s+(?:off|on|[a-z][a-z0-9_.-]*\s*=)")


class TextToolError(RuntimeError):
    """Report an invalid source view or text-tool execution."""


@dataclass(frozen=True, slots=True)
class _Alias:
    """Map one staged Markdown view back to its tracked source."""

    path: str
    column_offsets: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Alert:
    """One normalised Vale result at its tracked source location."""

    path: str
    line: int
    column: int
    check: str
    severity: str
    match: str
    message: str


def _source_paths(target: Path, suffixes: frozenset[str]) -> tuple[str, ...]:
    corpus = load_corpus()
    selected: list[str] = []
    for relative in tracked_regular_files(target):
        path = PurePosixPath(relative)
        if path.suffix.casefold() not in suffixes and path.name.casefold() not in _LICENSE_NAMES:
            continue
        try:
            source = (target / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise TextToolError(f"cannot read tracked text {relative}: {error}") from error
        decision = classify_source(relative, source, corpus)
        if decision.classification == "source":
            selected.append(relative)
        else:
            print(
                f"source-decision\t{relative}\t{decision.classification}\t{decision.reason}",
                file=sys.stderr,
            )
    return tuple(selected)


def _stage_view(
    target: Path,
    relative: str,
    staging: Path,
    *,
    extract_python: bool = False,
) -> tuple[str, _Alias | None, str]:
    source = (target / relative).read_text(encoding="utf-8")
    suffix = PurePosixPath(relative).suffix.casefold()
    offsets: tuple[int, ...] | None = None
    if suffix == ".jl":
        julia = julia_docstring_view(source)
        rendered = documenter_markdown_view(julia.text).text
        offsets = julia.column_offsets
    elif suffix == ".tex":
        latex = latex_prose_view_with_map(source)
        rendered = latex.text
        offsets = latex.column_offsets
    elif suffix in {".md", ".markdown"}:
        rendered = documenter_markdown_view(source).text
        offsets = (0,) * len(source.splitlines())
    elif suffix == ".py" and not extract_python:
        return relative, None, source
    elif suffix == ".py":
        rendered = _python_docstring_view(source)
        offsets = (0,) * len(source.splitlines())
    else:
        rendered = source
        offsets = (0,) * len(source.splitlines())
    if rendered == source and suffix in {".md", ".markdown"}:
        return relative, None, source
    staged = staging.joinpath(*PurePosixPath(relative).parts).with_name(
        PurePosixPath(relative).name + ".md"
    )
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(rendered, encoding="utf-8", newline="")
    return str(staged), _Alias(relative, offsets), source


def _directive_view(relative: str, source: str) -> str:
    """Return only the text where Vale can interpret inline directives."""
    suffix = PurePosixPath(relative).suffix.casefold()
    if suffix == ".py":
        return _python_docstring_view(source)
    if suffix == ".jl":
        return documenter_markdown_view(julia_docstring_view(source).text).text
    if suffix == ".tex":
        return latex_prose_view_with_map(source).text
    if suffix in {".md", ".markdown"}:
        return documenter_markdown_view(source).text
    return source


def _python_docstring_view(source: str) -> str:
    """Return a position-preserving view of Python docstring text."""
    tree = ast.parse(source)
    ranges = {
        (
            statement.value.lineno,
            statement.value.col_offset,
            statement.value.end_lineno,
            statement.value.end_col_offset,
        )
        for owner in ast.walk(tree)
        if isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and owner.body
        and isinstance((statement := owner.body[0]), ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
        and statement.value.end_lineno is not None
        and statement.value.end_col_offset is not None
    }
    lines = source.splitlines(keepends=True)
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    rendered = [character if character in "\r\n" else " " for character in source]
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type != tokenize.STRING:
            continue
        start_line, start_column = token.start
        end_line, end_column = token.end
        matching = next(
            (
                item
                for item in ranges
                if item[0] == start_line
                and item[1] == start_column
                and item[2] == end_line
                and item[3] == end_column
            ),
            None,
        )
        if matching is None:
            continue
        delimiter = re.match(r"(?i)^[rub]*('''|\"\"\"|'|\")", token.string)
        if delimiter is None:
            raise TextToolError("unsupported Python docstring literal")
        quote = delimiter.group(1)
        left = starts[start_line - 1] + start_column + delimiter.end()
        right = starts[end_line - 1] + end_column - len(quote)
        rendered[left:right] = source[left:right]
    return "".join(rendered)


def _run(argv: tuple[str, ...], target: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=target,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TextToolError(f"cannot execute {Path(argv[0]).name}: {error}") from error


def _mapped_path(raw: str, target: Path, aliases: dict[str, _Alias]) -> tuple[str, _Alias | None]:
    candidate = Path(raw)
    absolute = candidate.resolve() if candidate.is_absolute() else (target / candidate).resolve()
    alias = aliases.get(str(absolute))
    if alias is not None:
        return alias.path, alias
    try:
        return absolute.relative_to(target).as_posix(), None
    except ValueError as error:
        raise TextToolError(f"Vale reported an unknown input path: {raw}") from error


def _parse_alerts(output: str, target: Path, aliases: dict[str, _Alias]) -> tuple[_Alert, ...]:
    try:
        document: Any = json.loads(output or "{}")
    except json.JSONDecodeError as error:
        raise TextToolError(f"Vale returned invalid JSON: {error}") from error
    if not isinstance(document, dict) or not all(
        isinstance(path, str) and isinstance(items, list) for path, items in document.items()
    ):
        raise TextToolError("Vale returned an invalid finding document")
    alerts: list[_Alert] = []
    for raw_path, items in document.items():
        path, alias = _mapped_path(raw_path, target, aliases)
        for item in items:
            if not isinstance(item, dict):
                raise TextToolError("Vale returned an invalid finding")
            line = item.get("Line")
            span = item.get("Span")
            if (
                not isinstance(line, int)
                or line < 1
                or not isinstance(span, list)
                or not span
                or not isinstance(span[0], int)
            ):
                raise TextToolError("Vale returned an invalid finding location")
            offset = 0
            if alias is not None:
                if line > len(alias.column_offsets):
                    raise TextToolError("Vale finding exceeds the staged source map")
                offset = alias.column_offsets[line - 1]
            check = item.get("Check")
            severity = item.get("Severity")
            match = item.get("Match")
            message = item.get("Message")
            if not (
                isinstance(check, str)
                and isinstance(severity, str)
                and isinstance(match, str)
                and isinstance(message, str)
            ):
                raise TextToolError("Vale returned an incomplete finding")
            alerts.append(_Alert(path, line, span[0] + offset, check, severity, match, message))
    return tuple(sorted(alerts, key=lambda item: (item.path, item.line, item.column, item.check)))


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])
    )


def _allowance(alert: _Alert, resolved: dict[str, Any]) -> bool:
    allowances = resolved.get("allowances", [])
    return any(
        isinstance(item, dict)
        and isinstance(item.get("term"), str)
        and item["term"].casefold() == alert.match.casefold()
        and isinstance(item.get("paths"), list)
        and any(
            isinstance(pattern, str) and _matches(alert.path, pattern) for pattern in item["paths"]
        )
        for item in allowances
    )


def _resolve_acronyms(
    alerts: tuple[_Alert, ...], sources: dict[str, str], resolved: dict[str, Any]
) -> tuple[_Alert, ...]:
    candidates = {
        AcronymOccurrence(alert.path, alert.line, alert.column, alert.match): alert
        for alert in alerts
        if alert.check == "STECode.UnexpandedAcronyms"
    }
    if not candidates:
        return alerts
    accepted = resolved.get("accepted", [])
    acronyms = resolved.get("acronyms", [])
    terms = tuple(item for item in (*accepted, *acronyms) if isinstance(item, str))
    unresolved = set(
        unresolved_first_uses(candidates, sources, GLOBAL_ACRONYMS | established_acronyms(terms))
    )
    return tuple(
        alert
        for alert in alerts
        if alert.check != "STECode.UnexpandedAcronyms"
        or AcronymOccurrence(alert.path, alert.line, alert.column, alert.match) in unresolved
    )


def run_vale(target_value: Path, *, advisory: bool = False) -> int:
    """Run one generated Vale rule set with mapped tracked-source findings."""
    target = resolve_target(target_value)
    _digest, generated = build_corpus(target)
    selected = _source_paths(target, _PROSE_SUFFIXES)
    if not selected:
        return 0
    with tempfile.TemporaryDirectory(prefix="text-", dir=target / ".git/qat") as raw:
        staging = Path(raw)
        inputs: list[str] = []
        aliases: dict[str, _Alias] = {}
        sources: dict[str, str] = {}
        for relative in selected:
            name, alias, source = _stage_view(target, relative, staging)
            inputs.append(name)
            sources[relative] = _directive_view(relative, source)
            if alias is not None:
                aliases[str(Path(name).resolve())] = alias
        directives = tuple(
            f"{relative}:{line}: QTX001 inline Vale directives are forbidden"
            for relative, source in sources.items()
            for line, text in enumerate(source.splitlines(), start=1)
            if _DIRECTIVE.search(text)
        )
        if directives:
            print("\n".join(directives))
            return 1
        executable = executable_path(select_tools(["vale"])[0])
        configuration = generated / "vale" / ("ai-tells.ini" if advisory else ".vale.ini")
        completed = _run(
            (
                str(executable),
                "--no-global",
                f"--config={configuration}",
                "--output=JSON",
                *inputs,
            ),
            target,
        )
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode not in {0, 1}:
            raise TextToolError(f"Vale exited with unclassified status {completed.returncode}")
        alerts = _parse_alerts(completed.stdout, target, aliases)
        resolved = json.loads((generated / "resolved.json").read_text(encoding="utf-8"))
        alerts = _resolve_acronyms(alerts, sources, resolved)
        alerts = tuple(alert for alert in alerts if not _allowance(alert, resolved))
        for alert in alerts:
            print(
                f"{alert.path}:{alert.line}:{alert.column}: {alert.severity} "
                f"{alert.check}: {alert.message} [{alert.match}]"
            )
        if advisory:
            return int(bool(alerts))
        return int(any(alert.severity.casefold() == "error" for alert in alerts))


def run_cspell(target_value: Path) -> int:
    """Run CSpell once against selected tracked source text."""
    target = resolve_target(target_value)
    _digest, generated = build_corpus(target)
    selected = _source_paths(target, _SPELLING_SUFFIXES)
    if not selected:
        return 0
    with tempfile.TemporaryDirectory(prefix="spelling-", dir=target / ".git/qat") as raw:
        staging = Path(raw)
        inputs: list[str] = []
        aliases: dict[str, _Alias] = {}
        for relative in selected:
            name, alias, _source = _stage_view(target, relative, staging, extract_python=True)
            inputs.append(name)
            if alias is not None:
                aliases[str(Path(name).resolve())] = alias
        executable = executable_path(select_tools(["cspell"])[0])
        completed = _run(
            (
                str(executable),
                "--config",
                str(generated / "cspell.json"),
                "--no-progress",
                "--no-summary",
                *inputs,
            ),
            target,
        )
        if completed.stdout:
            print(_map_cspell_output(completed.stdout, target, aliases), end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode not in {0, 1}:
            raise TextToolError(f"CSpell exited with unclassified status {completed.returncode}")
        return completed.returncode


def _map_cspell_output(output: str, target: Path, aliases: dict[str, _Alias]) -> str:
    """Restore tracked paths and columns in CSpell's line-oriented output."""
    rendered: list[str] = []
    finding = re.compile(r"^(.*):(\d+):(\d+) - (.*)$")
    for line in output.splitlines():
        match = finding.fullmatch(line)
        if match is None:
            rendered.append(line)
            continue
        path, alias = _mapped_path(match.group(1), target, aliases)
        line_number = int(match.group(2))
        column = int(match.group(3))
        if alias is not None:
            if line_number > len(alias.column_offsets):
                raise TextToolError("CSpell finding exceeds the staged source map")
            column += alias.column_offsets[line_number - 1]
        rendered.append(f"{path}:{line_number}:{column} - {match.group(4)}")
    return "\n".join(rendered) + ("\n" if output.endswith("\n") else "")


def main(arguments: Sequence[str] | None = None) -> None:
    """Run one small text utility."""
    parser = argparse.ArgumentParser(prog="qat-text")
    parser.add_argument("operation", choices=("vale", "cspell"))
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--advisory", action="store_true")
    options = parser.parse_args(arguments)
    if options.advisory and options.operation != "vale":
        parser.error("--advisory is valid only for Vale")
    try:
        code = (
            run_vale(options.target, advisory=options.advisory)
            if options.operation == "vale"
            else run_cspell(options.target)
        )
    except (
        CorpusError,
        DeploymentError,
        OSError,
        RegistryError,
        SyntaxError,
        TextToolError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"qat-text: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main(sys.argv[1:])
