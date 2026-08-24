"""Small atomic file replacement helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_bytes(path: Path, content: bytes, mode: int = 0o644) -> None:
    """Replace one ordinary file after flushing its complete content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
