"""Language-neutral semantic identifier grammar evaluation."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from qa_toolkit.deployment import DeploymentError, tracked_regular_files
from qa_toolkit.models import Consumer, Gate
from qa_toolkit.paths import toolkit_root

_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_TERM = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_CALLABLE = re.compile(r"^_?[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_ROLE_ELEMENT = re.compile(r"^\{([a-z][a-z0-9_]*)\}$")
_VISIBILITIES = frozenset({"public", "private"})
_SYMBOL_TYPES = frozenset({"function", "method"})
_FINDING_CODES = {
    "uncovered": "USV001",
    "unknown": "USV002",
    "owned": "USV003",
    "grammar": "USV004",
    "selector": "USV005",
    "term": "USV006",
}


class VocabularyError(ValueError):
    """Raised when vocabulary policy or syntax extraction cannot be trusted."""


@dataclass(frozen=True, slots=True)
class IdentifierRecord:
    """Language adapter output consumed by the semantic evaluator."""

    text: str
    language: str
    symbol_type: str
    visibility: str
    path: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Boundary:
    """One path-specific semantic naming boundary."""

    id: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    symbol_types: frozenset[str]
    visibility: frozenset[str]
    grammars: tuple[str, ...]
    roles: dict[str, frozenset[str]]
    allowed_identifier_terms: frozenset[str]
    action_grammars: dict[str, tuple[str, ...]]
    action_selectors: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class VocabularyCase:
    """One project-owned semantic policy example."""

    id: str
    path: str
    identifier: str
    symbol_type: str
    visibility: str
    boundary: str
    expect: str
    hint: str | None


@dataclass(frozen=True, slots=True)
class VocabularyPolicy:
    """Validated terminology, grammar, boundary, and example policy."""

    accepted: tuple[str, ...]
    rejected: tuple[str, ...]
    replacements: dict[str, str]
    identifier_rejected: tuple[str, ...]
    identifier_replacements: dict[str, str]
    identifier_include: tuple[str, ...]
    identifier_exclude: tuple[str, ...]
    identifier_visibility: frozenset[str]
    spelling_include: tuple[str, ...]
    spelling_exclude: tuple[str, ...]
    roles: dict[str, frozenset[str]]
    grammars: dict[str, tuple[tuple[str, ...], ...]]
    boundaries: tuple[Boundary, ...]
    contract_coverage: str
    cases: tuple[VocabularyCase, ...]


@dataclass(frozen=True, slots=True)
class VocabularyFinding:
    """One stable semantic identifier policy finding."""

    code: str
    path: str
    line: int
    column: int
    identifier: str
    boundary: str
    message: str
    hint: str

    def as_dict(self) -> dict[str, Any]:
        """Return finding data for JSON output and evidence."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VocabularyResolution:
    """Optional semantic gate and the exact policy digest it evaluates."""

    gates: tuple[Gate, ...]
    digest: str | None


GrammarMatch = tuple[tuple[str, str], ...]


def _central_identifier_terms(root: Path | None) -> tuple[str, ...]:
    """Return the shared identifier terms in snake-case form."""
    repository = (root or toolkit_root()).resolve()
    document = tomllib.loads((repository / "corpus/vocabulary.toml").read_text(encoding="utf-8"))
    raw_terms = document.get("terms")
    if not isinstance(raw_terms, list):
        raise VocabularyError("shared corpus terms must be an array")
    terms = {
        re.sub(r"[^a-z0-9]+", "_", form.casefold()).strip("_")
        for rule in raw_terms
        if isinstance(rule, dict) and rule.get("identifier", "off") != "off"
        for form in rule.get("forms", [])
        if isinstance(form, str)
    }
    return tuple(sorted(term for term in terms if term))


def load_vocabulary(
    path: Path, *, target: Path | None = None, root: Path | None = None
) -> VocabularyPolicy:
    """Load the closed vocabulary schema from a regular, contained file."""
    data = _load_vocabulary_document(path, target)
    accepted, rejected, replacements, spelling_include, spelling_exclude = _load_terminology(data)
    (
        local_identifier_rejected,
        identifier_replacements,
        identifier_include,
        identifier_exclude,
        identifier_visibility,
    ) = _load_identifier_terms(data)
    local_identifier_forbidden = set(local_identifier_rejected) | set(identifier_replacements)
    identifier_rejected = tuple(
        sorted(set(local_identifier_rejected) | set(_central_identifier_terms(root)))
    )
    forbidden = set(rejected) | set(replacements)
    identifier_forbidden = set(identifier_rejected) | set(identifier_replacements)
    roles = _load_roles(data, forbidden | local_identifier_forbidden)
    grammars = _load_grammars(data, roles)
    boundaries = _load_boundaries(data, roles, grammars, identifier_forbidden)
    coverage, cases = _load_cases(data, boundaries)
    policy = VocabularyPolicy(
        accepted=accepted,
        rejected=rejected,
        replacements=replacements,
        identifier_rejected=identifier_rejected,
        identifier_replacements=identifier_replacements,
        identifier_include=identifier_include,
        identifier_exclude=identifier_exclude,
        identifier_visibility=identifier_visibility,
        spelling_include=spelling_include,
        spelling_exclude=spelling_exclude,
        roles=roles,
        grammars=grammars,
        boundaries=boundaries,
        contract_coverage=coverage,
        cases=cases,
    )
    validate_vocabulary_contract(policy)
    return policy


def _load_vocabulary_document(path: Path, target: Path | None) -> dict[str, Any]:
    resolved = _resolve_vocabulary_path(path, target)
    try:
        data = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise VocabularyError(f"cannot load vocabulary policy {path}: {exc}") from exc
    _closed(
        data,
        {
            "schema_version",
            "terminology",
            "identifiers",
            "roles",
            "grammars",
            "boundaries",
            "contract",
            "cases",
        },
        "vocabulary",
    )
    if data.get("schema_version") != 3 or isinstance(data.get("schema_version"), bool):
        raise VocabularyError("vocabulary requires schema_version = 3")
    return data


def _resolve_vocabulary_path(path: Path, target: Path | None) -> Path:
    resolved_target = target.resolve(strict=True) if target is not None else None
    candidate = path if resolved_target is None or path.is_absolute() else resolved_target / path
    if resolved_target is not None:
        relative = _relative_to_target(candidate, resolved_target)
        if relative is not None:
            _reject_symlink_chain(resolved_target, relative)
    elif candidate.is_symlink():
        raise VocabularyError(f"refusing symlinked vocabulary policy: {candidate}")
    resolved = _resolve_existing_policy(candidate)
    if resolved_target is not None and not _is_contained(resolved, resolved_target):
        raise VocabularyError(f"vocabulary policy escapes target root: {path}")
    return resolved


def _relative_to_target(path: Path, target: Path) -> Path | None:
    raw_path = path if path.is_absolute() else target / path
    try:
        return raw_path.relative_to(target)
    except ValueError:
        return None


def _reject_symlink_chain(target: Path, relative: Path) -> None:
    current = target
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise VocabularyError(f"refusing symlinked vocabulary policy path: {current}")


def _resolve_existing_policy(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise VocabularyError(f"cannot resolve vocabulary policy {path}: {exc}") from exc


def _is_contained(path: Path, target: Path) -> bool:
    return path == target or target in path.parents


def _load_terminology(
    data: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, str], tuple[str, ...], tuple[str, ...]]:
    terminology = _table(data.get("terminology"), "terminology")
    _closed(
        terminology,
        {"accepted", "rejected", "include", "exclude", "replacements"},
        "terminology",
    )
    accepted = _accepted_terms(terminology.get("accepted", []), "terminology.accepted")
    rejected = _terms(terminology.get("rejected", []), "terminology.rejected")
    spelling_include = _strings(
        terminology.get("include", ["**/*.py", "**/*.md", "**/*.markdown"]),
        "terminology.include",
        required=True,
    )
    spelling_exclude = _strings(terminology.get("exclude", []), "terminology.exclude")
    replacements = _replacements(terminology.get("replacements", {}), "terminology.replacements")
    flagged = set(rejected) | set(replacements)
    invalid_targets = sorted(flagged & set(replacements.values()))
    if invalid_targets:
        raise VocabularyError(
            "terminology replacement targets may not also be rejected: "
            + ", ".join(invalid_targets)
        )
    return accepted, rejected, replacements, spelling_include, spelling_exclude


def _load_identifier_terms(
    data: dict[str, Any],
) -> tuple[
    tuple[str, ...],
    dict[str, str],
    tuple[str, ...],
    tuple[str, ...],
    frozenset[str],
]:
    identifiers = _table(data.get("identifiers", {}), "identifiers")
    _closed(
        identifiers,
        {"rejected", "replacements", "include", "exclude", "visibility"},
        "identifiers",
    )
    identifier_rejected = _terms(identifiers.get("rejected", []), "identifiers.rejected")
    identifier_replacements = _replacements(
        identifiers.get("replacements", {}), "identifiers.replacements"
    )
    identifier_include = _strings(
        identifiers.get("include", ["**/*.py"]), "identifiers.include", required=True
    )
    identifier_exclude = _strings(identifiers.get("exclude", []), "identifiers.exclude")
    _validate_globs(identifier_include, "identifiers.include")
    _validate_globs(identifier_exclude, "identifiers.exclude")
    identifier_visibility = frozenset(
        _strings(
            identifiers.get("visibility", sorted(_VISIBILITIES)),
            "identifiers.visibility",
            required=True,
        )
    )
    unknown_visibility = sorted(identifier_visibility - _VISIBILITIES)
    if unknown_visibility:
        raise VocabularyError(
            "identifiers.visibility contains unsupported values: " + ", ".join(unknown_visibility)
        )
    identifier_flagged = set(identifier_rejected) | set(identifier_replacements)
    invalid_identifier_targets = sorted(identifier_flagged & set(identifier_replacements.values()))
    if invalid_identifier_targets:
        raise VocabularyError(
            "identifier replacement targets may not also be rejected: "
            + ", ".join(invalid_identifier_targets)
        )
    return (
        identifier_rejected,
        identifier_replacements,
        identifier_include,
        identifier_exclude,
        identifier_visibility,
    )


def _load_roles(data: dict[str, Any], forbidden: set[str]) -> dict[str, frozenset[str]]:
    roles_raw = _table(data.get("roles"), "roles")
    if not roles_raw:
        raise VocabularyError("roles must define at least one semantic role")
    roles: dict[str, frozenset[str]] = {}
    for role, values in sorted(roles_raw.items()):
        if not isinstance(role, str) or not _TERM.fullmatch(role):
            raise VocabularyError(f"invalid role name: {role!r}")
        roles[role] = frozenset(_terms(values, f"roles.{role}", required=True))
    rejected_roles = sorted(forbidden & {term for terms in roles.values() for term in terms})
    if rejected_roles:
        raise VocabularyError(
            "rejected terminology may not be assigned semantic roles: " + ", ".join(rejected_roles)
        )
    return roles


def _load_grammars(
    data: dict[str, Any], roles: dict[str, frozenset[str]]
) -> dict[str, tuple[tuple[str, ...], ...]]:
    grammars_raw = _table(data.get("grammars"), "grammars")
    if not grammars_raw:
        raise VocabularyError("grammars must define at least one named grammar")
    grammars: dict[str, tuple[tuple[str, ...], ...]] = {}
    for grammar, raw_shapes in sorted(grammars_raw.items()):
        grammars[grammar] = _load_grammar(grammar, raw_shapes, roles)
    return grammars


def _load_grammar(
    grammar: object, raw_shapes: object, roles: dict[str, frozenset[str]]
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(grammar, str) or not _TERM.fullmatch(grammar):
        raise VocabularyError(f"invalid grammar name: {grammar!r}")
    if not isinstance(raw_shapes, list) or not raw_shapes:
        raise VocabularyError(f"grammar {grammar!r} must contain shapes")
    return tuple(
        _load_grammar_shape(grammar, index, raw_shape, roles)
        for index, raw_shape in enumerate(raw_shapes)
    )


def _load_grammar_shape(
    grammar: str, index: int, raw_shape: object, roles: dict[str, frozenset[str]]
) -> tuple[str, ...]:
    shape = _strings(raw_shape, f"grammars.{grammar}[{index}]", required=True, unique=False)
    for element in shape:
        _validate_grammar_element(grammar, element, roles)
    return shape


def _validate_grammar_element(grammar: str, element: str, roles: dict[str, frozenset[str]]) -> None:
    match = _ROLE_ELEMENT.fullmatch(element)
    if match is not None and match.group(1) not in roles:
        raise VocabularyError(f"grammar {grammar!r} references unknown role {match.group(1)!r}")
    if match is None and not _TERM.fullmatch(element):
        raise VocabularyError(f"grammar {grammar!r} has invalid literal element {element!r}")


def _load_boundaries(
    data: dict[str, Any],
    roles: dict[str, frozenset[str]],
    grammars: dict[str, tuple[tuple[str, ...], ...]],
    identifier_forbidden: set[str],
) -> tuple[Boundary, ...]:
    raw_boundaries = data.get("boundaries")
    if not isinstance(raw_boundaries, list) or not raw_boundaries:
        raise VocabularyError("boundaries must be a non-empty array of tables")
    boundaries: list[Boundary] = []
    seen_ids: set[str] = set()
    for index, raw_boundary in enumerate(raw_boundaries):
        boundary = _load_boundary(raw_boundary, index, roles, grammars, identifier_forbidden)
        if boundary.id in seen_ids:
            raise VocabularyError(f"duplicate boundary id: {boundary.id}")
        seen_ids.add(boundary.id)
        boundaries.append(boundary)
    return tuple(boundaries)


def _load_boundary(
    raw_boundary: object,
    index: int,
    roles: dict[str, frozenset[str]],
    grammars: dict[str, tuple[tuple[str, ...], ...]],
    identifier_forbidden: set[str],
) -> Boundary:
    field = f"boundaries[{index}]"
    boundary = _table(raw_boundary, field)
    _closed(
        boundary,
        {
            "id",
            "include",
            "exclude",
            "symbol_types",
            "visibility",
            "grammars",
            "roles",
            "allowed_identifier_terms",
            "action_grammars",
            "action_selectors",
        },
        field,
    )
    boundary_id = boundary.get("id")
    if not isinstance(boundary_id, str) or not _ID.fullmatch(boundary_id):
        raise VocabularyError(f"{field}.id must be a lowercase identifier")
    include = _strings(boundary.get("include"), f"{field}.include", required=True)
    exclude = _strings(boundary.get("exclude", []), f"{field}.exclude")
    _validate_globs(include + exclude, field)
    symbol_types = _allowed_values(boundary, "symbol_types", field, _SYMBOL_TYPES)
    visibility = _allowed_values(boundary, "visibility", field, _VISIBILITIES)
    boundary_grammars = _known_grammars(boundary.get("grammars"), field, grammars)
    allowed = _boundary_roles(boundary, field, roles)
    exceptions = frozenset(
        _terms(boundary.get("allowed_identifier_terms", []), f"{field}.allowed_identifier_terms")
    )
    unknown_exceptions = sorted(exceptions - identifier_forbidden)
    if unknown_exceptions:
        raise VocabularyError(
            f"{field}.allowed_identifier_terms contains terms that are not rejected: "
            + ", ".join(unknown_exceptions)
        )
    return Boundary(
        id=boundary_id,
        include=include,
        exclude=exclude,
        symbol_types=symbol_types,
        visibility=visibility,
        grammars=boundary_grammars,
        roles=allowed,
        allowed_identifier_terms=exceptions,
        action_grammars=_boundary_action_grammars(boundary, field, roles, grammars, allowed),
        action_selectors=_boundary_action_selectors(boundary, field, roles, allowed),
    )


def _allowed_values(
    boundary: dict[str, Any], key: str, field: str, supported: frozenset[str]
) -> frozenset[str]:
    values = frozenset(_strings(boundary.get(key), f"{field}.{key}", required=True))
    if not values <= supported:
        raise VocabularyError(f"{field}.{key} contains unsupported values")
    return values


def _known_grammars(
    raw: object, field: str, grammars: dict[str, tuple[tuple[str, ...], ...]]
) -> tuple[str, ...]:
    selected = _strings(raw, f"{field}.grammars", required=True)
    missing = sorted(set(selected) - set(grammars))
    if missing:
        raise VocabularyError(f"{field} references unknown grammars: {', '.join(missing)}")
    return selected


def _boundary_roles(
    boundary: dict[str, Any], field: str, roles: dict[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    raw = _table(boundary.get("roles"), f"{field}.roles")
    unknown_roles = sorted(set(raw) - set(roles))
    if unknown_roles:
        raise VocabularyError(f"{field} contains unknown roles: {', '.join(unknown_roles)}")
    allowed: dict[str, frozenset[str]] = {}
    for role, values in sorted(raw.items()):
        terms = frozenset(_terms(values, f"{field}.roles.{role}"))
        unknown_terms = sorted(terms - roles[role])
        if unknown_terms:
            raise VocabularyError(
                f"{field}.roles.{role} contains undeclared terms: {', '.join(unknown_terms)}"
            )
        allowed[role] = terms
    return allowed


def _boundary_action_grammars(
    boundary: dict[str, Any],
    field: str,
    roles: dict[str, frozenset[str]],
    grammars: dict[str, tuple[tuple[str, ...], ...]],
    allowed: dict[str, frozenset[str]],
) -> dict[str, tuple[str, ...]]:
    raw = _table(boundary.get("action_grammars", {}), f"{field}.action_grammars")
    rules: dict[str, tuple[str, ...]] = {}
    for action, values in sorted(raw.items()):
        _validate_boundary_action(action, field, "grammar", roles, allowed)
        selected = _strings(values, f"{field}.action_grammars.{action}", required=True)
        missing = sorted(set(selected) - set(grammars))
        if missing:
            raise VocabularyError(
                f"{field} grammar rule references unknown grammars: {', '.join(missing)}"
            )
        rules[action] = selected
    return rules


def _boundary_action_selectors(
    boundary: dict[str, Any],
    field: str,
    roles: dict[str, frozenset[str]],
    allowed: dict[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    raw = _table(boundary.get("action_selectors", {}), f"{field}.action_selectors")
    rules: dict[str, frozenset[str]] = {}
    for action, values in sorted(raw.items()):
        _validate_boundary_action(action, field, "selector", roles, allowed)
        selectors = frozenset(_terms(values, f"{field}.action_selectors.{action}"))
        unknown = sorted(selectors - roles.get("selector", frozenset()))
        if unknown:
            raise VocabularyError(
                f"{field} selector rule contains unknown selectors: {', '.join(unknown)}"
            )
        rules[action] = selectors
    return rules


def _validate_boundary_action(
    action: str,
    field: str,
    rule_kind: str,
    roles: dict[str, frozenset[str]],
    allowed: dict[str, frozenset[str]],
) -> None:
    if action not in roles.get("action", frozenset()):
        raise VocabularyError(f"{field} {rule_kind} rule has unknown action {action!r}")
    boundary_actions = allowed.get("action")
    if boundary_actions is not None and action not in boundary_actions:
        raise VocabularyError(
            f"{field} {rule_kind} rule action {action!r} is not owned by the boundary"
        )


def _load_cases(
    data: dict[str, Any], boundaries: tuple[Boundary, ...]
) -> tuple[str, tuple[VocabularyCase, ...]]:
    contract = _table(data.get("contract"), "contract")
    _closed(contract, {"coverage"}, "contract")
    coverage = contract.get("coverage")
    if coverage != "strict":
        raise VocabularyError("contract.coverage must be 'strict'")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise VocabularyError("cases must be a non-empty array of tables")
    cases: list[VocabularyCase] = []
    case_ids: set[str] = set()
    boundary_ids = {boundary.id for boundary in boundaries}
    expected_results = {
        "pass",
        _FINDING_CODES["owned"],
        _FINDING_CODES["grammar"],
        _FINDING_CODES["selector"],
        _FINDING_CODES["term"],
    }
    for index, raw_case in enumerate(raw_cases):
        case = _load_case(raw_case, index, boundary_ids, expected_results)
        if case.id in case_ids:
            raise VocabularyError(f"duplicate vocabulary case id: {case.id}")
        case_ids.add(case.id)
        cases.append(case)
    return coverage, tuple(cases)


def _load_case(
    raw_case: object,
    index: int,
    boundary_ids: set[str],
    expected_results: set[str],
) -> VocabularyCase:
    field = f"cases[{index}]"
    case = _table(raw_case, field)
    _closed(
        case,
        {"id", "path", "identifier", "symbol_type", "visibility", "boundary", "expect", "hint"},
        field,
    )
    case_id = _case_identifier(case, field, "id", _ID, "a lowercase identifier")
    pure_path = _case_path(case, field)
    identifier = _case_identifier(
        case, field, "identifier", _CALLABLE, "a snake_case callable name"
    )
    symbol_type = _case_choice(case, field, "symbol_type", _SYMBOL_TYPES, "unsupported")
    visibility = _case_choice(case, field, "visibility", _VISIBILITIES, "unsupported")
    boundary_id = _case_choice(
        case, field, "boundary", boundary_ids, "references an unknown boundary"
    )
    expect = _case_choice(
        case, field, "expect", expected_results, "is not a stable vocabulary result"
    )
    hint = _case_hint(case, field)
    return VocabularyCase(
        id=case_id,
        path=pure_path.as_posix(),
        identifier=identifier,
        symbol_type=symbol_type,
        visibility=visibility,
        boundary=boundary_id,
        expect=expect,
        hint=hint,
    )


def _case_identifier(
    case: dict[str, Any], field: str, key: str, pattern: re.Pattern[str], requirement: str
) -> str:
    value = case.get(key)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VocabularyError(f"{field}.{key} must be {requirement}")
    return value


def _case_path(case: dict[str, Any], field: str) -> PurePosixPath:
    value = case.get("path")
    if not isinstance(value, str) or not value:
        raise VocabularyError(f"{field}.path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(char in value for char in "\x00*?[]"):
        raise VocabularyError(f"{field}.path must be a contained representative path")
    return path


def _case_choice(
    case: dict[str, Any], field: str, key: str, supported: set[str] | frozenset[str], error: str
) -> str:
    value = case.get(key)
    if not isinstance(value, str) or value not in supported:
        raise VocabularyError(f"{field}.{key} {error}")
    return value


def _case_hint(case: dict[str, Any], field: str) -> str | None:
    hint = case.get("hint")
    if hint is not None and (not isinstance(hint, str) or not hint):
        raise VocabularyError(f"{field}.hint must be a non-empty string")
    return hint


def validate_vocabulary_contract(policy: VocabularyPolicy) -> None:
    """Prove the project-owned positive and negative semantic examples."""
    passing: set[str] = set()
    failing: set[str] = set()
    for case in policy.cases:
        actual = _evaluate_contract_case(policy, case)
        if actual == "pass":
            passing.add(case.boundary)
        else:
            if actual in {_FINDING_CODES["uncovered"], _FINDING_CODES["unknown"]}:
                raise VocabularyError(
                    f"UVP201 case {case.id!r} is not a structural near miss: {actual}"
                )
            failing.add(case.boundary)
    _validate_contract_coverage(policy, passing, failing)


def _evaluate_contract_case(policy: VocabularyPolicy, case: VocabularyCase) -> str:
    record = _contract_record(case)
    findings = _contract_findings(policy, case, record)
    actual = "pass" if not findings else findings[0].code
    _validate_case_result(case, findings, actual)
    return actual


def _contract_record(case: VocabularyCase) -> IdentifierRecord:
    return IdentifierRecord(
        text=case.identifier,
        language="contract",
        symbol_type=case.symbol_type,
        visibility=case.visibility,
        path=case.path,
        line=1,
        column=1,
    )


def _contract_findings(
    policy: VocabularyPolicy, case: VocabularyCase, record: IdentifierRecord
) -> tuple[VocabularyFinding, ...]:
    try:
        if not _identifier_selected(policy, record):
            raise VocabularyError(f"UVP201 case {case.id!r} is outside identifier scope")
        resolved = _resolve_boundary(policy, record)
        if resolved.id != case.boundary:
            raise VocabularyError(
                f"UVP201 case {case.id!r} resolved boundary {resolved.id!r}, "
                f"expected {case.boundary!r}"
            )
        return evaluate_vocabulary(policy, (record,))
    except VocabularyError as exc:
        if str(exc).startswith("UVP201"):
            raise
        raise VocabularyError(f"UVP201 case {case.id!r} failed to evaluate: {exc}") from exc


def _validate_case_result(
    case: VocabularyCase, findings: tuple[VocabularyFinding, ...], actual: str
) -> None:
    if len(findings) > 1:
        raise VocabularyError(f"UVP201 case {case.id!r} produced multiple findings")
    if actual != case.expect:
        raise VocabularyError(f"UVP201 case {case.id!r} expected {case.expect}, observed {actual}")
    if case.hint is not None and (not findings or findings[0].hint != case.hint):
        observed = findings[0].hint if findings else "no finding"
        raise VocabularyError(
            f"UVP201 case {case.id!r} expected hint {case.hint!r}, observed {observed!r}"
        )


def _validate_contract_coverage(
    policy: VocabularyPolicy, passing: set[str], failing: set[str]
) -> None:
    if policy.contract_coverage != "strict":
        return
    boundaries = {boundary.id for boundary in policy.boundaries}
    missing_pass = sorted(boundaries - passing)
    missing_fail = sorted(boundaries - failing)
    detail: list[str] = []
    if missing_pass:
        detail.append("accepted cases: " + ", ".join(missing_pass))
    if missing_fail:
        detail.append("rejected near misses: " + ", ".join(missing_fail))
    if detail:
        raise VocabularyError("UVP202 strict contract coverage missing " + "; ".join(detail))


def evaluate_vocabulary(
    policy: VocabularyPolicy, records: tuple[IdentifierRecord, ...]
) -> tuple[VocabularyFinding, ...]:
    """Evaluate typed identifiers without parsing source code or prose."""
    findings: list[VocabularyFinding] = []
    for record in sorted(records, key=lambda item: (item.path, item.line, item.column, item.text)):
        if (
            record.text.startswith("__") and record.text.endswith("__")
        ) or not _identifier_selected(policy, record):
            continue
        finding = _evaluate_identifier(policy, record)
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def _identifier_selected(policy: VocabularyPolicy, record: IdentifierRecord) -> bool:
    return (
        record.visibility in policy.identifier_visibility
        and any(_matches(record.path, pattern) for pattern in policy.identifier_include)
        and not any(_matches(record.path, pattern) for pattern in policy.identifier_exclude)
    )


def _evaluate_identifier(
    policy: VocabularyPolicy, record: IdentifierRecord
) -> VocabularyFinding | None:
    boundary = _resolve_boundary(policy, record)
    raw_units = _identifier_units(record.text, policy, normalize=False)
    term_finding = _identifier_term_finding(policy, record, boundary, raw_units)
    if term_finding is not None:
        return term_finding
    units = _identifier_units(record.text, policy, normalize=True)
    ownership = _hard_role_violation(units, boundary, policy)
    if ownership is not None:
        return _ownership_finding(policy, record, boundary, *ownership)
    selector = _hard_selector_violation(units, boundary, policy)
    if selector is not None:
        return _selector_finding(record, boundary, *selector)
    matches = _global_matches(units, boundary, policy)
    if not matches:
        return _unmatched_finding(policy, record, boundary, units)
    allowed = [match for match in matches if _boundary_allows(match, boundary)]
    if not allowed:
        disallowed = _first_disallowed(matches[0], boundary)
        return _ownership_finding(policy, record, boundary, *disallowed)
    selector = _selector_problem(allowed, boundary)
    return _selector_finding(record, boundary, *selector) if selector is not None else None


def _identifier_term_finding(
    policy: VocabularyPolicy,
    record: IdentifierRecord,
    boundary: Boundary,
    units: tuple[str, ...],
) -> VocabularyFinding | None:
    problem = next(
        (
            term
            for term in units
            if (term in policy.identifier_rejected or term in policy.identifier_replacements)
            and term not in boundary.allowed_identifier_terms
        ),
        None,
    )
    if problem is None:
        return None
    preferred = policy.identifier_replacements.get(problem)
    hint = f"use {preferred!r}" if preferred is not None else "use a boundary-owned term"
    return _finding("term", record, boundary, f"identifier term {problem!r} is rejected", hint)


def _ownership_finding(
    policy: VocabularyPolicy,
    record: IdentifierRecord,
    boundary: Boundary,
    role: str,
    term: str,
) -> VocabularyFinding:
    owners = sorted(
        item.id for item in policy.boundaries if term in item.roles.get(role, frozenset())
    )
    owner_text = ", ".join(owners) if owners else "no configured boundary"
    return _finding(
        "owned",
        record,
        boundary,
        f"{role} term {term!r} is not owned by this boundary",
        f"configured owner: {owner_text}",
    )


def _selector_finding(
    record: IdentifierRecord,
    boundary: Boundary,
    action: str,
    selector: str,
    permitted: frozenset[str],
) -> VocabularyFinding:
    return _finding(
        "selector",
        record,
        boundary,
        f"action {action!r} may not use selector {selector!r}",
        "allowed selectors: " + ", ".join(sorted(permitted)),
    )


def _unmatched_finding(
    policy: VocabularyPolicy,
    record: IdentifierRecord,
    boundary: Boundary,
    units: tuple[str, ...],
) -> VocabularyFinding:
    literals = {
        element
        for shapes in policy.grammars.values()
        for shape in shapes
        for element in shape
        if _ROLE_ELEMENT.fullmatch(element) is None
    }
    unknown = tuple(
        unit for unit in units if unit not in literals and not _roles_for(unit, policy.roles)
    )
    if unknown:
        return _finding(
            "unknown",
            record,
            boundary,
            f"identifier contains terms without semantic roles: {', '.join(unknown)}",
            "declare semantic role terms or rename the identifier",
        )
    return _finding(
        "grammar",
        record,
        boundary,
        "identifier does not match an allowed semantic grammar",
        "allowed shapes: " + ", ".join(_shape_text(policy, boundary, units)),
    )


def _selector_problem(
    matches: list[GrammarMatch], boundary: Boundary
) -> tuple[str, str, frozenset[str]] | None:
    problem: tuple[str, str, frozenset[str]] | None = None
    for match in matches:
        action = _matched_term(match, "action")
        selector = _matched_term(match, "selector")
        permitted = boundary.action_selectors.get(action or "")
        if action is None or selector is None or permitted is None or selector in permitted:
            return None
        problem = (action, selector, permitted)
    return problem


def extract_python_identifiers(
    target: Path, *, executable: str = "ast-grep", batch_size: int = 128
) -> tuple[IdentifierRecord, ...]:
    """Extract functions and methods from stable batches of tracked Python files."""
    root = target.resolve(strict=True)
    binary = shutil.which(executable)
    if binary is None:
        raise VocabularyError("ast-grep is required for the Python vocabulary adapter")
    files = _tracked_python_files(root)
    records: list[IdentifierRecord] = []
    for offset in range(0, len(files), batch_size):
        batch = files[offset : offset + batch_size]
        command = (
            binary,
            "outline",
            "--json=stream",
            "--lang",
            "python",
            "--items",
            "structure",
            "--view",
            "expanded",
            "--color",
            "never",
            *batch,
        )
        try:
            result = _run_captured(command, cwd=root, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            raise VocabularyError(f"ast-grep outline invocation failed: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            raise VocabularyError(f"ast-grep outline failed: {detail}")
        records.extend(_parse_outline_stream(result.stdout, batch))
    return tuple(sorted(records, key=lambda item: (item.path, item.line, item.column, item.text)))


def _run_captured(
    command: tuple[str, ...], *, cwd: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def extract_identifiers(
    target: Path, languages: tuple[str, ...], *, executable: str = "ast-grep"
) -> tuple[IdentifierRecord, ...]:
    """Run the Python syntax adapter when Python is selected."""
    unsupported = sorted(set(languages) - {"julia", "python"})
    if unsupported:
        raise VocabularyError("unsupported semantic vocabulary adapters: " + ", ".join(unsupported))
    if not languages:
        raise VocabularyError("semantic vocabulary requires at least one supported adapter")
    if "python" not in languages:
        return ()
    return extract_python_identifiers(target, executable=executable)


def _tracked_python_files(target: Path) -> tuple[str, ...]:
    try:
        return tuple(path for path in tracked_regular_files(target) if path.endswith(".py"))
    except DeploymentError as exc:
        raise VocabularyError(f"cannot enumerate tracked Python files: {exc}") from exc


def _parse_outline_stream(output: str, expected: tuple[str, ...]) -> tuple[IdentifierRecord, ...]:
    records: list[IdentifierRecord] = []
    seen: set[str] = set()
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        path, items = _outline_payload(line, line_number, expected, seen)
        seen.add(path)
        records.extend(_outline_items(items, path))
    missing = sorted(set(expected) - seen)
    if missing:
        raise VocabularyError(
            "ast-grep returned empty success without outline payloads for: " + ", ".join(missing)
        )
    return tuple(records)


def _outline_payload(
    line: str, line_number: int, expected: tuple[str, ...], seen: set[str]
) -> tuple[str, list[object]]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise VocabularyError(f"malformed ast-grep outline JSON at line {line_number}") from exc
    if not isinstance(payload, dict) or payload.get("language") != "Python":
        raise VocabularyError("ast-grep returned an unsupported outline payload")
    path = payload.get("path")
    items = payload.get("items")
    if not isinstance(path, str) or path not in expected or path in seen:
        raise VocabularyError(f"ast-grep returned an unexpected outline path: {path!r}")
    if not isinstance(items, list):
        raise VocabularyError(f"ast-grep outline items are malformed for {path}")
    return path, items


def _outline_items(items: list[object], path: str) -> tuple[IdentifierRecord, ...]:
    records: list[IdentifierRecord] = []
    for item in items:
        record = _outline_record(item, path, "function")
        if record is not None:
            records.append(record)
        records.extend(_outline_members(item, path))
    return tuple(records)


def _outline_members(item: object, path: str) -> tuple[IdentifierRecord, ...]:
    if not isinstance(item, dict) or item.get("symbolType") != "class":
        return ()
    members = item.get("members", [])
    if not isinstance(members, list):
        raise VocabularyError(f"ast-grep class members are malformed for {path}")
    return tuple(
        record
        for member in members
        if (record := _outline_record(member, path, "method")) is not None
    )


def _outline_record(raw: object, path: str, expected_type: str) -> IdentifierRecord | None:
    if not isinstance(raw, dict):
        raise VocabularyError(f"ast-grep outline item is malformed for {path}")
    if raw.get("symbolType") != expected_type:
        return None
    name = _outline_name(raw, path)
    if name.startswith("__") and name.endswith("__"):
        return None
    line, column = _outline_position(raw, path)
    return IdentifierRecord(
        text=name,
        language="python",
        symbol_type=expected_type,
        visibility="private" if name.startswith("_") else "public",
        path=path,
        line=line + 1,
        column=column + 1,
    )


def _outline_name(raw: dict[str, Any], path: str) -> str:
    name = raw.get("name")
    if not isinstance(name, str) or not isinstance(raw.get("range"), dict):
        raise VocabularyError(f"ast-grep outline identifier is malformed for {path}")
    return name


def _outline_position(raw: dict[str, Any], path: str) -> tuple[int, int]:
    range_data = raw.get("range")
    if not isinstance(range_data, dict) or not isinstance(range_data.get("start"), dict):
        raise VocabularyError(f"ast-grep outline range is malformed for {path}")
    start = range_data["start"]
    line = start.get("line")
    column = start.get("column")
    if not isinstance(line, int) or not isinstance(column, int):
        raise VocabularyError(f"ast-grep outline position is malformed for {path}")
    return line, column


def _resolve_boundary(policy: VocabularyPolicy, record: IdentifierRecord) -> Boundary:
    candidates = [
        boundary
        for boundary in policy.boundaries
        if record.symbol_type in boundary.symbol_types
        and record.visibility in boundary.visibility
        and any(_matches(record.path, pattern) for pattern in boundary.include)
        and not any(_matches(record.path, pattern) for pattern in boundary.exclude)
    ]
    if not candidates:
        raise VocabularyError(
            f"{_FINDING_CODES['uncovered']} {record.path}:{record.line}: "
            f"no boundary covers {record.symbol_type} {record.text!r}"
        )
    scored = [
        (
            max(
                _specificity(pattern) for pattern in item.include if _matches(record.path, pattern)
            ),
            item,
        )
        for item in candidates
    ]
    best_score = max(score for score, _ in scored)
    best = [item for score, item in scored if score == best_score]
    if len(best) != 1:
        raise VocabularyError(
            f"ambiguous vocabulary boundaries for {record.path}: "
            + ", ".join(sorted(item.id for item in best))
        )
    return best[0]


def _identifier_units(
    identifier: str, policy: VocabularyPolicy, *, normalize: bool = True
) -> tuple[str, ...]:
    tokens = [token for token in identifier.strip("_").split("_") if token]
    compounds = sorted(
        {term for values in policy.roles.values() for term in values if "_" in term}
        | set(policy.replacements)
        | set(policy.identifier_rejected)
        | set(policy.identifier_replacements),
        key=lambda term: (-len(term.split("_")), term),
    )
    units: list[str] = []
    index = 0
    while index < len(tokens):
        match = next(
            (
                term
                for term in compounds
                if tokens[index : index + len(term.split("_"))] == term.split("_")
            ),
            None,
        )
        if match is None:
            token = tokens[index]
            units.append(policy.replacements.get(token, token) if normalize else token)
            index += 1
        else:
            units.append(policy.replacements.get(match, match) if normalize else match)
            index += len(match.split("_"))
    return tuple(units)


def _global_matches(
    units: tuple[str, ...], boundary: Boundary, policy: VocabularyPolicy
) -> list[GrammarMatch]:
    matches: list[GrammarMatch] = []
    grammar_names = boundary.grammars
    if units:
        grammar_names = boundary.action_grammars.get(units[0], grammar_names)
    for grammar in grammar_names:
        for shape in policy.grammars[grammar]:
            match = _match_shape(shape, units, policy.roles)
            if match is not None:
                matches.append(match)
    return matches


def _match_shape(
    shape: tuple[str, ...], units: tuple[str, ...], roles: dict[str, frozenset[str]]
) -> GrammarMatch | None:
    if len(shape) != len(units):
        return None
    captured: list[tuple[str, str]] = []
    for element, unit in zip(shape, units, strict=True):
        role_match = _ROLE_ELEMENT.fullmatch(element)
        if role_match is None:
            if element != unit:
                return None
            continue
        role = role_match.group(1)
        if unit not in roles[role]:
            return None
        captured.append((role, unit))
    return tuple(captured)


def _boundary_allows(match: GrammarMatch, boundary: Boundary) -> bool:
    return all(role not in boundary.roles or term in boundary.roles[role] for role, term in match)


def _matched_term(match: GrammarMatch, role: str) -> str | None:
    return next((term for candidate, term in match if candidate == role), None)


def _hard_role_violation(
    units: tuple[str, ...], boundary: Boundary, policy: VocabularyPolicy
) -> tuple[str, str] | None:
    """Apply boundary ownership where identifier position makes the role unambiguous."""
    action_problem = _hard_action_violation(units, boundary, policy)
    if action_problem is not None:
        return action_problem
    first_is_action = bool(units and units[0] in policy.roles.get("action", frozenset()))
    for index, term in enumerate(units):
        if index == 0 and first_is_action:
            continue
        problem = _hard_concept_violation(term, boundary, policy)
        if problem is not None:
            return problem
    return None


def _hard_action_violation(
    units: tuple[str, ...], boundary: Boundary, policy: VocabularyPolicy
) -> tuple[str, str] | None:
    if not units or units[0] not in policy.roles.get("action", frozenset()):
        return None
    allowed = boundary.roles.get("action")
    return ("action", units[0]) if allowed is not None and units[0] not in allowed else None


def _hard_concept_violation(
    term: str, boundary: Boundary, policy: VocabularyPolicy
) -> tuple[str, str] | None:
    assigned = frozenset(_roles_for(term, policy.roles))
    if not assigned or not assigned <= {"concept", "plural_concept"}:
        return None
    for role in ("concept", "plural_concept"):
        allowed = boundary.roles.get(role)
        if (
            allowed is not None
            and term in policy.roles.get(role, frozenset())
            and term not in allowed
        ):
            return role, term
    return None


def _hard_selector_violation(
    units: tuple[str, ...], boundary: Boundary, policy: VocabularyPolicy
) -> tuple[str, str, frozenset[str]] | None:
    """Enforce action selectors independently from a boundary's grammar strictness."""
    if len(units) < 3 or units[0] not in policy.roles.get("action", frozenset()):
        return None
    action = units[0]
    permitted = boundary.action_selectors.get(action)
    if permitted is None:
        return None
    for index, unit in enumerate(units[:-1]):
        if unit != "by":
            continue
        selector = units[index + 1]
        if selector in policy.roles.get("selector", frozenset()) and selector not in permitted:
            return action, selector, permitted
    return None


def _first_disallowed(match: GrammarMatch, boundary: Boundary) -> tuple[str, str]:
    for role, term in sorted(match):
        if role in boundary.roles and term not in boundary.roles[role]:
            return role, term
    raise AssertionError("match is boundary-safe")


def _roles_for(term: str, roles: dict[str, frozenset[str]]) -> tuple[str, ...]:
    return tuple(role for role, values in sorted(roles.items()) if term in values)


def _shape_text(
    policy: VocabularyPolicy, boundary: Boundary, units: tuple[str, ...]
) -> tuple[str, ...]:
    grammar_names = boundary.grammars
    if units:
        grammar_names = boundary.action_grammars.get(units[0], grammar_names)
    return tuple("_".join(shape) for grammar in grammar_names for shape in policy.grammars[grammar])


def _finding(
    kind: str,
    record: IdentifierRecord,
    boundary: Boundary,
    message: str,
    hint: str,
) -> VocabularyFinding:
    return VocabularyFinding(
        code=_FINDING_CODES[kind],
        path=record.path,
        line=record.line,
        column=record.column,
        identifier=record.text,
        boundary=boundary.id,
        message=message,
        hint=hint,
    )


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])
    )


def _specificity(pattern: str) -> tuple[int, int]:
    literal = sum(character not in "*?[]" for character in pattern)
    segments = sum(
        not any(character in part for character in "*?[]") for part in pattern.split("/")
    )
    return literal, segments


def _validate_globs(patterns: tuple[str, ...], field: str) -> None:
    for pattern in patterns:
        pure = PurePosixPath(pattern)
        if pure.is_absolute() or ".." in pure.parts or "\x00" in pattern:
            raise VocabularyError(f"{field} contains an unsafe path pattern: {pattern!r}")


def _closed(table: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise VocabularyError(f"{field} has unknown keys: {', '.join(unknown)}")


def _table(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VocabularyError(f"{field} must be a table")
    return value


def _strings(
    value: object, field: str, *, required: bool = False, unique: bool = True
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise VocabularyError(f"{field} must be an array of non-empty strings")
    result = tuple(value)
    if required and not result:
        raise VocabularyError(f"{field} may not be empty")
    if unique and len(set(result)) != len(result):
        raise VocabularyError(f"{field} contains duplicates")
    return result


def _terms(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    terms = _strings(value, field, required=required)
    if any(not _TERM.fullmatch(term) for term in terms):
        raise VocabularyError(f"{field} requires lowercase snake_case terms")
    return terms


def _accepted_terms(value: object, field: str) -> tuple[str, ...]:
    terms = _strings(value, field)
    if any(any(character.isspace() for character in term) or "\x00" in term for term in terms):
        raise VocabularyError(f"{field} requires individual terminology entries")
    return terms


def _replacements(value: object, field: str) -> dict[str, str]:
    raw = _table(value, field)
    replacements: dict[str, str] = {}
    for rejected_term, preferred in sorted(raw.items()):
        if not isinstance(rejected_term, str) or not _TERM.fullmatch(rejected_term):
            raise VocabularyError(f"{field} requires lowercase snake_case keys")
        if not isinstance(preferred, str) or not _TERM.fullmatch(preferred):
            raise VocabularyError(
                f"replacement for {rejected_term!r} must be a lowercase snake_case term"
            )
        if rejected_term == preferred:
            raise VocabularyError(f"replacement {rejected_term!r} may not map to itself")
        replacements[rejected_term] = preferred
    return replacements


def resolve_vocabulary(consumer: Consumer, *, target: Path, root: Path) -> VocabularyResolution:
    """Add one central gate when the consumer declares semantic schema 3."""
    if consumer.vocabulary_file is None:
        return VocabularyResolution((), None)
    policy_path = target / consumer.vocabulary_file
    try:
        document = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise VocabularyError(f"cannot load vocabulary policy {policy_path}: {error}") from error
    if document.get("schema_version") != 3:
        return VocabularyResolution((), None)
    load_vocabulary(policy_path, target=target, root=root)
    shared = _central_identifier_terms(root)
    digest = hashlib.sha256(
        policy_path.read_bytes() + json.dumps(shared, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    relative = consumer.vocabulary_file.as_posix()
    gate = Gate(
        "python-semantic-vocabulary",
        "check",
        (
            "{qat-python}",
            "-m",
            "qa_toolkit.vocabulary",
            "--target",
            ".",
            "--policy",
            relative,
            "--ast-grep",
            "{tool:ast-grep}",
            "--language",
            "python",
        ),
        (relative, "**/*.py"),
        300,
        "blocking",
        (),
        (1,),
        (2,),
    )
    return VocabularyResolution((gate,), digest)


def main(arguments: Sequence[str] | None = None) -> None:
    """Evaluate one tracked semantic vocabulary policy."""
    parser = argparse.ArgumentParser(prog="qat-vocabulary")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--ast-grep", default="ast-grep")
    parser.add_argument("--language", action="append", choices=("python", "julia"), required=True)
    options = parser.parse_args(arguments)
    try:
        target = options.target.resolve(strict=True)
        policy = load_vocabulary(options.policy, target=target)
        records = extract_identifiers(target, tuple(options.language), executable=options.ast_grep)
        findings = evaluate_vocabulary(policy, records)
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}:{finding.column}: {finding.code} "
                f"{finding.identifier}: {finding.message}; {finding.hint}"
            )
        code = 1 if findings else 0
    except (DeploymentError, OSError, subprocess.SubprocessError, VocabularyError) as error:
        print(f"qat-vocabulary: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main(sys.argv[1:])
