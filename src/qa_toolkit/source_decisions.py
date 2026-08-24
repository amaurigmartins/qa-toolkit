"""Classify source inputs that require deterministic lint treatment."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from qa_toolkit.corpus import Corpus


@dataclass(frozen=True, slots=True)
class SourceDecision:
    """One source classification and the exact reason that selected it."""

    classification: str
    reason: str


_LICENSE_MARKERS: dict[str, tuple[str, ...]] = {
    "Apache-2.0": (
        "apache license\nversion 2.0, january 2004",
        "http://www.apache.org/licenses/",
        "limitations under the license",
    ),
    "BSD-2-Clause": (
        "redistribution and use in source and binary forms",
        'this software is provided by the copyright holders and contributors "as is"',
        "redistributions in binary form must reproduce",
    ),
    "BSD-3-Clause": (
        "redistribution and use in source and binary forms",
        "neither the name of the copyright holder nor the names of its contributors",
        'this software is provided by the copyright holders and contributors "as is"',
    ),
    "GPL-3.0": (
        "gnu general public license\nversion 3, 29 june 2007",
        "free software foundation, inc.",
        "everyone is permitted to copy and distribute verbatim copies",
    ),
    "MIT": (
        "mit license",
        "permission is hereby granted, free of charge, to any person obtaining a copy",
        'the software is provided "as is", without warranty of any kind',
    ),
}


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])
    )


def recognized_license(text: str, families: tuple[str, ...]) -> str | None:
    """Return a family only when all identifying standard-text markers are present."""
    normalized = re.sub(r"[ \t]+", " ", text.casefold().replace("\r\n", "\n"))
    for family in families:
        markers = _LICENSE_MARKERS.get(family)
        if markers is not None and all(marker in normalized for marker in markers):
            return family
    return None


def classify_source(path: str, text: str, corpus: Corpus) -> SourceDecision:
    """Classify one tracked path without inferring from its extension alone."""
    normalized_path = PurePosixPath(path).as_posix().lstrip("./")
    for pattern in corpus.sources["generated_patterns"]:
        if _matches(normalized_path, pattern):
            return SourceDecision("generated", f"matches generated pattern {pattern}")
    name = PurePosixPath(normalized_path).name
    accepted_names = {item.casefold() for item in corpus.sources["license_names"]}
    if name.casefold().split(".", maxsplit=1)[0] in accepted_names:
        family = recognized_license(text, corpus.sources["license_families"])
        if family is not None:
            return SourceDecision("standard-license", f"verified {family} text")
    return SourceDecision("source", "no special source decision matched")


def is_gitlab_cache_key(key: str, corpus: Corpus) -> bool:
    """Identify only documented GitLab cache-key fields from the owned corpus."""
    return key in corpus.sources["gitlab_cache_keys"]
