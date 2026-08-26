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
    literal_allowances: tuple[str, ...] = ()


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
        empty = _empty_consumer_vocabulary()
        return ConsumerVocabulary(
            tuple(dict.fromkeys((*consumer.vocabulary_additions, *consumer.vocabulary_allowances))),
            empty.rejected,
            empty.replacements,
            empty.acronyms,
            empty.roles,
            empty.allowances,
            empty.locale,
            empty.source_additions,
        )
    path = target / consumer.vocabulary_file
    value = _load_toml(path)
    if value.get("schema_version") == 3:
        # The semantic loader imports the shared corpus and must be resolved after module loading.
        from qa_toolkit.vocabulary import VocabularyError, load_vocabulary  # noqa: PLC0415

        try:
            policy = load_vocabulary(path, target=target)
        except VocabularyError as error:
            raise CorpusError(str(error)) from error
        shared_forms = {
            _normalized(form)
            for rule in load_corpus().terms
            if rule.prose != "off"
            for form in rule.forms
        }
        accepted = tuple(
            dict.fromkeys(
                (
                    *(term for term in policy.accepted if _normalized(term) not in shared_forms),
                    *consumer.vocabulary_additions,
                    *consumer.vocabulary_allowances,
                )
            )
        )
        return ConsumerVocabulary(
            accepted=accepted,
            rejected=policy.rejected,
            replacements=policy.replacements,
            acronyms=(),
            roles={key: tuple(sorted(values)) for key, values in policy.roles.items()},
            allowances=(),
            locale="en-US",
            source_additions={},
            literal_allowances=policy.accepted,
        )
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
    accepted = _strings(terminology.get("accepted", []), f"{path}.terminology.accepted")
    return ConsumerVocabulary(
        accepted=tuple(
            dict.fromkeys(
                (
                    *accepted,
                    *consumer.vocabulary_additions,
                    *consumer.vocabulary_allowances,
                )
            )
        ),
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


def _vale_rule_name(identifier: str) -> str:
    return "".join(part.capitalize() for part in identifier.split("-") if part)


def _vale_existence_rule(
    level: str,
    terms: set[str],
    guidance: str,
    suggestions: tuple[str, ...] = (),
) -> str:
    patterns = sorted({_pattern(term) for term in terms}) or ["a^"]
    message = f"{guidance.rstrip()} Found '%s'."
    lines = [
        "extends: existence",
        f"message: {json.dumps(message)}",
        f"level: {level}",
        "ignorecase: true",
        "tokens:",
        *(f"  - {json.dumps(pattern)}" for pattern in patterns),
    ]
    if suggestions:
        lines.extend(
            (
                "action:",
                "  name: replace",
                "  params:",
                *(f"    - {json.dumps(suggestion)}" for suggestion in suggestions),
            )
        )
    return "\n".join(lines) + "\n"


def _vale_substitution_rule(level: str, term: str, replacement: str, guidance: str) -> str:
    message = f"{guidance.rstrip()} Use '%s' instead of '%s'."
    return "\n".join(
        (
            "extends: substitution",
            f"message: {json.dumps(message)}",
            f"level: {level}",
            "ignorecase: true",
            "swap:",
            f"  {json.dumps(_pattern(term))}: {json.dumps(replacement)}",
            "",
        )
    )


def _symlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source.resolve(strict=True), target_is_directory=True)


def _resolved(corpus: Corpus, consumer: ConsumerVocabulary) -> dict[str, object]:
    shared: dict[str, tuple[str, str]] = {}
    shared_rule_by_form: dict[str, TermRule] = {}
    for rule in corpus.terms:
        if rule.prose == "off":
            continue
        for form in rule.forms:
            shared[_normalized(form)] = (form, rule.prose)
            shared_rule_by_form[_normalized(form)] = rule
    literal_allowances = {_normalized(term) for term in consumer.literal_allowances}
    forbidden_acceptance = sorted(
        term
        for term in consumer.accepted
        if _normalized(term) in shared and _normalized(term) not in literal_allowances
    )
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
    replacement_forms = {_normalized(term) for term in consumer.replacements}
    shared_prose_rules: list[dict[str, object]] = []
    repository_prose_rules: list[dict[str, object]] = []
    for rule in corpus.terms:
        if rule.prose == "off":
            continue
        shared_forms = tuple(
            form
            for form in rule.forms
            if rule.prose != "warning" or _normalized(form) not in promoted
        )
        if shared_forms:
            shared_prose_rules.append(
                {
                    "id": rule.identifier,
                    "forms": list(shared_forms),
                    "severity": rule.prose,
                    "guidance": rule.guidance,
                    "suggestions": list(rule.suggestions),
                }
            )
        promoted_forms = tuple(
            form
            for form in rule.forms
            if rule.prose == "warning"
            and _normalized(form) in promoted
            and _normalized(form) not in replacement_forms
        )
        if promoted_forms:
            repository_prose_rules.append(
                {
                    "id": f"promoted-{rule.identifier}",
                    "forms": list(promoted_forms),
                    "severity": "error",
                    "guidance": rule.guidance,
                    "suggestions": list(rule.suggestions),
                }
            )
    shared_warning_forms = {
        form for form, (_literal, severity) in shared.items() if severity == "warning"
    }
    repository_rejected = sorted(
        term
        for term in consumer.rejected
        if _normalized(term) not in shared_warning_forms
        and _normalized(term) not in replacement_forms
    )
    repository_replacements = []
    for term, replacement in sorted(
        consumer.replacements.items(), key=lambda item: item[0].casefold()
    ):
        shared_rule = shared_rule_by_form.get(_normalized(term))
        repository_replacements.append(
            {
                "id": f"replace-{_normalized(term).replace('_', '-')}",
                "term": term,
                "replacement": replacement,
                "guidance": (
                    shared_rule.guidance
                    if shared_rule is not None
                    else "Use the configured repository terminology."
                ),
            }
        )
    accepted = (
        set(corpus.accepted)
        | set(corpus.acronyms)
        | set(consumer.accepted)
        | set(consumer.acronyms)
        | set(consumer.replacements.values())
    )
    roles = {key: sorted(set(values)) for key, values in corpus.roles.items()}
    for key, consumer_values in consumer.roles.items():
        roles[key] = sorted(set(roles.get(key, [])) | set(consumer_values))
    for role_values in roles.values():
        accepted.update(role_values)
        for value in role_values:
            accepted.update(value.split("_"))
    sources = {key: sorted(set(values)) for key, values in corpus.sources.items()}
    for key, additions in consumer.source_additions.items():
        sources[key] = sorted(set(sources.get(key, [])) | set(additions))
    return {
        "locale": consumer.locale or corpus.locale,
        "shared_errors": sorted(shared_errors),
        "shared_warnings": sorted(shared_warnings),
        "repository_errors": sorted(repository_errors),
        "accepted": sorted(accepted, key=str.casefold),
        "replacements": consumer.replacements,
        "shared_prose_rules": shared_prose_rules,
        "repository_prose_rules": repository_prose_rules,
        "repository_rejected": repository_rejected,
        "repository_replacements": repository_replacements,
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
        "literal_allowances": list(consumer.literal_allowances),
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
    vale_configuration = (root / "config/vale/.vale.ini").read_text(encoding="utf-8")
    locale = str(resolved["locale"]).casefold()
    if locale == "en-gb":
        spelling_override = "STECode.AmericanSpelling = NO"
    elif locale == "en-us":
        spelling_override = "STECode.BritishSpelling = NO"
    else:
        raise CorpusError(f"unsupported corpus locale: {resolved['locale']}")
    vale_configuration = vale_configuration.replace(
        "BasedOnStyles = STECode, OwnedTerms, RepositoryTerms\n",
        "BasedOnStyles = STECode, OwnedTerms, RepositoryTerms\n" + spelling_override + "\n",
    )
    (stage / "vale/.vale.ini").write_text(vale_configuration, encoding="utf-8")
    shutil.copy2(root / "config/vale/ai-tells.ini", stage / "vale/ai-tells.ini")
    for rule in cast(list[dict[str, object]], resolved.get("shared_prose_rules", [])):
        identifier = cast(str, rule["id"])
        (stage / f"vale/styles/OwnedTerms/{_vale_rule_name(identifier)}.yml").write_text(
            _vale_existence_rule(
                cast(str, rule["severity"]),
                set(cast(list[str], rule["forms"])),
                cast(str, rule["guidance"]),
                tuple(cast(list[str], rule["suggestions"])),
            ),
            encoding="utf-8",
        )
    (stage / "vale/styles/OwnedTerms/Hedges.yml").write_text(
        _vale_existence_rule(
            "warning",
            set(cast(list[str], resolved.get("hedges", []))),
            "Replace the hedge with a measured condition or uncertainty.",
        ),
        encoding="utf-8",
    )
    (stage / "vale/styles/OwnedTerms/Fillers.yml").write_text(
        _vale_existence_rule(
            "error",
            set(cast(list[str], resolved.get("fillers", []))),
            "Delete the filler or state the technical fact directly.",
        ),
        encoding="utf-8",
    )
    for rule in cast(list[dict[str, object]], resolved.get("repository_prose_rules", [])):
        identifier = cast(str, rule["id"])
        (stage / f"vale/styles/RepositoryTerms/{_vale_rule_name(identifier)}.yml").write_text(
            _vale_existence_rule(
                cast(str, rule["severity"]),
                set(cast(list[str], rule["forms"])),
                cast(str, rule["guidance"]),
                tuple(cast(list[str], rule["suggestions"])),
            ),
            encoding="utf-8",
        )
    (stage / "vale/styles/RepositoryTerms/Forbidden.yml").write_text(
        _vale_existence_rule(
            "error",
            set(cast(list[str], resolved.get("repository_rejected", []))),
            "Replace the repository term with precise wording.",
        ),
        encoding="utf-8",
    )
    for rule in cast(list[dict[str, object]], resolved.get("repository_replacements", [])):
        identifier = cast(str, rule["id"])
        (stage / f"vale/styles/RepositoryTerms/{_vale_rule_name(identifier)}.yml").write_text(
            _vale_substitution_rule(
                "error",
                cast(str, rule["term"]),
                cast(str, rule["replacement"]),
                cast(str, rule["guidance"]),
            ),
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
