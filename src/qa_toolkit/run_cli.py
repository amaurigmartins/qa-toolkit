"""Command-line surfaces for check, Sentinel, and advisory execution."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

from qa_toolkit.runner import guarded_execute


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-run")
    parser.add_argument("mode", choices=("check", "sentinel", "advisory"))
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--variant")
    parser.add_argument("--advisory", action="store_true")
    parser.add_argument("--changed", action="append", default=[])
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Execute one repository quality mode."""
    options = _parser().parse_args(arguments)
    mode = cast(Literal["check", "sentinel", "advisory"], options.mode)
    code, _ = guarded_execute(
        options.target,
        mode,
        variant=options.variant,
        include_advisory=options.advisory,
        changed=tuple(options.changed),
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
