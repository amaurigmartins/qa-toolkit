"""Store only the current repository guardrail breaker and Sentinel proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from qa_toolkit.config import digest_consumer, digest_profile, load_consumer, load_profile
from qa_toolkit.deployment import DeploymentError, git_bytes
from qa_toolkit.filesystem import atomic_bytes


class GuardrailStateError(RuntimeError):
    """Report invalid local breaker or proof state."""


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        return git_bytes(repository, *arguments)
    except DeploymentError as error:
        raise GuardrailStateError(f"cannot inspect repository state: {error}") from error


def identity(target: Path, root: Path) -> dict[str, object]:
    """Return the exact current toolkit, target, worktree, and profile identity."""
    target_revision = _git(target, "rev-parse", "HEAD").decode().strip()
    toolkit_revision = _git(root, "rev-parse", "HEAD").decode().strip()
    if len(target_revision) != 40 or len(toolkit_revision) != 40:
        raise GuardrailStateError("guardrail identity requires exact Git revisions")
    status = _git(target, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    consumer = load_consumer(target)
    profile = load_profile(consumer.profile, root)
    return {
        "toolkit_revision": toolkit_revision,
        "target_revision": target_revision,
        "worktree_fingerprint": hashlib.sha256(status).hexdigest(),
        "dirty": bool(status),
        "profile_digest": digest_profile(profile),
        "consumer_digest": digest_consumer(consumer),
    }


def _directory(target: Path) -> Path:
    return target / ".git" / "qat" / "guardrails"


def _atomic(path: Path, value: dict[str, object]) -> None:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    atomic_bytes(path, content)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65_536:
        raise GuardrailStateError(f"refusing irregular guardrail state: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GuardrailStateError(f"cannot parse guardrail state: {path.name}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise GuardrailStateError(f"invalid guardrail state: {path.name}")
    return value


def record_proof(target: Path, root: Path, evidence: Path) -> dict[str, object]:
    """Replace the current proof after one successful, stable Sentinel run."""
    evidence_root = (target / ".git" / "qat" / "evidence").resolve()
    resolved = evidence.resolve()
    if evidence_root not in resolved.parents or not (resolved / "summary.json").is_file():
        raise GuardrailStateError("Sentinel proof requires repository-local evidence")
    value = {
        "schema_version": 1,
        **identity(target, root),
        "evidence": resolved.relative_to(target / ".git" / "qat").as_posix(),
    }
    _atomic(_directory(target) / "proof.json", value)
    breaker = _directory(target) / "breaker.json"
    if breaker.exists():
        if breaker.is_symlink() or not breaker.is_file():
            raise GuardrailStateError("refusing irregular breaker state")
        breaker.unlink()
    return value


def proof_status(target: Path, root: Path) -> dict[str, object]:
    """Return whether the one retained Sentinel proof matches current state."""
    proof = _read(_directory(target) / "proof.json")
    if proof is None:
        return {"present": False, "current": False}
    expected = identity(target, root)
    current = all(proof.get(key) == value for key, value in expected.items())
    evidence = proof.get("evidence")
    if not isinstance(evidence, str):
        current = False
    else:
        summary = target / ".git" / "qat" / evidence / "summary.json"
        current = current and summary.is_file() and not summary.is_symlink()
    return {"present": True, "current": current, "evidence": evidence}


def open_breaker(target: Path, root: Path, reason: str) -> None:
    """Replace the current breaker with one bounded observed failure."""
    detail = " ".join(reason.split())[:1000]
    if not detail:
        raise GuardrailStateError("breaker reason must not be empty")
    _atomic(
        _directory(target) / "breaker.json",
        {"schema_version": 1, **identity(target, root), "reason": detail},
    )


def breaker_status(target: Path, root: Path) -> dict[str, object]:
    """Return the one retained breaker and whether it matches current state."""
    breaker = _read(_directory(target) / "breaker.json")
    if breaker is None:
        return {"open": False, "current": False}
    expected = identity(target, root)
    current = all(breaker.get(key) == value for key, value in expected.items())
    return {"open": True, "current": current, "reason": breaker.get("reason")}
