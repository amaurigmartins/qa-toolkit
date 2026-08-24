"""Read, inspect, and install the central tool registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

from qa_toolkit.paths import payload_root, toolkit_root

SCHEMA_VERSION: Final = 1
SUPPORTED_HOST: Final = "linux-x86_64"
HEX_SHA256: Final = re.compile(r"[0-9a-f]{64}")


class RegistryError(RuntimeError):
    """Report invalid registry data or a failed tool operation."""


@dataclass(frozen=True)
class Checksum:
    """Describe how an accepted payload is verified."""

    algorithm: str
    value: str


@dataclass(frozen=True)
class Asset:
    """Describe one Linux asset or locked environment member."""

    kind: str
    url: str | None
    archive: str | None
    executables: tuple[str, ...]


@dataclass(frozen=True)
class Tool:
    """One accepted tool record."""

    tool_id: str
    provider: str
    version: str
    source: str
    environment: str
    checksum: Checksum
    asset: Asset
    version_argv: tuple[str, ...]
    version_contains: str


def _closed_keys(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise RegistryError(f"{context}: unknown fields: {names}")


def _required_string(value: Mapping[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise RegistryError(f"{context}: {key} must be a non-empty string")
    return result


def _parse_tool(raw: object, index: int) -> Tool:
    context = f"tools[{index}]"
    if not isinstance(raw, dict):
        raise RegistryError(f"{context}: expected an object")
    _closed_keys(
        raw,
        {
            "id",
            "provider",
            "version",
            "source",
            "environment",
            "checksum",
            "asset",
            "version_argv",
            "version_contains",
        },
        context,
    )

    checksum_raw = raw.get("checksum")
    if not isinstance(checksum_raw, dict):
        raise RegistryError(f"{context}.checksum: expected an object")
    _closed_keys(checksum_raw, {"algorithm", "value"}, f"{context}.checksum")
    checksum = Checksum(
        algorithm=_required_string(checksum_raw, "algorithm", f"{context}.checksum"),
        value=_required_string(checksum_raw, "value", f"{context}.checksum"),
    )
    if checksum.algorithm == "sha256" and not HEX_SHA256.fullmatch(checksum.value):
        raise RegistryError(f"{context}.checksum.value: expected 64 lowercase hexadecimal digits")

    asset_raw = raw.get("asset")
    if not isinstance(asset_raw, dict):
        raise RegistryError(f"{context}.asset: expected an object")
    _closed_keys(asset_raw, {"kind", "url", "archive", "executables"}, f"{context}.asset")
    executable_values = asset_raw.get("executables")
    if not isinstance(executable_values, list) or not all(
        isinstance(item, str) and item for item in executable_values
    ):
        raise RegistryError(f"{context}.asset.executables: expected non-empty strings")
    url_value = asset_raw.get("url")
    archive_value = asset_raw.get("archive")
    if url_value is not None and not isinstance(url_value, str):
        raise RegistryError(f"{context}.asset.url: expected a string or null")
    if archive_value is not None and not isinstance(archive_value, str):
        raise RegistryError(f"{context}.asset.archive: expected a string or null")
    asset = Asset(
        kind=_required_string(asset_raw, "kind", f"{context}.asset"),
        url=url_value,
        archive=archive_value,
        executables=tuple(executable_values),
    )

    argv_value = raw.get("version_argv")
    if not isinstance(argv_value, list) or not all(
        isinstance(item, str) and item for item in argv_value
    ):
        raise RegistryError(f"{context}.version_argv: expected non-empty strings")

    return Tool(
        tool_id=_required_string(raw, "id", context),
        provider=_required_string(raw, "provider", context),
        version=_required_string(raw, "version", context),
        source=_required_string(raw, "source", context),
        environment=_required_string(raw, "environment", context),
        checksum=checksum,
        asset=asset,
        version_argv=tuple(argv_value),
        version_contains=_required_string(raw, "version_contains", context),
    )


def load_registry(root: Path | None = None) -> tuple[Tool, ...]:
    """Load and strictly validate the tracked registry."""
    repository = root or toolkit_root()
    try:
        raw = json.loads((repository / "registry" / "tools.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"cannot read registry/tools.json: {error}") from error
    if not isinstance(raw, dict):
        raise RegistryError("registry: expected an object")
    _closed_keys(raw, {"schema_version", "host", "tools"}, "registry")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RegistryError(f"registry: schema_version must be {SCHEMA_VERSION}")
    if raw.get("host") != SUPPORTED_HOST:
        raise RegistryError(f"registry: host must be {SUPPORTED_HOST}")
    values = raw.get("tools")
    if not isinstance(values, list):
        raise RegistryError("registry.tools: expected an array")
    tools = tuple(_parse_tool(value, index) for index, value in enumerate(values))
    identifiers = [tool.tool_id for tool in tools]
    if len(identifiers) != len(set(identifiers)):
        raise RegistryError("registry.tools: tool IDs must be unique")
    return tools


def select_tools(identifiers: Iterable[str], root: Path | None = None) -> tuple[Tool, ...]:
    """Resolve exact tool IDs, preserving the requested order."""
    tools = {tool.tool_id: tool for tool in load_registry(root)}
    selected: list[Tool] = []
    for identifier in identifiers:
        try:
            selected.append(tools[identifier])
        except KeyError as error:
            raise RegistryError(f"unknown tool: {identifier}") from error
    return tuple(selected)


def executable_path(tool: Tool, root: Path | None = None) -> Path:
    """Return the primary executable expected for a tool."""
    repository = root or toolkit_root()
    executable = tool.asset.executables[0] if tool.asset.executables else tool.tool_id
    if tool.environment == "python":
        return payload_root(repository) / "python" / "bin" / executable
    if tool.environment == "node":
        return payload_root(repository) / "node" / "bin" / executable
    if tool.environment.startswith("julia-"):
        return (
            payload_root(repository)
            / "julia"
            / tool.environment.removeprefix("julia-")
            / "bin"
            / executable
        )
    if tool.environment == "julia":
        return payload_root(repository) / "julia" / "1.12.6" / "bin" / executable
    return payload_root(repository) / tool.tool_id / "bin" / executable


def tool_status(tool: Tool, root: Path | None = None) -> tuple[bool, str]:
    """Return whether the installed primary executable reports the accepted version."""
    repository = root or toolkit_root()
    if tool.environment == "julia":
        return _julia_package_status(tool, repository)
    executable = executable_path(tool, root)
    needs_executable = "{executable}" in tool.version_argv
    if needs_executable and (not executable.is_file() or not os.access(executable, os.X_OK)):
        return False, "missing"
    python = payload_root(root or toolkit_root()) / "python" / "bin" / "python"
    replacements = {"{executable}": str(executable), "{python}": str(python)}
    argv = [replacements.get(item, item) for item in tool.version_argv]
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"execution-error: {error}"
    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        return False, f"execution-error: exit {result.returncode}"
    if tool.version_contains not in output:
        return False, f"version-mismatch: {output.splitlines()[0] if output else 'empty output'}"
    return True, tool.version


def _julia_package_status(tool: Tool, root: Path) -> tuple[bool, str]:
    source = root / "config" / "julia"
    qa = payload_root(root) / "julia" / "qa"
    return _julia_package_status_at(tool, source, qa)


def _julia_package_status_at(tool: Tool, source: Path, qa: Path) -> tuple[bool, str]:
    for minor in ("1.10", "1.12"):
        active = qa / minor
        project = active / "environment" / "Project.toml"
        manifest = active / "environment" / "Manifest.toml"
        expected_manifest = source / "locks" / minor / "Manifest.toml"
        if not project.is_file() or not manifest.is_file():
            return False, f"missing Julia {minor} QA environment"
        if project.read_bytes() != (source / "Project.toml").read_bytes():
            return False, f"Julia {minor} QA project mismatch"
        if manifest.read_bytes() != expected_manifest.read_bytes():
            return False, f"Julia {minor} QA manifest mismatch"
        document = tomllib.loads(manifest.read_text(encoding="utf-8"))
        packages = document.get("deps", {})
        records = (
            packages.get(_julia_package_name(tool.tool_id), [])
            if isinstance(packages, dict)
            else []
        )
        if not isinstance(records, list) or not any(
            isinstance(record, dict) and record.get("version") == tool.version for record in records
        ):
            return False, f"Julia {minor} manifest version mismatch"
        package_root = active / "depot" / "packages" / _julia_package_name(tool.tool_id)
        if not package_root.is_dir() or not any(item.is_dir() for item in package_root.iterdir()):
            return False, f"Julia {minor} package source missing"
    return True, tool.version


def _julia_package_name(identifier: str) -> str:
    return {
        "aqua": "Aqua",
        "explicitimports": "ExplicitImports",
        "juliaformatter": "JuliaFormatter",
    }[identifier]


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310 - registry URLs use reviewed HTTPS sources.
        url, headers={"User-Agent": "qa-toolkit/0.1"}
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,  # noqa: S310
            destination.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
    except (OSError, urllib.error.URLError) as error:
        raise RegistryError(f"download failed: {url}: {error}") from error


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise RegistryError(f"checksum mismatch: expected {expected}, got {actual}")


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def _extract(archive: Path, kind: str, destination: Path, executables: tuple[str, ...]) -> None:
    if kind == "raw":
        if len(executables) != 1:
            raise RegistryError("raw assets must declare exactly one executable")
        target = destination / executables[0]
        shutil.copy2(archive, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return
    if kind in {"tar.gz", "tar.xz"}:
        mode: Literal["r:gz", "r:xz"] = "r:gz" if kind == "tar.gz" else "r:xz"
        with tarfile.open(archive, mode) as tar_bundle:
            tar_members = tar_bundle.getmembers()
            if any(not _safe_member(member.name) for member in tar_members):
                raise RegistryError("archive contains an unsafe path")
            tar_bundle.extractall(destination, members=tar_members, filter="data")
        return
    if kind == "zip":
        with zipfile.ZipFile(archive) as zip_bundle:
            zip_members = zip_bundle.infolist()
            if any(not _safe_member(member.filename) for member in zip_members):
                raise RegistryError("archive contains an unsafe path")
            for member in zip_members:
                target = destination / member.filename
                unix_mode = member.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise RegistryError("archive contains a symbolic link")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        return
    raise RegistryError(f"unsupported archive kind: {kind}")


def _find_executable(payload: Path, name: str) -> Path:
    candidates = [path for path in payload.rglob(name) if path.is_file()]
    if len(candidates) != 1:
        raise RegistryError(f"asset must contain exactly one regular executable named {name}")
    candidate = candidates[0]
    candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return candidate


def _replace_directory(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = staged.parent / f".{target.name}.previous-{uuid.uuid4().hex}"
    moved_previous = False
    try:
        if target.exists() or target.is_symlink():
            os.replace(target, previous)
            moved_previous = True
        os.replace(staged, target)
    except OSError:
        if moved_previous and not target.exists():
            os.replace(previous, target)
        raise
    finally:
        if previous.exists():
            shutil.rmtree(previous)


def _prepare_asset(tool: Tool, work: Path) -> Path:
    if tool.asset.url is None or tool.asset.archive is None:
        raise RegistryError(f"{tool.tool_id}: no downloadable Linux asset")
    download = work / Path(urllib.parse.urlparse(tool.asset.url).path).name
    _download(tool.asset.url, download)
    if tool.checksum.algorithm != "sha256":
        raise RegistryError(f"{tool.tool_id}: downloadable assets require sha256")
    _verify_sha256(download, tool.checksum.value)
    staged = work / "installed"
    payload = staged / "payload"
    binary_directory = staged / "bin"
    payload.mkdir(parents=True)
    binary_directory.mkdir()
    _extract(download, tool.asset.archive, payload, tool.asset.executables)
    for executable_name in tool.asset.executables:
        executable = _find_executable(payload, executable_name)
        relative = os.path.relpath(executable, binary_directory)
        (binary_directory / executable_name).symlink_to(relative)
    valid, detail = tool_status(tool, _staged_root(tool, staged))
    if not valid:
        raise RegistryError(f"{tool.tool_id}: staged version check failed: {detail}")
    return staged


def _install_asset(tool: Tool, root: Path) -> None:
    staging_root = payload_root(root) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{tool.tool_id}-", dir=staging_root))
    try:
        staged = _prepare_asset(tool, work)
        _replace_directory(staged, payload_root(root) / tool.tool_id)
    finally:
        if work.exists():
            shutil.rmtree(work)


def _staged_root(tool: Tool, staged: Path) -> Path:
    """Create a temporary root view that points status checks at *staged*."""
    view = staged.parent / "view"
    (view / "toolkit").mkdir(parents=True, exist_ok=True)
    (view / "toolkit" / tool.tool_id).symlink_to(staged)
    return view


def _environment_view(environment: str, staged: Path) -> Path:
    view = staged.parent / f"view-{environment}"
    toolkit = view / "toolkit"
    toolkit.mkdir(parents=True, exist_ok=True)
    if environment == "python":
        (toolkit / "python").symlink_to(staged)
    elif environment == "node":
        (toolkit / "node").symlink_to(staged)
    elif environment.startswith("julia-"):
        julia = toolkit / "julia"
        julia.mkdir()
        (julia / environment.removeprefix("julia-")).symlink_to(staged)
    else:
        raise RegistryError(f"unsupported staged environment: {environment}")
    return view


def _run(argv: list[str], *, environment: Mapping[str, str] | None = None) -> None:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=1200,
            shell=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RegistryError(f"command failed to execute: {argv[0]}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RegistryError(f"command failed with exit {result.returncode}: {detail}")


def _install_python_environment(root: Path) -> None:
    uv = executable_path(select_tools(["uv"], root)[0], root)
    if not uv.is_file():
        raise RegistryError("python environment requires the accepted uv installation")
    staging_root = payload_root(root) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="python-", dir=staging_root))
    staged = work / "environment"
    environment = os.environ.copy()
    environment.update(
        {
            "UV_CACHE_DIR": str(payload_root(root) / ".cache" / "uv"),
            "UV_LINK_MODE": "copy",
            "UV_NO_PROGRESS": "1",
            "UV_PROJECT_ENVIRONMENT": str(staged),
            "UV_PYTHON_INSTALL_DIR": str(payload_root(root) / "python-runtimes"),
        }
    )
    try:
        _run([str(uv), "python", "install", "3.11.15"], environment=environment)
        _run(
            [str(uv), "venv", "--python", "3.11.15", "--relocatable", str(staged)],
            environment=environment,
        )
        _run(
            [
                str(uv),
                "sync",
                "--frozen",
                "--all-groups",
                "--project",
                str(root),
            ],
            environment=environment,
        )
        view = _environment_view("python", staged)
        for tool in load_registry(root):
            if tool.environment == "python" and tool.asset.executables:
                valid, detail = tool_status(tool, view)
                if not valid:
                    raise RegistryError(f"{tool.tool_id}: staged version check failed: {detail}")
        _replace_directory(staged, payload_root(root) / "python")
    finally:
        if work.exists():
            shutil.rmtree(work)


def _install_node_environment(root: Path) -> None:
    node, cspell = select_tools(["node", "cspell"], root)
    if node.asset.url is None or node.asset.archive is None:
        raise RegistryError("node: no downloadable Linux asset")
    staging_root = payload_root(root) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="node-", dir=staging_root))
    try:
        download = work / Path(urllib.parse.urlparse(node.asset.url).path).name
        _download(node.asset.url, download)
        _verify_sha256(download, node.checksum.value)
        expanded = work / "expanded"
        expanded.mkdir()
        _extract(download, node.asset.archive, expanded, node.asset.executables)
        roots = [path for path in expanded.iterdir() if (path / "bin" / "node").is_file()]
        if len(roots) != 1:
            raise RegistryError("node asset must contain exactly one runtime root")
        staged = work / "environment"
        os.replace(roots[0], staged)
        shutil.copy2(root / "config" / "cspell" / "package.json", staged / "package.json")
        shutil.copy2(root / "config" / "cspell" / "package-lock.json", staged / "package-lock.json")
        environment = os.environ.copy()
        environment["npm_config_cache"] = str(payload_root(root) / ".cache" / "npm")
        npm_cli = staged / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"
        _run(
            [
                str(staged / "bin" / "node"),
                str(npm_cli),
                "ci",
                "--ignore-scripts",
                "--prefix",
                str(staged),
            ],
            environment=environment,
        )
        cspell_link = staged / "bin" / "cspell"
        if not cspell_link.exists():
            cspell_link.symlink_to("../node_modules/.bin/cspell")
        view = _environment_view("node", staged)
        for tool in (node, cspell):
            valid, detail = tool_status(tool, view)
            if not valid:
                raise RegistryError(f"{tool.tool_id}: staged version check failed: {detail}")
        _replace_directory(staged, payload_root(root) / "node")
    finally:
        if work.exists():
            shutil.rmtree(work)


def _install_julia_runtime(tool: Tool, root: Path) -> None:
    if tool.asset.url is None or tool.asset.archive is None:
        raise RegistryError(f"{tool.tool_id}: no downloadable Linux asset")
    staging_root = payload_root(root) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{tool.tool_id}-", dir=staging_root))
    try:
        download = work / Path(urllib.parse.urlparse(tool.asset.url).path).name
        _download(tool.asset.url, download)
        _verify_sha256(download, tool.checksum.value)
        expanded = work / "expanded"
        expanded.mkdir()
        _extract(download, tool.asset.archive, expanded, tool.asset.executables)
        roots = [path for path in expanded.iterdir() if (path / "bin" / "julia").is_file()]
        if len(roots) != 1:
            raise RegistryError("Julia asset must contain exactly one runtime root")
        staged = work / "runtime"
        os.replace(roots[0], staged)
        view = _environment_view(tool.environment, staged)
        valid, detail = tool_status(tool, view)
        if not valid:
            raise RegistryError(f"{tool.tool_id}: staged version check failed: {detail}")
        target = payload_root(root) / "julia" / tool.version
        _replace_directory(staged, target)
    finally:
        if work.exists():
            shutil.rmtree(work)


def _install_julia_qa(root: Path) -> None:
    runtimes = select_tools(["julia-1.10.11", "julia-1.12.6"], root)
    if not all(tool_status(tool, root)[0] for tool in runtimes):
        raise RegistryError("Julia QA packages require both accepted runtimes")
    staging_root = payload_root(root) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="julia-qa-", dir=staging_root))
    staged = work / "qa"
    try:
        for runtime, minor in zip(runtimes, ("1.10", "1.12"), strict=True):
            environment_root = staged / minor
            project = environment_root / "environment"
            depot = environment_root / "depot"
            project.mkdir(parents=True)
            depot.mkdir()
            shutil.copy2(root / "config/julia/Project.toml", project / "Project.toml")
            shutil.copy2(
                root / "config" / "julia" / "locks" / minor / "Manifest.toml",
                project / "Manifest.toml",
            )
            process_environment = os.environ.copy()
            process_environment.update(
                {
                    "JULIA_DEPOT_PATH": str(depot),
                    "JULIA_HISTORY": os.devnull,
                    "JULIA_PKG_PRECOMPILE_AUTO": "0",
                }
            )
            _run(
                [
                    str(executable_path(runtime, root)),
                    "--startup-file=no",
                    "--history-file=no",
                    "--color=no",
                    f"--project={project}",
                    str(root / "config/julia/scripts/instantiate.jl"),
                ],
                environment=process_environment,
            )
        for tool in select_tools(["juliaformatter", "aqua", "explicitimports"], root):
            valid, detail = _julia_package_status_at(tool, root / "config/julia", staged)
            if not valid:
                raise RegistryError(f"{tool.tool_id}: staged Julia QA check failed: {detail}")
        _replace_directory(staged, payload_root(root) / "julia" / "qa")
    finally:
        if work.exists():
            shutil.rmtree(work)


def fetch_environment(environment: str, root: Path | None = None, *, force: bool = False) -> None:
    """Install one shared locked tool environment atomically."""
    repository = root or toolkit_root()
    tools = tuple(tool for tool in load_registry(repository) if tool.environment == environment)
    current = bool(tools) and all(tool_status(tool, repository)[0] for tool in tools)
    if current and not force:
        return
    if environment == "python":
        _install_python_environment(repository)
    elif environment == "node":
        _install_node_environment(repository)
    elif environment.startswith("julia-"):
        runtime = next((tool for tool in tools if tool.tool_id == environment), None)
        if runtime is None:
            raise RegistryError(f"missing runtime record for {environment}")
        _install_julia_runtime(runtime, repository)
    elif environment == "julia":
        _install_julia_qa(repository)
    else:
        raise RegistryError(f"unsupported environment: {environment}")


def fetch_tool(tool: Tool, root: Path | None = None, *, force: bool = False) -> None:
    """Install one verified standalone asset below the repository payload directory."""
    repository = root or toolkit_root()
    valid, _ = tool_status(tool, repository)
    if valid and not force:
        return
    if tool.environment == "standalone":
        _install_asset(tool, repository)
        return
    if tool.environment == "julia":
        fetch_environment("julia", repository, force=force)
        return
    fetch_environment(tool.environment, repository, force=force)


def update_standalone(
    identifier: str,
    version: str,
    url: str,
    checksum: str,
    archive: str,
    version_contains: str | None = None,
    root: Path | None = None,
) -> None:
    """Verify a proposed standalone release, then atomically accept and activate it."""
    repository = root or toolkit_root()
    current = select_tools([identifier], repository)[0]
    if current.environment != "standalone":
        raise RegistryError("tool updates currently accept standalone registry entries only")
    if not version:
        raise RegistryError("version must be non-empty")
    if not HEX_SHA256.fullmatch(checksum):
        raise RegistryError("checksum must contain 64 lowercase hexadecimal digits")
    if archive not in {"raw", "tar.gz", "tar.xz", "zip"}:
        raise RegistryError(f"unsupported archive kind: {archive}")
    proposed = Tool(
        tool_id=current.tool_id,
        provider=current.provider,
        version=version,
        source=current.source,
        environment=current.environment,
        checksum=Checksum("sha256", checksum),
        asset=Asset(archive, url, archive, current.asset.executables),
        version_argv=current.version_argv,
        version_contains=version_contains or version,
    )

    registry_path = repository / "registry" / "tools.json"
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    records = raw["tools"]
    record = next(item for item in records if item["id"] == identifier)
    record["version"] = version
    record["checksum"] = {"algorithm": "sha256", "value": checksum}
    record["asset"]["kind"] = archive
    record["asset"]["archive"] = archive
    record["asset"]["url"] = url
    record["version_contains"] = version_contains or version

    staging_root = payload_root(repository) / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"update-{identifier}-", dir=staging_root))
    registry_temporary = registry_path.with_name(f".{registry_path.name}.{uuid.uuid4().hex}")
    target = payload_root(repository) / identifier
    previous = work / "previous"
    moved_previous = False
    activated = False
    try:
        staged = _prepare_asset(proposed, work)
        registry_temporary.write_text(
            f"{json.dumps(raw, indent=2, sort_keys=False)}\n", encoding="utf-8"
        )
        if target.exists():
            os.replace(target, previous)
            moved_previous = True
        os.replace(staged, target)
        activated = True
        try:
            os.replace(registry_temporary, registry_path)
        except OSError:
            shutil.rmtree(target)
            activated = False
            if moved_previous:
                os.replace(previous, target)
                moved_previous = False
            raise
        if previous.exists():
            shutil.rmtree(previous)
    finally:
        if activated and previous.exists():
            shutil.rmtree(previous)
        if registry_temporary.exists():
            registry_temporary.unlink()
        if work.exists():
            shutil.rmtree(work)


def list_rows(root: Path | None = None) -> tuple[tuple[str, str, str], ...]:
    """Return registry rows for stable text or JSON display."""
    return tuple((tool.tool_id, tool.version, tool.environment) for tool in load_registry(root))
