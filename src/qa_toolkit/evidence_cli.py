"""Show or export repository-local evidence directories."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.deployment import DeploymentError, resolve_target


def _latest(target: Path) -> Path:
    evidence = target / ".git" / "qat" / "evidence"
    runs = sorted(path for path in evidence.iterdir() if (path / "summary.json").is_file())
    if not runs:
        raise DeploymentError("no evidence run exists")
    return runs[-1]


def main(arguments: Sequence[str] | None = None) -> None:
    """Show the latest summary or copy one complete evidence directory."""
    parser = argparse.ArgumentParser(prog="qat-evidence")
    parser.add_argument("operation", choices=("show", "export"))
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--run", type=Path)
    parser.add_argument("--destination", type=Path)
    options = parser.parse_args(arguments)
    try:
        target = resolve_target(options.target)
        run = options.run.resolve() if options.run else _latest(target)
        evidence_root = (target / ".git" / "qat" / "evidence").resolve()
        if run.parent != evidence_root or not (run / "summary.json").is_file():
            raise DeploymentError("run must name a repository-local evidence directory")
        if options.operation == "show":
            print(json.dumps(json.loads((run / "summary.json").read_text()), indent=2))
        else:
            if options.destination is None:
                raise DeploymentError("export requires --destination")
            destination = options.destination.resolve()
            if destination.exists():
                raise DeploymentError(f"refusing to replace export destination: {destination}")
            shutil.copytree(run, destination, symlinks=True)
            print(destination)
    except (DeploymentError, OSError, json.JSONDecodeError) as error:
        print(f"qat-evidence-{options.operation}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
