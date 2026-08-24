"""Print one installed Python distribution version for registry verification."""

from __future__ import annotations

import importlib.metadata
import sys


def main() -> None:
    """Print the exact installed version named by one command argument."""
    if len(sys.argv) != 2:
        print("usage: python -m qa_toolkit.package_version DISTRIBUTION", file=sys.stderr)
        raise SystemExit(2)
    try:
        print(importlib.metadata.version(sys.argv[1]))
    except importlib.metadata.PackageNotFoundError as error:
        print(f"package is not installed: {sys.argv[1]}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
