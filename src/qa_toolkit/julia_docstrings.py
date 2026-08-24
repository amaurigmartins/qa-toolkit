"""Position-preserving Markdown projection of attached Julia docstrings."""

from __future__ import annotations

from dataclasses import dataclass

import tree_sitter_julia
from tree_sitter import Language, Node, Parser, Query, QueryCursor

_DOCSTRING_QUERY = r"""
((_ (string_literal) @docstring .
    [(abstract_definition)
     (assignment)
     (call_expression)
     (const_statement)
     (function_definition)
     (identifier)
     (macro_definition)
     (macrocall_expression)
     (module_definition)
     (primitive_definition)
     (struct_definition)
     (typed_expression)]))

((macrocall_expression
   (macro_identifier) @macro
   (macro_argument_list
     [(string_literal) (prefixed_string_literal)] @docstring))
 (#eq? @macro "@doc"))
"""


@dataclass(frozen=True, slots=True)
class JuliaDocstringView:
    """Markdown text and per-line offsets that restore Julia source columns."""

    text: str
    column_offsets: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _LineSegment:
    text: str
    column_offset: int


def julia_docstring_view(source: str) -> JuliaDocstringView:
    """Extract attached Julia docstrings as source-mapped Markdown."""
    encoded = source.encode("utf-8")
    language = Language(tree_sitter_julia.language())
    tree = Parser(language).parse(encoded)
    if tree.root_node.has_error:
        raise ValueError("Julia syntax tree contains an error")
    captures = QueryCursor(Query(language, _DOCSTRING_QUERY)).captures(tree.root_node)
    nodes = tuple(
        sorted(
            set(captures.get("docstring", ())),
            key=lambda node: (node.start_byte, node.end_byte),
        )
    )
    lines = source.splitlines(keepends=True)
    source_lines = tuple(_without_line_ending(line) for line in lines)
    segments: dict[int, _LineSegment] = {}
    for node in nodes:
        _project_docstring(node, encoded, source_lines, segments)
    projected: list[str] = []
    offsets: list[int] = []
    for index, line in enumerate(lines):
        segment = segments.get(index, _LineSegment("", 0))
        projected.append(segment.text + _line_ending(line))
        offsets.append(segment.column_offset)
    return JuliaDocstringView("".join(projected), tuple(offsets))


def _project_docstring(
    node: Node,
    source: bytes,
    lines: tuple[str, ...],
    projected: dict[int, _LineSegment],
) -> None:
    opening, closing = _delimiters(node, source)
    start_row, start_byte_column = node.start_point
    end_row, end_byte_column = node.end_point
    content_start = start_byte_column + len(opening)
    content_end = end_byte_column - len(closing)
    base_indent = _character_column(lines[start_row], start_byte_column)
    interpolations = tuple(_descendants(node, "string_interpolation"))
    for row in range(start_row, end_row + 1):
        line = lines[row]
        line_bytes = line.encode("utf-8")
        left_byte = content_start if row == start_row else 0
        right_byte = content_end if row == end_row else len(line_bytes)
        if right_byte < left_byte:
            raise ValueError("Julia docstring has invalid delimiter positions")
        left = _character_column(line, left_byte)
        right = _character_column(line, right_byte)
        text = list(line[left:right])
        _mask_interpolations(text, row, left, line, interpolations)
        strip = 0 if row == start_row else min(base_indent, _leading_whitespace("".join(text)))
        segment = _LineSegment("".join(text[strip:]), left + strip)
        _store_segment(projected, row, segment)


def _delimiters(node: Node, source: bytes) -> tuple[bytes, bytes]:
    text = source[node.start_byte : node.end_byte]
    candidates = (
        (b'raw"""', b'"""'),
        (b'"""', b'"""'),
        (b'raw"', b'"'),
        (b'"', b'"'),
    )
    for opening, closing in candidates:
        if text.startswith(opening) and text.endswith(closing):
            return opening, closing
    raise ValueError(f"unsupported Julia docstring literal: {node.type}")


def _descendants(node: Node, node_type: str) -> tuple[Node, ...]:
    matches: list[Node] = []
    pending = list(node.children)
    while pending:
        child = pending.pop()
        if child.type == node_type:
            matches.append(child)
        else:
            pending.extend(child.children)
    return tuple(matches)


def _mask_interpolations(
    text: list[str],
    row: int,
    segment_left: int,
    line: str,
    interpolations: tuple[Node, ...],
) -> None:
    for interpolation in interpolations:
        start_row, start_byte_column = interpolation.start_point
        end_row, end_byte_column = interpolation.end_point
        if row < start_row or row > end_row:
            continue
        left_byte = start_byte_column if row == start_row else 0
        right_byte = end_byte_column if row == end_row else len(line.encode("utf-8"))
        left = max(0, _character_column(line, left_byte) - segment_left)
        right = min(len(text), _character_column(line, right_byte) - segment_left)
        for index in range(left, right):
            if text[index] not in {"\r", "\n"}:
                text[index] = " "


def _store_segment(projected: dict[int, _LineSegment], row: int, segment: _LineSegment) -> None:
    previous = projected.get(row)
    if previous is None or not previous.text.strip():
        projected[row] = segment
        return
    if not segment.text.strip():
        return
    raise ValueError("multiple Julia docstrings occupy one source line")


def _character_column(line: str, byte_column: int) -> int:
    encoded = line.encode("utf-8")
    if byte_column < 0 or byte_column > len(encoded):
        raise ValueError("Julia syntax tree reported an invalid source column")
    try:
        return len(encoded[:byte_column].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("Julia syntax tree split a UTF-8 character") from exc


def _leading_whitespace(value: str) -> int:
    return len(value) - len(value.lstrip(" \t"))


def _without_line_ending(line: str) -> str:
    return line.removesuffix("\n").removesuffix("\r")


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""
