"""Run qualified Julia tools against private tracked-source copies."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

from qa_toolkit.deployment import DeploymentError, resolve_target, tracked_entries
from qa_toolkit.paths import payload_root, toolkit_root

RUNTIMES = ("1.10.11", "1.12.6")
OPERATIONS = ("format", "tests", "aqua", "explicit-imports", "vulnerabilities")


class JuliaToolError(RuntimeError):
    """Report invalid Julia inputs or a failed supporting command."""


@dataclass(frozen=True, slots=True)
class JuliaProject:
    """One tracked root or nested Julia project."""

    directory: PurePosixPath
    name: str | None
    loadable: bool
    manifest: PurePosixPath | None
    has_tests: bool


def _tracked_snapshot(target: Path, snapshot: Path) -> tuple[str, ...]:
    copied: list[str] = []
    for mode, relative in tracked_entries(target):
        if mode not in {"100644", "100755"}:
            raise JuliaToolError(f"Julia snapshot refuses non-regular tracked input: {relative}")
        source = target / relative
        source_mode = source.lstat().st_mode
        if not stat.S_ISREG(source_mode):
            raise JuliaToolError(f"Julia snapshot input is not regular: {relative}")
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if mode == "100755" else 0o644)
        copied.append(relative)
    return tuple(sorted(copied))


def discover_projects(snapshot: Path, copied: tuple[str, ...]) -> tuple[JuliaProject, ...]:
    """Discover valid root and nested Julia projects in lexical order."""
    copied_set = set(copied)
    projects: list[JuliaProject] = []
    for relative in sorted(path for path in copied if PurePosixPath(path).name == "Project.toml"):
        project_path = snapshot / relative
        if project_path.stat().st_size > 262_144:
            raise JuliaToolError(f"Julia project is too large: {relative}")
        try:
            document = tomllib.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            raise JuliaToolError(f"cannot parse Julia project {relative}: {error}") from error
        directory = PurePosixPath(relative).parent
        if directory == PurePosixPath("."):
            directory = PurePosixPath()
        name = _package_identity(document, relative)
        entry = directory / "src" / f"{name}.jl" if name is not None else None
        manifest = directory / "Manifest.toml"
        tests = directory / "test" / "runtests.jl"
        projects.append(
            JuliaProject(
                directory,
                name,
                entry is not None and entry.as_posix() in copied_set,
                manifest if manifest.as_posix() in copied_set else None,
                tests.as_posix() in copied_set,
            )
        )
    return tuple(projects)


def _package_identity(document: dict[str, object], relative: str) -> str | None:
    values = tuple(document.get(key) for key in ("name", "uuid", "version"))
    if values == (None, None, None):
        return None
    name, uuid, version = values
    if not isinstance(name, str) or not name or not name.replace("_", "a").isalnum():
        raise JuliaToolError(f"Julia project has an invalid package name: {relative}")
    try:
        normalized_uuid = str(UUID(uuid)) if isinstance(uuid, str) else ""
    except ValueError:
        normalized_uuid = ""
    if normalized_uuid != uuid:
        raise JuliaToolError(f"Julia project has an invalid package UUID: {relative}")
    if not isinstance(version, str) or not version or len(version) > 128:
        raise JuliaToolError(f"Julia project has an invalid package version: {relative}")
    return name


def _eligible(projects: tuple[JuliaProject, ...], operation: str) -> tuple[JuliaProject, ...]:
    selected: list[JuliaProject] = []
    for project in projects:
        label = project.directory.as_posix() or "."
        if project.has_tests and not project.loadable:
            raise JuliaToolError(f"Julia tests require a loadable package: {label}")
        if not project.loadable or (operation == "tests" and not project.has_tests):
            continue
        selected.append(project)
    return tuple(selected)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dependency_identity(root: Path) -> tuple[str, str | None]:
    manifest = root / "Manifest.toml"
    return _digest(root / "Project.toml"), _digest(manifest) if manifest.is_file() else None


def _environment(
    run_root: Path, root: Path, runtime: str, target: Path | None = None
) -> dict[str, str]:
    minor = ".".join(runtime.split(".")[:2])
    writable_depot = (
        target / ".git" / "qat" / "cache" / "julia" / runtime / "depot"
        if target is not None
        else run_root / "depot"
    )
    home = run_root / "home"
    cache = run_root / "cache"
    for directory in (writable_depot, home, cache):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    central_depot = payload_root(root) / "julia" / "qa" / minor / "depot"
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "JULIA_DEPOT_PATH": os.pathsep.join((str(writable_depot), str(central_depot))),
            "JULIA_HISTORY": os.devnull,
            "JULIA_PKG_PRECOMPILE_AUTO": "0",
            "XDG_CACHE_HOME": str(cache),
        }
    )
    return environment


def _invoke(
    argv: tuple[str, ...], cwd: Path, environment: dict[str, str], run_root: Path, timeout: int
) -> int:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise JuliaToolError(f"cannot execute Julia command: {error}") from error
    for stream, destination in ((completed.stdout, sys.stdout), (completed.stderr, sys.stderr)):
        stable = stream.replace(str(run_root), "<julia-run>")
        if stable:
            print(stable, end="" if stable.endswith("\n") else "\n", file=destination)
    return completed.returncode


def _julia_argv(
    executable: Path, project: Path, script: Path, *arguments: str | Path
) -> tuple[str, ...]:
    return (
        str(executable),
        "--startup-file=no",
        "--history-file=no",
        "--color=no",
        f"--project={project}",
        str(script),
        *(str(argument) for argument in arguments),
    )


def _run_native(
    operation: str,
    runtime: str,
    target: Path,
    root: Path,
    test_arguments: tuple[str, ...] = (),
) -> int:
    if test_arguments and operation != "tests":
        raise JuliaToolError("--test-arg is valid only for the tests operation")
    executable = payload_root(root) / "julia" / runtime / "bin" / "julia"
    if not executable.is_file():
        raise JuliaToolError(f"missing accepted Julia runtime: {runtime}")
    minor = ".".join(runtime.split(".")[:2])
    qa_project = payload_root(root) / "julia" / "qa" / minor / "environment"
    scripts = root / "config" / "julia" / "scripts"
    with tempfile.TemporaryDirectory(prefix="qat-julia-") as raw_run:
        run_root = Path(raw_run)
        run_root.chmod(0o700)
        snapshot = run_root / "source"
        snapshot.mkdir(mode=0o700)
        copied = _tracked_snapshot(target, snapshot)
        if ".JuliaFormatter.toml" not in copied:
            shutil.copy2(
                root / "config/julia/.JuliaFormatter.toml", snapshot / ".JuliaFormatter.toml"
            )
        projects = discover_projects(snapshot, copied)
        environment = _environment(run_root, root, runtime, target)
        if operation == "format":
            code = _invoke(
                _julia_argv(
                    executable,
                    qa_project,
                    scripts / "format_check.jl",
                    snapshot,
                    "2.12.5",
                ),
                snapshot,
                environment,
                run_root,
                300,
            )
            return 0 if code == 0 else 1
        for project in _eligible(projects, operation):
            project_root = snapshot.joinpath(*project.directory.parts)
            before = _dependency_identity(project_root)
            instantiate = _invoke(
                _julia_argv(
                    executable,
                    project_root,
                    scripts / "instantiate.jl",
                ),
                project_root,
                environment,
                run_root,
                900,
            )
            if instantiate != 0:
                return 2
            resolved = _dependency_identity(project_root)
            if resolved[0] != before[0] or (project.manifest is not None and resolved != before):
                raise JuliaToolError(
                    f"Julia command modified copied dependency files: {project_root}"
                )
            if project.manifest is None:
                if resolved[1] is None:
                    raise JuliaToolError(f"Julia did not resolve a manifest for: {project_root}")
                label = project.directory.as_posix() or "."
                print(f"julia-resolved-manifest: {label} sha256={resolved[1]}")
            script = {
                "tests": "test_project.jl",
                "aqua": "aqua_check.jl",
                "explicit-imports": "explicit_imports_check.jl",
            }[operation]
            active_project = project_root if operation == "tests" else qa_project
            arguments: tuple[str | Path, ...] = (
                test_arguments if operation == "tests" else (project_root,)
            )
            code = _invoke(
                _julia_argv(executable, active_project, scripts / script, *arguments),
                project_root,
                environment,
                run_root,
                1200,
            )
            if _dependency_identity(project_root) != resolved:
                raise JuliaToolError(
                    f"Julia command modified copied dependency files: {project_root}"
                )
            if code != 0:
                return 1
        return 0


def _run_trivy(target: Path, root: Path) -> int:
    executable = payload_root(root) / "trivy" / "bin" / "trivy"
    if not executable.is_file():
        raise JuliaToolError("missing accepted Trivy executable")
    with tempfile.TemporaryDirectory(prefix="qat-trivy-julia-") as raw_run:
        run_root = Path(raw_run)
        source = run_root / "source"
        scan = run_root / "scan"
        source.mkdir()
        scan.mkdir()
        copied = _tracked_snapshot(target, source)
        projects = discover_projects(source, copied)
        pairs = [
            (project.directory, project.manifest)
            for project in projects
            if project.manifest is not None
        ]
        if not pairs:
            print("julia-vulnerabilities: no tracked manifests")
            return 0
        for index, (directory, manifest) in enumerate(pairs):
            staged = scan / f"{index:04d}"
            staged.mkdir()
            shutil.copy2(
                source.joinpath(*directory.parts) / "Project.toml", staged / "Project.toml"
            )
            shutil.copy2(source.joinpath(*manifest.parts), staged / "Manifest.toml")
        cache = target / ".git" / "qat" / "trivy-cache"
        cache.mkdir(parents=True, exist_ok=True)
        code = _invoke(
            (
                str(executable),
                "--cache-dir",
                str(cache),
                "--quiet",
                "filesystem",
                "--scanners",
                "vuln",
                "--pkg-types",
                "library",
                "--exit-code",
                "1",
                "--no-progress",
                "--disable-telemetry",
                "--skip-version-check",
                str(scan),
            ),
            run_root,
            os.environ.copy(),
            run_root,
            600,
        )
        return code if code in {0, 1} else 2


def main(arguments: Sequence[str] | None = None) -> None:
    """Run one Julia operation with a selected exact runtime."""
    parser = argparse.ArgumentParser(prog="qat-julia")
    parser.add_argument("operation", choices=OPERATIONS)
    parser.add_argument("--runtime", choices=RUNTIMES)
    parser.add_argument("--test-arg", action="append", default=[])
    parser.add_argument("--target", type=Path, default=Path.cwd())
    options = parser.parse_args(arguments)
    try:
        target = resolve_target(options.target)
        if options.operation == "vulnerabilities":
            code = _run_trivy(target, toolkit_root())
        else:
            if options.runtime is None:
                raise JuliaToolError("native Julia operations require --runtime")
            code = _run_native(
                options.operation,
                options.runtime,
                target,
                toolkit_root(),
                tuple(options.test_arg),
            )
    except (
        JuliaToolError,
        DeploymentError,
        OSError,
        subprocess.CalledProcessError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(f"qat-julia: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
