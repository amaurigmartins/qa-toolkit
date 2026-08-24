"""Position-preserving projection of Documenter Markdown reader prose."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})([^\r\n]*)")
_DOCUMENTATION_FENCE = re.compile(r"(?:math|@[a-z][a-z0-9_-]*)\b", re.IGNORECASE)
_DOCUMENTATION_DESTINATION = re.compile(
    r"@(ref|id|extref|cite(?:t|p|alt|alp|num)?\*?)(?![a-z0-9_*])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DocumenterMarkdownView:
    """Markdown text with non-reader Documenter syntax replaced by spaces."""

    text: str


def documenter_markdown_view(source: str) -> DocumenterMarkdownView:
    """Mask Documenter math, directives, citation keys, and link destinations."""
    rendered = list(source)
    protected = [False] * len(source)
    _classify_fenced_blocks(source, rendered, protected)
    _classify_inline_code(source, rendered, protected)
    _mask_dollar_math(source, rendered, protected)
    _mask_documenter_links(source, rendered, protected)
    return DocumenterMarkdownView("".join(rendered))


def _classify_fenced_blocks(source: str, rendered: list[str], protected: list[bool]) -> None:
    lines = _line_ranges(source)
    index = 0
    while index < len(lines):
        start, content_end, _ = lines[index]
        opening = _FENCE_OPEN.fullmatch(source[start:content_end])
        if opening is None:
            index += 1
            continue
        fence = opening.group(1)
        documenter = _DOCUMENTATION_FENCE.match(opening.group(2).strip()) is not None
        final_index = len(lines) - 1
        for candidate in range(index + 1, len(lines)):
            candidate_start, candidate_content_end, _ = lines[candidate]
            text = source[candidate_start:candidate_content_end]
            stripped = text.lstrip(" ")
            indent = len(text) - len(stripped)
            if indent <= 3 and _closes_fence(stripped, fence):
                final_index = candidate
                break
        block_end = lines[final_index][2]
        _protect(protected, start, block_end)
        if documenter:
            _blank(rendered, start, block_end)
        index = final_index + 1


def _line_ranges(source: str) -> tuple[tuple[int, int, int], ...]:
    ranges: list[tuple[int, int, int]] = []
    cursor = 0
    for line in source.splitlines(keepends=True):
        content_end = cursor + len(line.rstrip("\r\n"))
        ranges.append((cursor, content_end, cursor + len(line)))
        cursor += len(line)
    if cursor < len(source) or not source:
        ranges.append((cursor, len(source), len(source)))
    return tuple(ranges)


def _closes_fence(text: str, opening: str) -> bool:
    run_length = 0
    while run_length < len(text) and text[run_length] == opening[0]:
        run_length += 1
    return run_length >= len(opening) and not text[run_length:].strip()


def _classify_inline_code(source: str, rendered: list[str], protected: list[bool]) -> None:
    index = 0
    while index < len(source):
        if source[index] != "`" or protected[index]:
            index += 1
            continue
        run_end = index + 1
        while run_end < len(source) and source[run_end] == "`" and not protected[run_end]:
            run_end += 1
        delimiter = source[index:run_end]
        closing = _inline_closing(source, run_end, delimiter, protected)
        if closing is None:
            index = run_end
            continue
        end = closing + len(delimiter)
        _protect(protected, index, end)
        if len(delimiter) == 2:
            _blank(rendered, index, end)
        index = end


def _inline_closing(source: str, start: int, delimiter: str, protected: list[bool]) -> int | None:
    cursor = start
    while True:
        candidate = source.find(delimiter, cursor)
        if candidate < 0:
            return None
        end = candidate + len(delimiter)
        if (
            "\n" not in source[start:candidate]
            and not any(protected[candidate:end])
            and (candidate == 0 or source[candidate - 1] != "`")
            and (end == len(source) or source[end] != "`")
        ):
            return candidate
        if "\n" in source[start:candidate]:
            return None
        cursor = end


def _mask_dollar_math(source: str, rendered: list[str], protected: list[bool]) -> None:
    index = 0
    while index < len(source):
        if source[index] != "$" or protected[index] or _is_escaped(source, index):
            index += 1
            continue
        end = _dollar_math_end(source, index, protected)
        if end is None:
            index += 2 if source.startswith("$$", index) else 1
            continue
        _blank(rendered, index, end)
        index = end


def _dollar_math_end(source: str, index: int, protected: list[bool]) -> int | None:
    if source.startswith("$$", index) and not any(protected[index : index + 2]):
        closing = _find_dollar_closing(source, index + 2, "$$", protected, multiline=True)
        return None if closing is None else closing + 2
    if index + 1 >= len(source) or source[index + 1].isspace():
        return None
    closing = _find_dollar_closing(source, index + 1, "$", protected, multiline=False)
    return None if closing is None else closing + 1


def _find_dollar_closing(
    source: str,
    start: int,
    delimiter: str,
    protected: list[bool],
    *,
    multiline: bool,
) -> int | None:
    cursor = start
    while True:
        candidate = source.find(delimiter, cursor)
        if candidate < 0 or (not multiline and "\n" in source[start:candidate]):
            return None
        end = candidate + len(delimiter)
        if _valid_dollar_closing(source, start, candidate, end, delimiter, protected):
            return candidate
        cursor = end


def _valid_dollar_closing(
    source: str,
    start: int,
    candidate: int,
    end: int,
    delimiter: str,
    protected: list[bool],
) -> bool:
    if any(protected[candidate:end]) or any(protected[start:candidate]):
        return False
    if _is_escaped(source, candidate):
        return False
    return delimiter == "$$" or (candidate > start and not source[candidate - 1].isspace())


def _mask_documenter_links(source: str, rendered: list[str], protected: list[bool]) -> None:
    index = 0
    while index < len(source):
        if source[index] != "[" or protected[index]:
            index += 1
            continue
        bounds = _documenter_link_bounds(source, index, protected)
        if bounds is None:
            index += 1
            continue
        label_end, destination_end = bounds
        target = source[label_end + 2 : destination_end].strip()
        command = _DOCUMENTATION_DESTINATION.match(target)
        if command is not None:
            _mask_documenter_destination(
                source,
                rendered,
                index,
                label_end,
                destination_end,
                target,
                command,
            )
        index = destination_end + 1


def _documenter_link_bounds(
    source: str,
    index: int,
    protected: list[bool],
) -> tuple[int, int] | None:
    label_end = _balanced_end(source, index, "[", "]", protected, allow_newline=False)
    if label_end is None or label_end + 1 >= len(source) or source[label_end + 1] != "(":
        return None
    destination_end = _balanced_end(
        source,
        label_end + 1,
        "(",
        ")",
        protected,
        allow_newline=False,
    )
    return None if destination_end is None else (label_end, destination_end)


def _mask_documenter_destination(
    source: str,
    rendered: list[str],
    index: int,
    label_end: int,
    destination_end: int,
    target: str,
    command: re.Match[str],
) -> None:
    _blank(rendered, label_end + 1, destination_end + 1)
    name = command.group(1).casefold()
    arguments = target[command.end() :].strip()
    if not name.startswith("cite") or arguments:
        return
    semicolon = source.find(";", index + 1, label_end)
    key_end = label_end if semicolon < 0 else semicolon + 1
    _blank(rendered, index + 1, key_end)


def _balanced_end(
    source: str,
    start: int,
    opening: str,
    closing: str,
    protected: list[bool],
    *,
    allow_newline: bool,
) -> int | None:
    depth = 0
    index = start
    while index < len(source):
        if not allow_newline and source[index] in {"\r", "\n"}:
            return None
        if protected[index] or _is_escaped(source, index):
            index += 1
            continue
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _is_escaped(source: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and source[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _protect(protected: list[bool], start: int, end: int) -> None:
    protected[start:end] = [True] * (end - start)


def _blank(rendered: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if rendered[index] not in {"\r", "\n"}:
            rendered[index] = " "
