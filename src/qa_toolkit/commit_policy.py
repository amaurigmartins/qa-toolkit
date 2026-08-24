"""Validate ordinary commit messages with one managed terminology corpus."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qa_toolkit.corpus import load_consumer_vocabulary, load_corpus

SUPPORTED_TYPES = frozenset(
    {"build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test"}
)
SUBJECT_LENGTH_LIMIT = 72
EMPTY_SUBJECTS = frozenset({"changes", "cleanup", "fix", "misc", "update", "wip"})
COCOGITTO_ARGUMENTS = (
    "verify",
    "--ignore-merge-commits",
    "--ignore-fixup-commits",
    "--file",
    "-",
)

_CONVENTIONAL = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()\r\n]*)\))?(?:!)?: (?P<subject>[^\r\n]*)$"
)
_LIFECYCLE = re.compile(r'^(?:Merge .+|Revert ".+"|(?:fixup|amend|squash)! .+)$')
_LEADING_WORD = re.compile(r"^[A-Za-z]+(?:-[A-Za-z]+)*")
_NON_IMPERATIVE = frozenset(
    {
        "added",
        "adding",
        "adds",
        "allowed",
        "allowing",
        "allows",
        "bound",
        "binding",
        "binds",
        "blocked",
        "blocking",
        "blocks",
        "changed",
        "changing",
        "changes",
        "checked",
        "checking",
        "checks",
        "cleaned",
        "cleaning",
        "cleans",
        "created",
        "creating",
        "creates",
        "documented",
        "documenting",
        "documents",
        "enforced",
        "enforcing",
        "enforces",
        "fixed",
        "fixing",
        "fixes",
        "implemented",
        "implementing",
        "implements",
        "improved",
        "improving",
        "improves",
        "moved",
        "moving",
        "moves",
        "prevented",
        "preventing",
        "prevents",
        "rejected",
        "rejecting",
        "rejects",
        "removed",
        "removing",
        "removes",
        "resolved",
        "resolving",
        "resolves",
        "ran",
        "running",
        "runs",
        "supported",
        "supporting",
        "supports",
        "updated",
        "updating",
        "updates",
        "validated",
        "validating",
        "validates",
    }
)


@dataclass(frozen=True, slots=True)
class CommitFinding:
    """One stable commit-message diagnostic."""

    code: str
    severity: str
    message: str


def subject_line(message: str) -> str:
    """Return the first line with an optional carriage return removed."""
    return message.partition("\n")[0].removesuffix("\r")


def is_lifecycle_message(message: str) -> bool:
    """Return whether Git owns the message as a merge or rewrite operation."""
    return _LIFECYCLE.fullmatch(subject_line(message)) is not None


def structural_findings(message: str) -> tuple[CommitFinding, ...]:
    """Validate the supported Conventional Commit structure."""
    parsed = _CONVENTIONAL.fullmatch(subject_line(message))
    if parsed is None:
        return (
            CommitFinding(
                "QCM001",
                "error",
                "use '<type>(<scope>): <imperative subject>' Conventional Commit syntax",
            ),
        )
    findings = []
    commit_type = parsed.group("type")
    scope = parsed.group("scope")
    subject = parsed.group("subject").strip()
    if commit_type not in SUPPORTED_TYPES:
        findings.append(
            CommitFinding(
                "QCM002",
                "error",
                f"unsupported commit type {commit_type!r}; use: "
                + ", ".join(sorted(SUPPORTED_TYPES)),
            )
        )
    if scope is None or not scope.strip():
        findings.append(CommitFinding("QCM003", "error", "commit scope must not be empty"))
    if len(subject) > SUBJECT_LENGTH_LIMIT:
        findings.append(
            CommitFinding(
                "QCM004",
                "error",
                f"commit subject exceeds {SUBJECT_LENGTH_LIMIT} characters",
            )
        )
    leading = _LEADING_WORD.match(subject)
    if leading is None or leading.group() != leading.group().lower():
        findings.append(
            CommitFinding(
                "QCM005",
                "error",
                "commit subject must begin with a lowercase imperative verb",
            )
        )
    elif leading.group().casefold() in _NON_IMPERATIVE:
        findings.append(
            CommitFinding(
                "QCM006",
                "error",
                "commit subject must use the imperative form of its leading verb",
            )
        )
    if subject.casefold() in EMPTY_SUBJECTS:
        findings.append(
            CommitFinding(
                "QCM007",
                "error",
                "commit subject must name a concrete action and object",
            )
        )
    return tuple(findings)


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _term_pattern(value: str) -> re.Pattern[str]:
    parts = re.split(r"[\s_-]+", value)
    joined = r"[\s_-]+".join(re.escape(part) for part in parts)
    return re.compile(
        rf"(?<![A-Za-z0-9]){joined}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def terminology_findings(target: Path, message: str, root: Path) -> tuple[CommitFinding, ...]:
    """Apply shared and consumer commit terminology without duplicate matches."""
    corpus = load_corpus(root)
    consumer = load_consumer_vocabulary(target)
    consumer_terms = set(consumer.rejected) | set(consumer.replacements)
    promoted = {_normalized(term) for term in consumer_terms}
    findings = []
    for rule in corpus.terms:
        if rule.commit == "off":
            continue
        matched = next(
            (
                form
                for form in rule.forms
                if _normalized(form) not in promoted and _term_pattern(form).search(message)
            ),
            None,
        )
        if matched is not None:
            findings.append(
                CommitFinding(
                    "QCT001",
                    rule.commit,
                    f"{matched!r}: {rule.guidance}",
                )
            )
    for term in sorted(consumer_terms, key=str.casefold):
        if _term_pattern(term).search(message):
            replacement = consumer.replacements.get(term)
            suffix = f"; use {replacement!r}" if replacement else ""
            findings.append(
                CommitFinding("QCT002", "error", f"repository rejects {term!r}{suffix}")
            )
    return tuple(findings)


def render(findings: tuple[CommitFinding, ...], label: str) -> str:
    """Render findings in evaluation order."""
    return "\n".join(
        f"{label}: {finding.code} {finding.severity}: {finding.message}" for finding in findings
    )
