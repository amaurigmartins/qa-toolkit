"""Resolve an exact qa-toolkit identity from Git or immutable action delivery."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

EXACT_REVISION = re.compile(r"[0-9a-f]{40}")
REVISION_MARKER = ".qat-toolkit-revision"


class SourceIdentityError(RuntimeError):
    """Report an invalid or unavailable qa-toolkit source identity."""


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SourceIdentityError(f"cannot inspect qa-toolkit source: {error}") from error


def _owned_git_root(root: Path) -> bool:
    result = _git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return False
    try:
        resolved = Path(result.stdout.decode().strip()).resolve()
    except (OSError, UnicodeDecodeError) as error:
        raise SourceIdentityError("qa-toolkit Git root is invalid") from error
    return resolved == root.resolve()


def _exact(value: str) -> str:
    if EXACT_REVISION.fullmatch(value) is None:
        raise SourceIdentityError("qa-toolkit identity requires an exact 40-character revision")
    return value


def _marker_revision(root: Path) -> str:
    marker = root / REVISION_MARKER
    try:
        irregular = marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 41
    except OSError as error:
        raise SourceIdentityError("cannot inspect qa-toolkit action revision marker") from error
    if irregular:
        raise SourceIdentityError("qa-toolkit source has no exact Git or action revision")
    try:
        return _exact(marker.read_text(encoding="ascii").strip())
    except (OSError, UnicodeDecodeError) as error:
        raise SourceIdentityError("qa-toolkit action revision marker is invalid") from error


def toolkit_revision(root: Path) -> str:
    """Return the exact revision for a Git checkout or immutable action archive."""
    if not _owned_git_root(root):
        return _marker_revision(root)
    result = _git(root, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise SourceIdentityError("cannot resolve qa-toolkit Git revision")
    try:
        return _exact(result.stdout.decode().strip())
    except UnicodeDecodeError as error:
        raise SourceIdentityError("qa-toolkit Git revision is invalid") from error


def toolkit_facts(root: Path) -> tuple[str, bool, str]:
    """Return revision, dirty state, and fingerprint for qa-toolkit evidence."""
    if not _owned_git_root(root):
        return _marker_revision(root), False, hashlib.sha256(b"").hexdigest()
    revision = toolkit_revision(root)
    status = _git(root, "status", "--porcelain=v1", "-z")
    if status.returncode != 0:
        raise SourceIdentityError("cannot inspect qa-toolkit Git worktree")
    return revision, bool(status.stdout), hashlib.sha256(status.stdout).hexdigest()
