"""Render Mermaid source directories to PDF with a pinned container image."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from qa_toolkit.paths import toolkit_root


class MermaidError(RuntimeError):
    """Report invalid renderer inputs or a failed container invocation."""


@dataclass(frozen=True, slots=True)
class MermaidConfiguration:
    """Pinned Mermaid CLI container selection."""

    version: str
    image: str


@dataclass(frozen=True, slots=True)
class RenderSummary:
    """Counts and output location for one rendering pass."""

    sources: int
    rendered: int
    current: int
    target: Path


def _configuration(root: Path | None = None) -> MermaidConfiguration:
    path = (root or toolkit_root()) / "config" / "mermaid.toml"
    try:
        document: Any = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise MermaidError(f"cannot read {path}: {error}") from error
    if not isinstance(document, dict) or set(document) != {"version", "image"}:
        raise MermaidError("config/mermaid.toml must contain only version and image")
    version = document.get("version")
    image = document.get("image")
    if not isinstance(version, str) or not version:
        raise MermaidError("Mermaid CLI version must be a non-empty string")
    marker = f":{version}@sha256:"
    if (
        not isinstance(image, str)
        or marker not in image
        or len(image.rsplit(marker, maxsplit=1)[1]) != 64
    ):
        raise MermaidError("Mermaid CLI image must bind the declared version to a SHA-256 digest")
    return MermaidConfiguration(version, image)


def _select_engine(requested: str) -> str:
    candidates = ("podman", "docker") if requested == "auto" else (requested,)
    for candidate in candidates:
        if shutil.which(candidate) is not None:
            return candidate
    if requested == "auto":
        raise MermaidError("neither Podman nor Docker is available")
    raise MermaidError(f"container engine not found: {requested}")


def _paths(source: Path, target: Path | None) -> tuple[Path, Path]:
    try:
        source_root = source.expanduser().resolve(strict=True)
    except OSError as error:
        raise MermaidError(f"cannot resolve source directory {source}: {error}") from error
    if not source_root.is_dir():
        raise MermaidError(f"source is not a directory: {source_root}")
    target_root = (
        target.expanduser().resolve(strict=False)
        if target is not None
        else source_root / "mermaid-pdf"
    )
    if target_root == source_root:
        raise MermaidError("target must differ from the source directory")
    if target_root in source_root.parents:
        raise MermaidError("target must not contain the source directory")
    if target_root.exists() and not target_root.is_dir():
        raise MermaidError(f"target is not a directory: {target_root}")
    return source_root, target_root


def _sources(source: Path, target: Path) -> tuple[Path, ...]:
    selected: list[Path] = []
    for candidate in source.rglob("*.mmd"):
        if target == candidate or target in candidate.parents:
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise MermaidError(f"refusing irregular Mermaid source: {candidate}")
        selected.append(candidate)
    if not selected:
        raise MermaidError(f"no .mmd files found under {source}")
    return tuple(sorted(selected))


def _signature(source: Path, configuration: MermaidConfiguration) -> str:
    digest = hashlib.sha256()
    digest.update(configuration.image.encode("utf-8"))
    digest.update(b"\0pdf\0transparent\0fit\0")
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _container_argv(
    engine: str,
    image: str,
    source: Path,
    target: Path,
    relative: Path,
    output_relative: Path,
) -> tuple[str, ...]:
    arguments = [engine, "run", "--rm", "--network", "none", "--workdir", "/data/source"]
    if engine == "podman":
        arguments.extend(
            (
                "--userns",
                "keep-id",
                "--user",
                str(os.getuid()),
                "--volume",
                f"{source}:/data/source:ro,z",
                "--volume",
                f"{target}:/data/target:rw,z",
            )
        )
    else:
        arguments.extend(
            (
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--volume",
                f"{source}:/data/source:ro",
                "--volume",
                f"{target}:/data/target:rw",
            )
        )
    input_path = PurePosixPath("/data/source") / PurePosixPath(relative.as_posix())
    output_path = PurePosixPath("/data/target") / PurePosixPath(output_relative.as_posix())
    arguments.extend(
        (image, "-i", str(input_path), "-o", str(output_path), "-b", "transparent", "-f")
    )
    return tuple(arguments)


def _run_container(
    engine: str,
    configuration: MermaidConfiguration,
    source_root: Path,
    target_root: Path,
    relative: Path,
    partial_relative: Path,
    timeout: int,
) -> None:
    argv = _container_argv(
        engine,
        configuration.image,
        source_root,
        target_root,
        relative,
        partial_relative,
    )
    try:
        completed = subprocess.run(
            list(argv),
            timeout=timeout,
            text=True,
            check=False,
            capture_output=True,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MermaidError(f"cannot render {relative}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise MermaidError(
            f"Mermaid CLI failed for {relative} with exit {completed.returncode}: {detail}"
        )


def _write_stamp(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_mermaid(
    source: Path,
    target: Path | None = None,
    *,
    engine: str = "auto",
    force: bool = False,
    timeout: int = 300,
    root: Path | None = None,
) -> RenderSummary:
    """Render every regular ``.mmd`` source below one directory."""
    if timeout <= 0:
        raise MermaidError("timeout must be positive")
    configuration = _configuration(root)
    source_root, target_root = _paths(source, target)
    sources = _sources(source_root, target_root)
    selected_engine = _select_engine(engine)
    target_root.mkdir(parents=True, exist_ok=True)
    rendered = 0
    current = 0
    for source_file in sources:
        relative = source_file.relative_to(source_root)
        output_relative = relative.with_suffix(".pdf")
        output = target_root / output_relative
        stamp = target_root / ".qat-mermaid" / output_relative.with_suffix(".sha256")
        signature = _signature(source_file, configuration)
        if not force and output.is_file() and stamp.is_file():
            try:
                if stamp.read_text(encoding="utf-8").strip() == signature:
                    current += 1
                    continue
            except OSError:
                pass
        output.parent.mkdir(parents=True, exist_ok=True)
        partial_relative = output_relative.with_name(
            f".{output_relative.stem}.{os.getpid()}.partial.pdf"
        )
        partial = target_root / partial_relative
        try:
            _run_container(
                selected_engine,
                configuration,
                source_root,
                target_root,
                relative,
                partial_relative,
                timeout,
            )
            if not partial.is_file():
                raise MermaidError(f"Mermaid CLI produced no PDF for {relative}")
            os.replace(partial, output)
            _write_stamp(stamp, signature)
            rendered += 1
        finally:
            if partial.exists():
                partial.unlink()
    return RenderSummary(len(sources), rendered, current, target_root)


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the optional Mermaid PDF renderer."""
    parser = argparse.ArgumentParser(prog="qat-docs-mermaid")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--engine", choices=("auto", "podman", "docker"), default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    options = parser.parse_args(arguments)
    try:
        summary = render_mermaid(
            options.source,
            options.target,
            engine=options.engine,
            force=options.force,
            timeout=options.timeout,
        )
    except MermaidError as error:
        print(f"qat-docs-mermaid: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    print(
        f"mermaid-pdf\tsources={summary.sources}\trendered={summary.rendered}"
        f"\tcurrent={summary.current}\ttarget={summary.target}"
    )


if __name__ == "__main__":
    main()
