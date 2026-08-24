"""Document-level resolution of acronym first-use candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_ACRONYM = re.compile(r"[A-Z][A-Z0-9]{2,7}")
_WORD = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_IGNORED_WORDS = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "with"}
)
_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
GLOBAL_ACRONYMS = frozenset(
    term.casefold()
    for term in (
        "API",
        "ASCII",
        "CAUTION",
        "CLI",
        "CPU",
        "CSV",
        "DANGER",
        "DSL",
        "EOF",
        "GPU",
        "HTTP",
        "HTTPS",
        "IDE",
        "IMPORTANT",
        "IO",
        "JSON",
        "KPI",
        "MIME",
        "NOTE",
        "POSIX",
        "RAM",
        "README",
        "REST",
        "RFC",
        "SQL",
        "SSH",
        "STE",
        "SVG",
        "TCP",
        "TOML",
        "TTY",
        "UDP",
        "UI",
        "URI",
        "URL",
        "UTC",
        "UTF",
        "UUID",
        "WARNING",
        "XDG",
        "XML",
        "YAML",
    )
)


@dataclass(frozen=True, slots=True, order=True)
class AcronymOccurrence:
    """One reader-prose acronym candidate at an original source location."""

    path: str
    line: int
    column: int
    term: str


def established_acronyms(terms: Iterable[str]) -> frozenset[str]:
    """Return case-folded acronym spellings from a terminology collection."""
    return frozenset(term.casefold() for term in terms if _ACRONYM.fullmatch(term))


def unresolved_first_uses(
    occurrences: Iterable[AcronymOccurrence],
    sources: Mapping[str, str],
    established: frozenset[str] = frozenset(),
    required: frozenset[AcronymOccurrence] = frozenset(),
) -> tuple[AcronymOccurrence, ...]:
    """Keep only the first unresolved occurrence of each term in each document."""
    retained: list[AcronymOccurrence] = []
    seen: set[tuple[str, str]] = set()
    for occurrence in sorted(occurrences):
        line = _source_line(occurrence, sources)
        key = occurrence.path, occurrence.term.casefold()
        if key in seen:
            continue
        seen.add(key)
        if (key[1] in established and occurrence not in required) or _defines_term(
            line, occurrence
        ):
            continue
        retained.append(occurrence)
    return tuple(retained)


def _source_line(occurrence: AcronymOccurrence, sources: Mapping[str, str]) -> str:
    source = sources.get(occurrence.path)
    if source is None:
        raise ValueError(f"acronym source is unavailable: {occurrence.path}")
    lines = source.splitlines()
    if occurrence.line < 1 or occurrence.line > len(lines) or occurrence.column < 1:
        raise ValueError(f"acronym occurrence has an invalid source location: {occurrence.path}")
    line = lines[occurrence.line - 1]
    start = occurrence.column - 1
    observed = line[start : start + len(occurrence.term)]
    if observed != occurrence.term:
        raise ValueError(
            f"acronym occurrence does not match source text: {occurrence.path}:"
            f"{occurrence.line}:{occurrence.column}"
        )
    return line


def _defines_term(line: str, occurrence: AcronymOccurrence) -> bool:
    start = occurrence.column - 1
    end = start + len(occurrence.term)
    return _definition_before(line, start, end, occurrence.term) or _definition_after(
        line, end, occurrence.term
    )


def _definition_before(line: str, start: int, end: int, term: str) -> bool:
    if start == 0 or line[start - 1] != "(":
        return False
    closing = end
    while closing < len(line) and line[closing].isspace():
        closing += 1
    if closing >= len(line) or line[closing] != ")":
        return False
    words = _WORD.findall(line[: start - 1])
    return any(
        _initialism(words[-count:], term) == term
        for count in range(1, min(len(words), len(term) + 3) + 1)
    )


def _definition_after(line: str, end: int, term: str) -> bool:
    opening = end
    while opening < len(line) and line[opening].isspace():
        opening += 1
    if opening >= len(line) or line[opening] != "(":
        return False
    closing = line.find(")", opening + 1)
    if closing < 0:
        return False
    words = _WORD.findall(line[opening + 1 : closing])
    return bool(words) and _initialism(words, term) == term


def _initialism(words: list[str], term: str) -> str:
    initials: list[str] = []
    for word in words:
        for part in word.split("-"):
            folded = part.casefold()
            if folded == "to" and "2" in term:
                initials.append("2")
            elif folded in _NUMBER_WORDS and _NUMBER_WORDS[folded] in term:
                initials.append(_NUMBER_WORDS[folded])
            elif folded not in _IGNORED_WORDS:
                initials.append(part[0].upper())
    return "".join(initials)
