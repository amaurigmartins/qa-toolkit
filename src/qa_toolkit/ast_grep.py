"""Resolve tracked consumer ast-grep rules into core-owned gates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from qa_toolkit.models import Consumer, Gate
from qa_toolkit.python_tools import _tracked_regular_files

_RULE_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})


class AstGrepPolicyError(ValueError):
    """Raised when a consumer ast-grep extension is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class ResolvedAstGrep:
    """Validated consumer ast-grep inputs and their core-owned gates."""

    gates: tuple[Gate, ...] = ()
    digest: str | None = None
    rule_ids: tuple[str, ...] = ()


def resolve_ast_grep(consumer: Consumer, *, target: Path, root: Path) -> ResolvedAstGrep:
    """Validate one consumer extension and construct its deterministic gates."""
    if consumer.ast_grep_config is None and consumer.ast_grep_tests is None:
        return ResolvedAstGrep()
    if consumer.ast_grep_config is None or consumer.ast_grep_tests is None:
        raise AstGrepPolicyError("consumer ast-grep declaration requires config and tests")
    policy = (consumer.ast_grep_config.as_posix(), consumer.ast_grep_tests.as_posix())
    tracked = _tracked_consumer_inputs(target)
    config_text, test_inputs, test_files = _declared_inputs(policy, target, tracked)
    rule_files = _declared_rule_files(policy, config_text, tracked)
    consumer_rules, rule_digests = _consumer_rules(target, rule_files, root)
    cases, case_digests = _consumer_rule_cases(target, test_files, consumer_rules)
    _require_complete_cases(consumer_rules, cases)
    inputs = [
        (policy[0], _content_digest(config_text)),
        *(
            (relative, _content_digest(_read(target, relative)))
            for relative in test_inputs
            if relative not in test_files
        ),
        *rule_digests,
        *case_digests,
    ]
    return ResolvedAstGrep(
        gates=_consumer_gates(policy),
        digest=_input_digest(inputs),
        rule_ids=tuple(sorted(consumer_rules)),
    )


def _tracked_consumer_inputs(target: Path) -> set[str]:
    try:
        return set(_tracked_regular_files(target))
    except (OSError, UnicodeError) as exc:
        raise AstGrepPolicyError(str(exc)) from exc


def _declared_inputs(
    policy: tuple[str, str], target: Path, tracked: set[str]
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    config, tests = policy
    if config not in tracked:
        raise AstGrepPolicyError(f"ast_grep.config must be a tracked regular file: {config}")
    test_inputs = _tracked_yaml_below(tracked, tests)
    test_files = tuple(path for path in test_inputs if "/__snapshots__/" not in f"/{path}")
    if not test_files:
        raise AstGrepPolicyError("ast_grep.tests must contain tracked YAML rule cases")
    return _read(target, config), test_inputs, test_files


def _declared_rule_files(
    policy: tuple[str, str], config_text: str, tracked: set[str]
) -> tuple[str, ...]:
    rule_directories = _rule_directories(config_text, policy[0])
    rule_files = tuple(
        sorted(
            {
                path
                for directory in rule_directories
                for path in _tracked_yaml_below(tracked, directory)
            }
        )
    )
    if not rule_files:
        raise AstGrepPolicyError("consumer ast-grep configuration must select tracked YAML rules")
    return rule_files


def _consumer_rules(
    target: Path, rule_files: tuple[str, ...], root: Path
) -> tuple[dict[str, tuple[str, str]], tuple[tuple[str, str], ...]]:
    managed = _managed_rules(root)
    consumer: dict[str, tuple[str, str]] = {}
    inputs: list[tuple[str, str]] = []
    for relative in rule_files:
        text = _read(target, relative)
        rule_id, body = _rule(text, relative)
        if rule_id in consumer:
            raise AstGrepPolicyError(f"duplicate consumer ast-grep rule id: {rule_id}")
        body_digest = _content_digest(body)
        if rule_id in managed:
            raise AstGrepPolicyError(f"consumer ast-grep rule copies managed rule id: {rule_id}")
        if body_digest in managed.values():
            raise AstGrepPolicyError(
                f"consumer ast-grep rule copies a managed rule body: {rule_id}"
            )
        consumer[rule_id] = (relative, body_digest)
        inputs.append((relative, _content_digest(text)))
    return consumer, tuple(inputs)


def _consumer_rule_cases(
    target: Path,
    test_files: tuple[str, ...],
    consumer: dict[str, tuple[str, str]],
) -> tuple[dict[str, tuple[bool, bool]], tuple[tuple[str, str], ...]]:
    cases: dict[str, tuple[bool, bool]] = {}
    inputs: list[tuple[str, str]] = []
    for relative in test_files:
        text = _read(target, relative)
        rule_id, has_valid, has_invalid = _rule_cases(text, relative)
        if rule_id in cases:
            raise AstGrepPolicyError(f"duplicate consumer ast-grep rule test id: {rule_id}")
        if rule_id not in consumer:
            raise AstGrepPolicyError(f"consumer ast-grep tests name an unknown rule: {rule_id}")
        cases[rule_id] = (has_valid, has_invalid)
        inputs.append((relative, _content_digest(text)))
    return cases, tuple(inputs)


def _require_complete_cases(
    consumer: dict[str, tuple[str, str]], cases: dict[str, tuple[bool, bool]]
) -> None:
    for rule_id in sorted(consumer):
        valid, invalid = cases.get(rule_id, (False, False))
        if not valid or not invalid:
            raise AstGrepPolicyError(
                f"consumer ast-grep rule {rule_id} requires accepted and rejected cases"
            )


def _consumer_gates(policy: tuple[str, str]) -> tuple[Gate, ...]:
    config, tests = policy
    return (
        Gate(
            "consumer-ast-grep-tests",
            "check",
            (
                "{tool:ast-grep}",
                "test",
                "--config",
                config,
                "--test-dir",
                tests,
                "--color",
                "never",
            ),
            (config, f"{tests}/**"),
            120,
            "blocking",
            (),
            (1,),
            (2,),
        ),
        Gate(
            "consumer-ast-grep-scan",
            "check",
            ("{tool:ast-grep}", "scan", "--config", config, "--color", "never", "."),
            ("**",),
            120,
            "blocking",
            (),
            (1,),
            (2,),
        ),
    )


def _tracked_yaml_below(tracked: set[str], directory: str) -> tuple[str, ...]:
    prefix = directory.rstrip("/") + "/"
    return tuple(
        sorted(
            path
            for path in tracked
            if path.startswith(prefix) and PurePosixPath(path).suffix in _YAML_SUFFIXES
        )
    )


def _read(target: Path, relative: str) -> str:
    try:
        return (target / PurePosixPath(relative)).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AstGrepPolicyError(f"cannot read consumer ast-grep input {relative}: {exc}") from exc


def _rule_directories(text: str, config_path: str) -> tuple[str, ...]:
    values = _top_level_sequence(text, "ruleDirs")
    if not values:
        raise AstGrepPolicyError("consumer ast-grep config requires a non-empty ruleDirs list")
    parent = PurePosixPath(config_path).parent
    directories: list[str] = []
    for value in values:
        relative = parent / value
        normalized = relative.as_posix()
        if not _safe_path(value) or not _safe_path(normalized):
            raise AstGrepPolicyError(f"unsafe consumer ast-grep rule directory: {value}")
        directories.append(normalized)
    if len(set(directories)) != len(directories):
        raise AstGrepPolicyError("consumer ast-grep config contains duplicate rule directories")
    return tuple(directories)


def _rule(text: str, relative: str) -> tuple[str, str]:
    rule_id = _top_level_scalar(text, "id", relative)
    if _RULE_ID.fullmatch(rule_id) is None:
        raise AstGrepPolicyError(f"consumer ast-grep rule has an invalid id: {rule_id}")
    body = _top_level_block(text, "rule")
    normalized = "\n".join(
        line.rstrip()
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not normalized:
        raise AstGrepPolicyError(f"consumer ast-grep rule has no rule body: {relative}")
    return rule_id, normalized


def _rule_cases(text: str, relative: str) -> tuple[str, bool, bool]:
    rule_id = _top_level_scalar(text, "id", relative)
    if _RULE_ID.fullmatch(rule_id) is None:
        raise AstGrepPolicyError(f"consumer ast-grep rule test has an invalid id: {rule_id}")
    return (
        rule_id,
        _has_sequence_item(_top_level_block(text, "valid")),
        _has_sequence_item(_top_level_block(text, "invalid")),
    )


def _top_level_scalar(text: str, key: str, relative: str) -> str:
    matches: list[str] = re.findall(rf"(?m)^{re.escape(key)}:[ \t]*(.+?)[ \t]*$", text)
    if len(matches) != 1:
        raise AstGrepPolicyError(f"{relative} requires exactly one top-level {key}")
    raw = matches[0]
    if raw.startswith(("'", '"')):
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1].replace("''", "'")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AstGrepPolicyError(f"{relative} has an invalid quoted {key}") from exc
        if not isinstance(parsed, str):
            raise AstGrepPolicyError(f"{relative} has a non-string {key}")
        return parsed
    if " #" in raw:
        raw = raw.split(" #", 1)[0].rstrip()
    if not raw or any(character in raw for character in "{}[],:&*!|>@`"):
        raise AstGrepPolicyError(f"{relative} has an unsupported {key} scalar")
    return raw


def _top_level_block(text: str, key: str) -> str:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if re.fullmatch(rf"{key}:[ \t]*", line)]
    if len(starts) != 1:
        raise AstGrepPolicyError(f"consumer ast-grep YAML requires one top-level {key} block")
    block: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        block.append(line)
    return "\n".join(block)


def _top_level_sequence(text: str, key: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in _top_level_block(text, key).splitlines():
        match = re.fullmatch(r"[ \t]+-[ \t]+([^#]+?)[ \t]*(?:#.*)?", line)
        if match is not None:
            values.append(match.group(1).strip().strip("'\""))
        elif line.strip() and not line.lstrip().startswith("#"):
            raise AstGrepPolicyError(f"consumer ast-grep {key} must be a plain YAML sequence")
    return tuple(values)


def _has_sequence_item(block: str) -> bool:
    return any(re.match(r"[ \t]+-[ \t]+", line) for line in block.splitlines())


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and "\\" not in value
        and not any(character in value for character in "*?[]")
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _managed_rules(root: Path) -> dict[str, str]:
    managed: dict[str, str] = {}
    rules_root = root / "config" / "ast-grep"
    for resource in rules_root.rglob("*.yml"):
        if "/rules/" not in str(resource).replace("\\", "/"):
            continue
        text = resource.read_text(encoding="utf-8")
        rule_id, body = _rule(text, str(resource))
        managed[rule_id] = _content_digest(body)
    return managed


def _content_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _input_digest(inputs: list[tuple[str, str]]) -> str:
    canonical = json.dumps(sorted(inputs), separators=(",", ":"))
    return _content_digest(canonical)
