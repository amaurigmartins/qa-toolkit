"""Build the resolved corpus for one enrolled repository."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.corpus import CorpusError, build_corpus
from qa_toolkit.deployment import DeploymentError
from qa_toolkit.models import ConfigurationError


def main(arguments: Sequence[str] | None = None) -> None:
    """Generate all target corpus inputs once."""
    parser = argparse.ArgumentParser(prog="qat-corpus-build")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    options = parser.parse_args(arguments)
    try:
        digest, destination = build_corpus(options.target)
        print(f"corpus\t{digest}\t{destination}")
    except (CorpusError, DeploymentError, ConfigurationError, OSError) as error:
        print(f"qat-corpus-build: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
