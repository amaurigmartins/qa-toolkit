"""Run Grain once with an explicit central configuration."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from grain.config import load_config  # type: ignore[import-untyped]
from grain.runner import (  # type: ignore[import-untyped]
    determine_exit_code,
    format_violations,
    run_checks,
)

from qa_toolkit.python_tools import _tracked_regular_files


def main(arguments: Sequence[str] | None = None) -> None:
    """Check tracked Python and Markdown inputs with one explicit config."""
    parser = argparse.ArgumentParser(prog="qat-grain")
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args(arguments)
    files = [
        path
        for path in _tracked_regular_files(Path.cwd())
        if path.endswith((".py", ".md", ".markdown"))
    ]
    violations = run_checks(files, load_config(options.config))
    print(format_violations(violations), end="")
    raise SystemExit(determine_exit_code(violations))


if __name__ == "__main__":
    main(sys.argv[1:])
