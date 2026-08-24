"""Validate tracked Julia syntax, docstrings, and terse public identifiers."""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

import tree_sitter_julia
from tree_sitter import Language, Node, Parser

from qa_toolkit.corpus import load_corpus
from qa_toolkit.deployment import DeploymentError, resolve_target, tracked_regular_files
from qa_toolkit.julia_docstrings import julia_docstring_view


def _walk(root: Node) -> tuple[Node, ...]:
    pending = [root]
    result: list[Node] = []
    while pending:
        node = pending.pop()
        result.append(node)
        pending.extend(reversed(node.children))
    return tuple(result)


def _scientific(identifier: str) -> bool:
    value = identifier.rstrip("!")
    if value == "im" or (len(value) == 1 and value.isalpha()):
        return True
    return any(
        ord(character) > 127
        and (
            character.isalpha()
            or "GREEK" in unicodedata.name(character, "")
            or "MATHEMATICAL" in unicodedata.name(character, "")
        )
        for character in value
    )


def findings(path: str, source: str) -> tuple[str, ...]:
    """Return terse exported Julia identifiers not explained by scientific notation."""
    julia_docstring_view(source)
    encoded = source.encode("utf-8")
    tree = Parser(Language(tree_sitter_julia.language())).parse(encoded)
    if tree.root_node.has_error:
        raise ValueError(f"Julia syntax tree contains an error: {path}")
    found: list[str] = []
    accepted = {item.casefold() for item in load_corpus().identifier_accepted}
    for statement in _walk(tree.root_node):
        if statement.type not in {"export_statement", "public_statement"}:
            continue
        for node in _walk(statement):
            if node.type != "identifier":
                continue
            identifier = encoded[node.start_byte : node.end_byte].decode("utf-8")
            if (
                len(identifier.rstrip("!")) <= 2
                and identifier.rstrip("!").casefold() not in accepted
                and not _scientific(identifier)
            ):
                found.append(
                    f"{path}:{node.start_point.row + 1}:{node.start_point.column + 1}: "
                    f"terse public Julia identifier {identifier!r} requires a specific name"
                )
    return tuple(found)


def main(arguments: Sequence[str] | None = None) -> None:
    """Check tracked Julia inputs without reading generated or untracked files."""
    parser = argparse.ArgumentParser(prog="qat-julia-source")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    options = parser.parse_args(arguments)
    try:
        target = resolve_target(options.target)
        reported = tuple(
            item
            for path in tracked_regular_files(target)
            if PurePosixPath(path).suffix.casefold() == ".jl"
            for item in findings(path, (target / path).read_text(encoding="utf-8"))
        )
        for item in reported:
            print(item)
        code = 1 if reported else 0
    except (DeploymentError, OSError, UnicodeError, ValueError) as error:
        print(f"qat-julia-source: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
