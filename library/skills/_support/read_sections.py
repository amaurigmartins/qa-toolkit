#!/usr/bin/env python3
"""Print named, heading-bounded excerpts from owned Markdown sources."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

_CHUNK_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class ExcerptError(RuntimeError):
    """Report an invalid excerpt index or source boundary."""


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExcerptError(f"{context}: expected a non-empty string")
    return value


def _library_root(index: Path) -> Path:
    resolved = index.resolve()
    for parent in resolved.parents:
        if parent.name == "library" and (parent / "instructions").is_dir():
            return parent
    raise ExcerptError(f"index is not inside the owned library: {index}")


def load_chunks(index_value: Path) -> dict[str, tuple[Path, str, str | None]]:
    """Load and validate every named excerpt from one closed index."""
    index = index_value.resolve()
    try:
        document = tomllib.loads(index.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ExcerptError(f"cannot read excerpt index {index}: {error}") from error
    if set(document) != {"schema_version", "chunk"} or document["schema_version"] != 1:
        raise ExcerptError("excerpt index must contain schema_version 1 and chunk")
    raw_chunks = document["chunk"]
    if not isinstance(raw_chunks, dict) or not raw_chunks:
        raise ExcerptError("excerpt index chunk table must not be empty")

    library = _library_root(index)
    result: dict[str, tuple[Path, str, str | None]] = {}
    for name, raw in raw_chunks.items():
        if not isinstance(name, str) or _CHUNK_NAME.fullmatch(name) is None:
            raise ExcerptError(f"invalid excerpt name: {name}")
        if not isinstance(raw, dict) or not {"source", "start"} <= set(raw):
            raise ExcerptError(f"chunk.{name}: expected source and start")
        if not set(raw) <= {"source", "start", "end"}:
            raise ExcerptError(f"chunk.{name}: unknown field")
        source = (index.parent / _text(raw["source"], f"chunk.{name}.source")).resolve()
        if library not in source.parents or not source.is_file() or source.is_symlink():
            raise ExcerptError(f"chunk.{name}: source must be a regular owned library file")
        start = _text(raw["start"], f"chunk.{name}.start")
        end = None if "end" not in raw else _text(raw["end"], f"chunk.{name}.end")
        result[name] = (source, start, end)
    return result


def excerpt(source: Path, start: str, end: str | None) -> str:
    """Return one exact source excerpt bounded by unique Markdown headings."""
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == start]
    if len(starts) != 1:
        raise ExcerptError(f"{source}: expected one start heading {start!r}")
    first = starts[0]
    if end is None:
        last = len(lines)
    else:
        ends = [
            index
            for index, line in enumerate(lines)
            if index > first and line.rstrip("\r\n") == end
        ]
        if len(ends) != 1:
            raise ExcerptError(f"{source}: expected one later end heading {end!r}")
        last = ends[0]
    return "".join(lines[first:last]).rstrip() + "\n"


def main() -> None:
    """Print only the requested exact excerpts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("chunks", nargs="*")
    options = parser.parse_args()
    try:
        chunks = load_chunks(options.index)
        if options.list:
            if options.chunks:
                raise ExcerptError("--list does not accept excerpt names")
            print("\n".join(sorted(chunks)))
            return
        if not options.chunks:
            raise ExcerptError("name at least one excerpt")
        unknown = [name for name in options.chunks if name not in chunks]
        if unknown:
            raise ExcerptError(f"unknown excerpt: {', '.join(unknown)}")
        outputs = [excerpt(*chunks[name]) for name in options.chunks]
        sys.stdout.write("\n".join(item.rstrip() for item in outputs) + "\n")
    except ExcerptError as error:
        print(f"read-sections: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
