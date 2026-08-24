"""Deterministic, position-preserving prose extraction from LaTeX sources."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pylatexenc.latexwalker import (  # type: ignore[import-untyped]
    LatexCharsNode,
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexMathNode,
    LatexWalker,
    LatexWalkerParseError,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec  # type: ignore[import-untyped]

_IGNORED_ENVIRONMENTS = frozenset(
    {
        "align",
        "align*",
        "alignat",
        "alignat*",
        "code",
        "displaymath",
        "equation",
        "equation*",
        "filecontents",
        "filecontents*",
        "gather",
        "gather*",
        "latin",
        "lstlisting",
        "math",
        "minted",
        "multline",
        "multline*",
        "otherlanguage",
        "otherlanguage*",
        "pygmented",
        "split",
        "tikzpicture",
        "verbatim",
        "verbatim*",
    }
)

_IGNORED_MACROS = frozenset(
    {
        "ac",
        "acl",
        "acrlong",
        "acrshort",
        "acs",
        "addbibresource",
        "addcontentsline",
        "addtolength",
        "ang",
        "author",
        "autocite",
        "autoref",
        "bibliography",
        "bibliographystyle",
        "cite",
        "citep",
        "citet",
        "complexqty",
        "cref",
        "declaremathoperator",
        "declarerobustcommand",
        "date",
        "def",
        "documentclass",
        "eqref",
        "footcite",
        "foreignlanguage",
        "geometry",
        "gls",
        "glspl",
        "hypersetup",
        "include",
        "includegraphics",
        "includeonly",
        "input",
        "label",
        "let",
        "lstinline",
        "mintinline",
        "nameref",
        "newcolumntype",
        "newcommand",
        "newenvironment",
        "nocite",
        "nolinkurl",
        "num",
        "pageref",
        "parencite",
        "path",
        "printbibliography",
        "providecommand",
        "qty",
        "ref",
        "renewcommand",
        "renewenvironment",
        "setcounter",
        "setlength",
        "setotherlanguage",
        "si",
        "smartcite",
        "textcite",
        "texttt",
        "tikzset",
        "unit",
        "url",
        "usepackage",
        "usetikzlibrary",
        "verb",
        "vref",
    }
)

_SELECTED_ARGUMENTS = {
    "caption": (1,),
    "captionof": (2,),
    "chapter": (2,),
    "href": (1,),
    "multicolumn": (2,),
    "paragraph": (2,),
    "resizebox": (2,),
    "section": (2,),
    "subparagraph": (2,),
    "subsection": (2,),
    "subsubsection": (2,),
    "textcolor": (1,),
    "texorpdfstring": (0,),
}

_HEADING_MACROS = frozenset(
    {
        "caption",
        "captionof",
        "chapter",
        "paragraph",
        "pretitle",
        "section",
        "subparagraph",
        "subsection",
        "subsubsection",
        "subtitle",
        "title",
    }
)

_CUSTOM_MACRO_SPECS = {
    "Cref": "{",
    "Gls": "*[{",
    "Glspl": "*[{",
    "SI": "[{{",
    "Vref": "{",
    "addcontentsline": "{{{",
    "autocite": "*[[{",
    "caption": "[{",
    "captionof": "{[{",
    "complexqty": "[{{",
    "foreignlanguage": "{{",
    "footcite": "*[[{",
    "geometry": "{",
    "gls": "*[{",
    "glspl": "*[{",
    "href": "{{",
    "hypersetup": "{",
    "lstinline": "[{",
    "mintinline": "[{{",
    "multicolumn": "{{{",
    "nameref": "{",
    "newcolumntype": "{{",
    "nolinkurl": "{",
    "num": "[{",
    "pageref": "{",
    "parencite": "*[[{",
    "path": "{",
    "qty": "[{{",
    "resizebox": "{{{",
    "setotherlanguage": "{",
    "si": "[{",
    "smartcite": "*[[{",
    "subtitle": "{",
    "textcite": "*[[{",
    "textcolor": "{{",
    "texorpdfstring": "{{",
    "tikzset": "{",
    "pretitle": "{",
    "unit": "[{",
    "usetikzlibrary": "{",
    "vref": "{",
}

_INLINE_LITERAL = re.compile(r"\\(?:verb|lstinline)\*?(?:\[[^\]\r\n]*\])?")


@dataclass(frozen=True, slots=True)
class LatexProseView:
    """Extracted Markdown and offsets that restore original source columns."""

    text: str
    column_offsets: tuple[int, ...]


def latex_prose_view(source: str) -> str:
    """Return the Markdown-compatible prose extracted from a LaTeX source."""
    return latex_prose_view_with_map(source).text


def latex_prose_view_with_map(source: str) -> LatexProseView:
    """Extract Markdown and the line offsets required to restore source columns."""
    blocked = _inline_literal_positions(source)
    output = [character if character in "\r\n" else " " for character in source]
    try:
        nodes, _, _ = LatexWalker(source, latex_context=_latex_context()).get_latex_nodes()
    except LatexWalkerParseError as exc:
        raise ValueError(f"cannot parse LaTeX input: {exc}") from exc
    _render_nodes(nodes, source, output, blocked)
    rendered = "".join(output)
    if len(rendered) != len(source) or rendered.count("\n") != source.count("\n"):
        raise RuntimeError("LaTeX prose extraction did not preserve source positions")
    return _remove_markdown_indentation(rendered)


def _latex_context() -> Any:
    context = get_default_latex_context_db()
    context.add_context_category(
        "qa-toolkit",
        macros=[MacroSpec(name, argspec) for name, argspec in _CUSTOM_MACRO_SPECS.items()],
        prepend=True,
    )
    return context


def _render_nodes(
    nodes: Sequence[Any],
    source: str,
    output: list[str],
    blocked: bytearray,
) -> None:
    for node in nodes:
        if isinstance(node, LatexCharsNode):
            _copy_chars(node.pos, node.len, source, output, blocked)
        elif isinstance(node, LatexGroupNode):
            _render_nodes(node.nodelist, source, output, blocked)
        elif isinstance(node, LatexMacroNode):
            _render_macro(node, source, output, blocked)
        elif isinstance(node, LatexEnvironmentNode):
            if node.environmentname.casefold() not in _IGNORED_ENVIRONMENTS:
                _render_nodes(node.nodelist, source, output, blocked)
        elif isinstance(node, (LatexCommentNode, LatexMathNode)):
            continue


def _render_macro(
    node: Any,
    source: str,
    output: list[str],
    blocked: bytearray,
) -> None:
    name = node.macroname.casefold()
    if name in _IGNORED_MACROS:
        return
    if name in _HEADING_MACROS:
        output[node.pos] = "#"
    if name == "item":
        _fill_markup(node.pos, node.len, output, "- ")
    raw_arguments = tuple(getattr(getattr(node, "nodeargd", None), "argnlist", ()))
    selected = _SELECTED_ARGUMENTS.get(name)
    if selected is not None:
        arguments = tuple(
            raw_arguments[index]
            for index in selected
            if index < len(raw_arguments) and raw_arguments[index] is not None
        )
    else:
        arguments = tuple(argument for argument in raw_arguments if argument is not None)
    for argument in arguments:
        nodelist = getattr(argument, "nodelist", None)
        if nodelist:
            _render_nodes(nodelist, source, output, blocked)


def _copy_chars(
    start: int,
    length: int,
    source: str,
    output: list[str],
    blocked: bytearray,
) -> None:
    for index in range(start, start + length):
        character = source[index]
        if not blocked[index] and character not in "~&":
            output[index] = character


def _fill_markup(start: int, length: int, output: list[str], pattern: str) -> None:
    for offset, index in enumerate(range(start, start + length)):
        if output[index] not in "\r\n":
            output[index] = pattern[offset % len(pattern)]


def _remove_markdown_indentation(rendered: str) -> LatexProseView:
    lines: list[str] = []
    offsets: list[int] = []
    for line in rendered.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        leading = len(content) - len(content.lstrip())
        offset = leading if leading >= 4 else 0
        lines.append(line[offset:])
        offsets.append(offset)
    return LatexProseView("".join(lines), tuple(offsets))


def _inline_literal_positions(source: str) -> bytearray:
    blocked = bytearray(len(source))
    for match in _INLINE_LITERAL.finditer(source):
        delimiter_position = match.end()
        if delimiter_position >= len(source):
            continue
        delimiter = source[delimiter_position]
        if delimiter.isspace() or delimiter == "{":
            continue
        end = source.find(delimiter, delimiter_position + 1)
        line_end = source.find("\n", delimiter_position + 1)
        if end < 0 or (line_end >= 0 and end > line_end):
            raise ValueError(f"unterminated LaTeX inline literal at offset {match.start()}")
        blocked[match.start() : end + 1] = b"\x01" * (end + 1 - match.start())
    return blocked
