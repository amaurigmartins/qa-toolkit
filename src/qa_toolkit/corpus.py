"""Resolve the owned terminology corpus and generate tool-native inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from qa_toolkit.config import load_consumer
from qa_toolkit.deployment import resolve_target, status
from qa_toolkit.models import ConfigurationError, closed_keys, relative_path, string_list
from qa_toolkit.paths import toolkit_root

LEVELS = frozenset({"off", "warning", "error"})
TERM_ID = re.compile(r"[a-z][a-z0-9-]{0,63}")
ROLE_KEYS = frozenset(
    {"action", "outcome", "concept", "plural_concept", "context", "condition", "qualifier"}
)
SOURCE_KEYS = frozenset(
    {"license_names", "license_families", "generated_patterns", "gitlab_cache_keys"}
)


class CorpusError(RuntimeError):
    """Report invalid shared or consumer vocabulary data."""


@dataclass(frozen=True)
class TermRule:
    """One owned term family and its rule severities."""

    identifier: str
    forms: tuple[str, ...]
    guidance: str
    suggestions: tuple[str, ...]
    prose: str
    identifier_severity: str
    commit: str


@dataclass(frozen=True)
class Corpus:
    """The parsed shared corpus used by every converter."""

    terms: tuple[TermRule, ...]
    locale: str
    accepted: tuple[str, ...]
    hedges: tuple[str, ...]
    fillers: tuple[str, ...]
    identifier_accepted: tuple[str, ...]
    roles: dict[str, tuple[str, ...]]
    acronyms: tuple[str, ...]
    sources: dict[str, tuple[str, ...]]
    documents: dict[str, tuple[str, ...]]
    ai_tells_directory: Path
    source: Path


@dataclass(frozen=True)
class ConsumerVocabulary:
    """Typed consumer additions that cannot weaken the shared corpus."""

    accepted: tuple[str, ...]
    rejected: tuple[str, ...]
    replacements: dict[str, str]
    acronyms: tuple[str, ...]
    roles: dict[str, tuple[str, ...]]
    allowances: tuple[dict[str, object], ...]
    locale: str | None
    source_additions: dict[str, tuple[str, ...]]


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CorpusError(f"cannot read vocabulary {path}: {error}") from error
    if not isinstance(value, dict):
        raise CorpusError(f"{path}: expected a table")
    return value


def _table(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorpusError(f"{context}: expected a table")
    return value


def _strings(value: object, context: str, *, required: bool = False) -> tuple[str, ...]:
    try:
        result = string_list(value, context)
    except ConfigurationError as error:
        raise CorpusError(str(error)) from error
    if required and not result:
        raise CorpusError(f"{context}: may not be empty")
    if len({item.casefold() for item in result}) != len(result):
        raise CorpusError(f"{context}: duplicate values")
    return result


def _term(raw: object, index: int, forms_seen: set[str], identifiers: set[str]) -> TermRule:
    context = f"terms[{index}]"
    table = _table(raw, context)
    closed_keys(
        table,
        {"id", "forms", "guidance", "suggestions", "prose", "identifier", "commit"},
        context,
    )
    identifier = table.get("id")
    if not isinstance(identifier, str) or TERM_ID.fullmatch(identifier) is None:
        raise CorpusError(f"{context}.id: expected lowercase kebab-case")
    if identifier in identifiers:
        raise CorpusError(f"duplicate term ID: {identifier}")
    identifiers.add(identifier)
    forms = _strings(table.get("forms"), f"{context}.forms", required=True)
    duplicates = {form.casefold() for form in forms} & forms_seen
    if duplicates:
        raise CorpusError(f"duplicate term forms: {', '.join(sorted(duplicates))}")
    forms_seen.update(form.casefold() for form in forms)
    guidance = table.get("guidance")
    if not isinstance(guidance, str) or not guidance:
        raise CorpusError(f"{context}.guidance: expected a non-empty string")
    levels = tuple(table.get(name, "off") for name in ("prose", "identifier", "commit"))
    if any(not isinstance(level, str) or level not in LEVELS for level in levels):
        raise CorpusError(f"{context}: invalid severity")
    return TermRule(
        identifier,
        forms,
        guidance,
        _strings(table.get("suggestions", []), f"{context}.suggestions"),
        str(levels[0]),
        str(levels[1]),
        str(levels[2]),
    )


def _mapping_of_strings(value: object, context: str) -> dict[str, tuple[str, ...]]:
    table = _table(value, context)
    return {key: _strings(item, f"{context}.{key}") for key, item in table.items()}


def _closed_mapping_of_strings(
    value: object, context: str, allowed: frozenset[str]
) -> dict[str, tuple[str, ...]]:
    table = _table(value, context)
    closed_keys(table, set(allowed), context)
    return {key: _strings(item, f"{context}.{key}") for key, item in table.items()}


def load_corpus(root: Path | None = None) -> Corpus:
    """Load the one shared corpus through a closed schema."""
    repository = (root or toolkit_root()).resolve()
    path = repository / "corpus" / "vocabulary.toml"
    value = _load_toml(path)
    closed_keys(
        value,
        {
            "schema_version",
            "terms",
            "settings",
            "prose",
            "identifiers",
            "roles",
            "acronyms",
            "sources",
            "documents",
            "ai_tells",
        },
        str(path),
    )
    if value.get("schema_version") != 1:
        raise CorpusError(f"{path}: schema_version must be 1")
    terms_raw = value.get("terms")
    if not isinstance(terms_raw, list) or not terms_raw:
        raise CorpusError(f"{path}.terms: expected a non-empty array")
    forms_seen: set[str] = set()
    identifiers_seen: set[str] = set()
    terms = tuple(
        _term(raw, index, forms_seen, identifiers_seen) for index, raw in enumerate(terms_raw)
    )
    settings = _table(value.get("settings"), f"{path}.settings")
    closed_keys(settings, {"locale"}, f"{path}.settings")
    locale = settings.get("locale")
    if not isinstance(locale, str) or not locale:
        raise CorpusError(f"{path}.settings.locale: expected a non-empty string")
    prose = _table(value.get("prose"), f"{path}.prose")
    closed_keys(prose, {"accepted", "hedges", "fillers"}, f"{path}.prose")
    identifiers = _table(value.get("identifiers"), f"{path}.identifiers")
    closed_keys(identifiers, {"accepted"}, f"{path}.identifiers")
    acronyms = _table(value.get("acronyms"), f"{path}.acronyms")
    closed_keys(acronyms, {"accepted"}, f"{path}.acronyms")
    ai_tells = _table(value.get("ai_tells"), f"{path}.ai_tells")
    closed_keys(ai_tells, {"directory", "severity"}, f"{path}.ai_tells")
    if ai_tells.get("severity") != "advisory":
        raise CorpusError(f"{path}.ai_tells.severity: must be advisory")
    directory_value = ai_tells.get("directory")
    if not isinstance(directory_value, str):
        raise CorpusError(f"{path}.ai_tells.directory: expected a relative path")
    directory = relative_path(directory_value, f"{path}.ai_tells.directory")
    if not (repository / directory).is_dir():
        raise CorpusError(f"{path}.ai_tells.directory: directory does not exist")
    return Corpus(
        terms=terms,
        locale=locale,
        accepted=_strings(prose.get("accepted"), f"{path}.prose.accepted"),
        hedges=_strings(prose.get("hedges"), f"{path}.prose.hedges"),
        fillers=_strings(prose.get("fillers"), f"{path}.prose.fillers"),
        identifier_accepted=_strings(identifiers.get("accepted"), f"{path}.identifiers.accepted"),
        roles=_closed_mapping_of_strings(value.get("roles"), f"{path}.roles", ROLE_KEYS),
        acronyms=_strings(acronyms.get("accepted"), f"{path}.acronyms.accepted"),
        sources=_closed_mapping_of_strings(value.get("sources"), f"{path}.sources", SOURCE_KEYS),
        documents=_mapping_of_strings(value.get("documents"), f"{path}.documents"),
        ai_tells_directory=directory,
        source=path,
    )


def _empty_consumer_vocabulary() -> ConsumerVocabulary:
    return ConsumerVocabulary((), (), {}, (), {}, (), None, {})


def load_consumer_vocabulary(target: Path) -> ConsumerVocabulary:
    """Load the optional repository vocabulary through a closed schema."""
    consumer = load_consumer(target)
    if consumer.vocabulary_file is None:
        return _empty_consumer_vocabulary()
    path = target / consumer.vocabulary_file
    value = _load_toml(path)
    closed_keys(
        value,
        {"schema_version", "terminology", "acronyms", "roles", "allowances", "settings", "sources"},
        str(path),
    )
    if value.get("schema_version") != 1:
        raise CorpusError(f"{path}: schema_version must be 1")
    terminology = _table(value.get("terminology", {}), f"{path}.terminology")
    closed_keys(terminology, {"accepted", "rejected", "replacements"}, f"{path}.terminology")
    replacements_raw = _table(
        terminology.get("replacements", {}), f"{path}.terminology.replacements"
    )
    if not all(
        isinstance(key, str) and isinstance(item, str) for key, item in replacements_raw.items()
    ):
        raise CorpusError(f"{path}.terminology.replacements: expected string values")
    acronym_table = _table(value.get("acronyms", {}), f"{path}.acronyms")
    closed_keys(acronym_table, {"accepted"}, f"{path}.acronyms")
    settings = _table(value.get("settings", {}), f"{path}.settings")
    closed_keys(settings, {"locale"}, f"{path}.settings")
    locale = settings.get("locale")
    if locale is not None and (not isinstance(locale, str) or not locale):
        raise CorpusError(f"{path}.settings.locale: expected a non-empty string")
    allowances_raw = value.get("allowances", [])
    if not isinstance(allowances_raw, list):
        raise CorpusError(f"{path}.allowances: expected an array of tables")
    allowances: list[dict[str, object]] = []
    for index, raw in enumerate(allowances_raw):
        context = f"{path}.allowances[{index}]"
        table = _table(raw, context)
        closed_keys(table, {"term", "paths", "reason"}, context)
        term = table.get("term")
        reason = table.get("reason")
        if not isinstance(term, str) or not term or not isinstance(reason, str) or not reason:
            raise CorpusError(f"{context}: term and reason must be non-empty strings")
        paths = _strings(table.get("paths"), f"{context}.paths", required=True)
        for item in paths:
            try:
                relative_path(item, f"{context}.paths")
            except ConfigurationError as error:
                raise CorpusError(str(error)) from error
        allowances.append(
            {
                "term": term,
                "paths": list(paths),
                "reason": reason,
            }
        )
    return ConsumerVocabulary(
        accepted=_strings(terminology.get("accepted", []), f"{path}.terminology.accepted"),
        rejected=_strings(terminology.get("rejected", []), f"{path}.terminology.rejected"),
        replacements={str(key): str(item) for key, item in replacements_raw.items()},
        acronyms=_strings(acronym_table.get("accepted", []), f"{path}.acronyms.accepted"),
        roles=_closed_mapping_of_strings(value.get("roles", {}), f"{path}.roles", ROLE_KEYS),
        allowances=tuple(allowances),
        locale=locale,
        source_additions=_closed_mapping_of_strings(
            value.get("sources", {}), f"{path}.sources", SOURCE_KEYS
        ),
    )


def _normalized(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.casefold()).strip("_")


def _pattern(term: str) -> str:
    parts = re.split(r"[\s_-]+", term)
    separator = r"[\s_-]+"
    return rf"\b{separator.join(re.escape(part) for part in parts)}\b"


def _vale_rule(level: str, terms: set[str]) -> str:
    patterns = sorted({_pattern(term) for term in terms}) or ["a^"]
    lines = [
        "extends: existence",
        "message: \"Replace vague terminology '%s' with the exact operation, object, or property.\"",
        f"level: {level}",
        "ignorecase: true",
        "tokens:",
        *(f"  - {json.dumps(pattern)}" for pattern in patterns),
    ]
    return "\n".join(lines) + "\n"


def _symlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(os.path.relpath(source, destination.parent), target_is_directory=True)


def _resolved(corpus: Corpus, consumer: ConsumerVocabulary) -> dict[str, object]:
    shared: dict[str, tuple[str, str]] = {}
    for rule in corpus.terms:
        if rule.prose == "off":
            continue
        for form in rule.forms:
            shared[_normalized(form)] = (form, rule.prose)
    forbidden_acceptance = sorted(term for term in consumer.accepted if _normalized(term) in shared)
    if forbidden_acceptance:
        raise CorpusError(
            "consumer accepted terms cannot disable shared rules: "
            + ", ".join(forbidden_acceptance)
        )
    consumer_rejected = set(consumer.rejected) | set(consumer.replacements)
    copied_errors = sorted(
        term for term in consumer_rejected if shared.get(_normalized(term), ("", ""))[1] == "error"
    )
    if copied_errors:
        raise CorpusError("consumer vocabulary copies shared errors: " + ", ".join(copied_errors))
    promoted = {
        _normalized(term)
        for term in consumer_rejected
        if shared.get(_normalized(term), ("", ""))[1] == "warning"
    }
    shared_errors = {form for rule in corpus.terms if rule.prose == "error" for form in rule.forms}
    shared_warnings = {
        form
        for rule in corpus.terms
        if rule.prose == "warning"
        for form in rule.forms
        if _normalized(form) not in promoted
    }
    repository_errors = set(consumer_rejected)
    accepted = (
        set(corpus.accepted)
        | set(corpus.acronyms)
        | set(consumer.accepted)
        | set(consumer.acronyms)
        | set(consumer.replacements.values())
    )
    roles = {key: sorted(set(values)) for key, values in corpus.roles.items()}
    for key, values in consumer.roles.items():
        roles[key] = sorted(set(roles.get(key, [])) | set(values))
    sources = {key: sorted(set(values)) for key, values in corpus.sources.items()}
    for key, values in consumer.source_additions.items():
        sources[key] = sorted(set(sources.get(key, [])) | set(values))
    return {
        "locale": consumer.locale or corpus.locale,
        "shared_errors": sorted(shared_errors),
        "shared_warnings": sorted(shared_warnings),
        "repository_errors": sorted(repository_errors),
        "accepted": sorted(accepted, key=str.casefold),
        "replacements": consumer.replacements,
        "hedges": list(corpus.hedges),
        "fillers": list(corpus.fillers),
        "roles": roles,
        "identifier_rejections": sorted(
            {
                _normalized(form)
                for rule in corpus.terms
                if rule.identifier_severity != "off"
                for form in rule.forms
            }
        ),
        "identifier_accepted": list(corpus.identifier_accepted),
        "commit_rules": [
            {
                "id": rule.identifier,
                "forms": list(rule.forms),
                "severity": rule.commit,
                "guidance": rule.guidance,
                "suggestions": list(rule.suggestions),
            }
            for rule in corpus.terms
            if rule.commit != "off"
        ],
        "acronyms": sorted(set(corpus.acronyms) | set(consumer.acronyms)),
        "allowances": list(consumer.allowances),
        "sources": sources,
        "documents": corpus.documents,
    }


def _write_outputs(stage: Path, root: Path, resolved: dict[str, object]) -> str:
    canonical = json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    (stage / "vale/styles/OwnedTerms").mkdir(parents=True)
    (stage / "vale/styles/RepositoryTerms").mkdir(parents=True)
    central_styles = root / "config" / "vale" / "styles"
    for name in ("STECode", "ai-tells", "config"):
        _symlink(central_styles / name, stage / "vale" / "styles" / name)
    shutil.copy2(root / "config/vale/.vale.ini", stage / "vale/.vale.ini")
    shutil.copy2(root / "config/vale/ai-tells.ini", stage / "vale/ai-tells.ini")
    (stage / "vale/styles/OwnedTerms/Forbidden.yml").write_text(
        _vale_rule("error", set(cast(list[str], resolved["shared_errors"]))), encoding="utf-8"
    )
    (stage / "vale/styles/OwnedTerms/Questionable.yml").write_text(
        _vale_rule("warning", set(cast(list[str], resolved["shared_warnings"]))),
        encoding="utf-8",
    )
    (stage / "vale/styles/RepositoryTerms/Forbidden.yml").write_text(
        _vale_rule("error", set(cast(list[str], resolved["repository_errors"]))),
        encoding="utf-8",
    )
    cspell = {
        "version": "0.2",
        "language": str(resolved["locale"]),
        "useGitignore": True,
        "words": resolved["accepted"],
    }
    (stage / "cspell.json").write_text(
        f"{json.dumps(cspell, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    for name, value in (
        (
            "identifiers.json",
            {
                "accepted": resolved["identifier_accepted"],
                "rejected": resolved["identifier_rejections"],
                "roles": resolved["roles"],
            },
        ),
        ("commits.json", {"rules": resolved["commit_rules"]}),
        (
            "source-decisions.json",
            {
                "sources": resolved["sources"],
                "documents": resolved["documents"],
                "allowances": resolved["allowances"],
            },
        ),
        ("resolved.json", {**resolved, "digest": digest}),
    ):
        (stage / name).write_text(
            f"{json.dumps(value, indent=2, sort_keys=True)}\n", encoding="utf-8"
        )
    return digest


def build_corpus(target_value: Path, root: Path | None = None) -> tuple[str, Path]:
    """Generate every tool-native corpus input through one atomic target update."""
    root = (root or toolkit_root()).resolve()
    target = resolve_target(target_value)
    if not status(target, root)["current"]:
        raise CorpusError("repository deployment is stale; run qat repo sync")
    corpus = load_corpus(root)
    consumer = load_consumer_vocabulary(target)
    resolved = _resolved(corpus, consumer)
    staging_root = target / ".git" / "qat" / "corpus-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="build-", dir=staging_root))
    stage = work / "corpus"
    stage.mkdir()
    destination = target / ".qat" / "generated" / "corpus"
    previous = staging_root / f"previous-{uuid.uuid4().hex}"
    moved_previous = False
    try:
        digest = _write_outputs(stage, root, resolved)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            os.replace(destination, previous)
            moved_previous = True
        os.replace(stage, destination)
        if previous.exists():
            shutil.rmtree(previous)
        return digest, destination
    except Exception:
        if moved_previous and not destination.exists():
            os.replace(previous, destination)
        raise
    finally:
        if previous.exists():
            shutil.rmtree(previous)
        if work.exists():
            shutil.rmtree(work)
