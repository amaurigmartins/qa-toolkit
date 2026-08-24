"""Resolve paths owned by the central toolkit repository."""

from __future__ import annotations

from pathlib import Path


def toolkit_root() -> Path:
    """Return the repository root containing this package source."""
    return Path(__file__).resolve().parents[2]


def payload_root(root: Path | None = None) -> Path:
    """Return the ignored payload directory for *root*."""
    return (root or toolkit_root()) / "toolkit"
