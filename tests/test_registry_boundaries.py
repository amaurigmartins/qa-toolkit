"""Boundary tests for registry parsing, archives, and environment installers."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from test_registry import _record, _write_registry

from qa_toolkit import registry
from qa_toolkit.registry import Asset, Checksum, RegistryError, Tool


def _tool(
    identifier: str = "sample",
    *,
    environment: str = "standalone",
    archive: str | None = "raw",
    url: str | None = "https://example.invalid/sample",
    executables: tuple[str, ...] = ("sample",),
) -> Tool:
    return Tool(
        identifier,
        "fixture",
        "1.2.3",
        "https://example.invalid/source",
        environment,
        Checksum("sha256", "0" * 64),
        Asset(archive or "none", url, archive, executables),
        ("{executable}", "--version"),
        "1.2.3",
    )


class RegistryParsingTests(unittest.TestCase):
    def test_tool_records_reject_malformed_nested_values(self) -> None:
        base = _record("https://example.invalid/sample", "0" * 64)
        cases: tuple[tuple[str, object], ...] = (
            ("record", []),
            ("checksum", "bad"),
            ("checksum_field", {"algorithm": "sha256", "value": "bad"}),
            ("asset", "bad"),
            ("executables", [""]),
            ("url", 1),
            ("archive", 1),
            ("argv", [""]),
            ("required", ""),
        )
        for name, value in cases:
            raw: object = json.loads(json.dumps(base))
            if name == "record":
                raw = value
            elif name == "checksum" or name == "checksum_field":
                raw["checksum"] = value  # type: ignore[index]
            elif name == "asset":
                raw["asset"] = value  # type: ignore[index]
            elif name in {"executables", "url", "archive"}:
                raw["asset"][name] = value  # type: ignore[index]
            elif name == "argv":
                raw["version_argv"] = value  # type: ignore[index]
            else:
                raw["provider"] = value  # type: ignore[index]
            with self.subTest(name=name), self.assertRaises(RegistryError):
                registry._parse_tool(raw, 0)

    def test_registry_document_and_selection_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "registry/tools.json"
            path.parent.mkdir()
            malformed: tuple[object, ...] = (
                [],
                {"schema_version": 2, "host": "linux-x86_64", "tools": []},
                {"schema_version": 1, "host": "other", "tools": []},
                {"schema_version": 1, "host": "linux-x86_64", "tools": {}},
            )
            for document in malformed:
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(document=document), self.assertRaises(RegistryError):
                    registry.load_registry(root)
            record = _record("https://example.invalid/sample", "0" * 64)
            document = {
                "schema_version": 1,
                "host": "linux-x86_64",
                "tools": [record, record],
            }
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "unique"):
                registry.load_registry(root)
            _write_registry(root, record)
            with self.assertRaisesRegex(RegistryError, "unknown tool"):
                registry.select_tools(["missing"], root)
            path.write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "cannot read"):
                registry.load_registry(root)

    def test_executable_paths_cover_every_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            expected = {
                "python": root / "toolkit/python/bin/sample",
                "node": root / "toolkit/node/bin/sample",
                "julia-1.10.11": root / "toolkit/julia/1.10.11/bin/sample",
                "julia": root / "toolkit/julia/1.12.6/bin/sample",
                "standalone": root / "toolkit/sample/bin/sample",
            }
            for environment, path in expected.items():
                with self.subTest(environment=environment):
                    self.assertEqual(
                        registry.executable_path(_tool(environment=environment), root), path
                    )


class RegistryStatusTests(unittest.TestCase):
    def test_process_status_classifies_missing_errors_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tool = _tool()
            self.assertEqual(registry.tool_status(tool, root), (False, "missing"))
            executable = registry.executable_path(tool, root)
            executable.parent.mkdir(parents=True)
            executable.write_text("fixture", encoding="utf-8")
            executable.chmod(0o755)
            cases = (
                (OSError("no"), "execution-error"),
                (subprocess.CompletedProcess([], 2, "", "bad"), "exit 2"),
                (subprocess.CompletedProcess([], 0, "other", ""), "version-mismatch"),
                (subprocess.CompletedProcess([], 0, "sample 1.2.3", ""), "1.2.3"),
            )
            for result, expected in cases:
                with (
                    self.subTest(expected=expected),
                    patch(
                        "qa_toolkit.registry.subprocess.run",
                        side_effect=result if isinstance(result, Exception) else None,
                        return_value=result if not isinstance(result, Exception) else None,
                    ),
                ):
                    current, detail = registry.tool_status(tool, root)
                self.assertEqual(current, expected == "1.2.3")
                self.assertIn(expected, detail)

    def test_julia_package_status_checks_both_locked_environments(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "config"
            qa = root / "qa"
            tool = _tool("aqua", environment="julia", executables=())
            self.assertIn("missing", registry._julia_package_status_at(tool, source, qa)[1])
            for minor in ("1.10", "1.12"):
                active = qa / minor
                environment = active / "environment"
                lock = source / "locks" / minor
                package = active / "depot/packages/Aqua/hash"
                environment.mkdir(parents=True)
                lock.mkdir(parents=True)
                package.mkdir(parents=True)
                project = "[deps]\n"
                manifest = '[[deps.Aqua]]\nversion = "1.2.3"\n'
                (source / "Project.toml").parent.mkdir(parents=True, exist_ok=True)
                (source / "Project.toml").write_text(project, encoding="utf-8")
                (environment / "Project.toml").write_text(project, encoding="utf-8")
                (environment / "Manifest.toml").write_text(manifest, encoding="utf-8")
                (lock / "Manifest.toml").write_text(manifest, encoding="utf-8")
            self.assertEqual(registry._julia_package_status_at(tool, source, qa), (True, "1.2.3"))
            (qa / "1.10/environment/Project.toml").write_text("bad", encoding="utf-8")
            self.assertIn(
                "project mismatch", registry._julia_package_status_at(tool, source, qa)[1]
            )
            (qa / "1.10/environment/Project.toml").write_text("[deps]\n", encoding="utf-8")
            (qa / "1.10/environment/Manifest.toml").write_text("[deps]\n", encoding="utf-8")
            self.assertIn(
                "manifest mismatch", registry._julia_package_status_at(tool, source, qa)[1]
            )


class RegistryArchiveTests(unittest.TestCase):
    def test_download_checksum_and_safe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "download"
            with patch(
                "qa_toolkit.registry.urllib.request.urlopen", return_value=io.BytesIO(b"data")
            ):
                registry._download("https://example.invalid/data", destination)
            self.assertEqual(destination.read_bytes(), b"data")
            digest = hashlib.sha256(b"data").hexdigest()
            registry._verify_sha256(destination, digest)
            with self.assertRaisesRegex(RegistryError, "checksum mismatch"):
                registry._verify_sha256(destination, "0" * 64)
            with (
                patch("qa_toolkit.registry.urllib.request.urlopen", side_effect=OSError("offline")),
                self.assertRaisesRegex(RegistryError, "download failed"),
            ):
                registry._download("https://example.invalid/data", destination)
            self.assertTrue(registry._safe_member("directory/file"))
            self.assertFalse(registry._safe_member("../file"))
            self.assertFalse(registry._safe_member("/file"))

    def test_raw_tar_and_zip_extraction_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.write_bytes(b"tool")
            raw_destination = root / "raw"
            raw_destination.mkdir()
            registry._extract(source, "raw", raw_destination, ("tool",))
            self.assertTrue(os.access(raw_destination / "tool", os.X_OK))
            with self.assertRaisesRegex(RegistryError, "exactly one"):
                registry._extract(source, "raw", raw_destination, ())

            archives: tuple[tuple[str, Literal["w:gz", "w:xz"], str], ...] = (
                ("tar.gz", "w:gz", "tgz"),
                ("tar.xz", "w:xz", "txz"),
            )
            for kind, mode, suffix in archives:
                archive = root / f"bundle.{suffix}"
                with tarfile.open(archive, mode) as bundle:
                    bundle.add(source, arcname="nested/tool")
                destination = root / kind
                destination.mkdir()
                registry._extract(archive, kind, destination, ("tool",))
                self.assertEqual((destination / "nested/tool").read_bytes(), b"tool")

            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("nested/", b"")
                bundle.writestr("nested/tool", b"tool")
            destination = root / "zip"
            destination.mkdir()
            registry._extract(archive, "zip", destination, ("tool",))
            self.assertEqual((destination / "nested/tool").read_bytes(), b"tool")
            with self.assertRaisesRegex(RegistryError, "unsupported"):
                registry._extract(source, "rar", destination, ("tool",))

    def test_archives_reject_unsafe_paths_and_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tar_path = root / "unsafe.tar.gz"
            info = tarfile.TarInfo("../escape")
            info.size = 1
            with tarfile.open(tar_path, "w:gz") as bundle:
                bundle.addfile(info, io.BytesIO(b"x"))
            destination = root / "tar"
            destination.mkdir()
            with self.assertRaisesRegex(RegistryError, "unsafe"):
                registry._extract(tar_path, "tar.gz", destination, ("tool",))

            zip_path = root / "unsafe.zip"
            with zipfile.ZipFile(zip_path, "w") as bundle:
                bundle.writestr("../escape", b"x")
            with self.assertRaisesRegex(RegistryError, "unsafe"):
                registry._extract(zip_path, "zip", destination, ("tool",))
            link_path = root / "link.zip"
            link = zipfile.ZipInfo("link")
            link.external_attr = (0o120777 << 16) | 0xA000
            with zipfile.ZipFile(link_path, "w") as bundle:
                bundle.writestr(link, "target")
            with self.assertRaisesRegex(RegistryError, "symbolic"):
                registry._extract(link_path, "zip", destination, ("tool",))

    def test_executable_lookup_and_atomic_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "payload"
            payload.mkdir()
            with self.assertRaisesRegex(RegistryError, "exactly one"):
                registry._find_executable(payload, "tool")
            executable = payload / "tool"
            executable.write_text("tool", encoding="utf-8")
            self.assertEqual(registry._find_executable(payload, "tool"), executable)
            (payload / "nested").mkdir()
            (payload / "nested/tool").write_text("tool", encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "exactly one"):
                registry._find_executable(payload, "tool")

            target = root / "active"
            target.mkdir()
            (target / "value").write_text("old", encoding="utf-8")
            staged = root / "staged"
            staged.mkdir()
            (staged / "value").write_text("new", encoding="utf-8")
            registry._replace_directory(staged, target)
            self.assertEqual((target / "value").read_text(encoding="utf-8"), "new")


class EnvironmentInstallerTests(unittest.TestCase):
    def test_asset_preparation_and_installation_classify_failures(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            missing = _tool(url=None)
            with self.assertRaisesRegex(RegistryError, "no downloadable"):
                registry._prepare_asset(missing, work)
            wrong = Tool(**{**_tool().__dict__, "checksum": Checksum("other", "value")})
            with (
                patch("qa_toolkit.registry._download"),
                self.assertRaisesRegex(RegistryError, "require sha256"),
            ):
                registry._prepare_asset(wrong, work)

            tool = _tool()
            with (
                patch("qa_toolkit.registry._download") as download,
                patch("qa_toolkit.registry._verify_sha256"),
                patch("qa_toolkit.registry._extract") as extract,
                patch("qa_toolkit.registry.tool_status", return_value=(True, "1.2.3")),
            ):

                def materialize(
                    _archive: Path, _kind: str, payload: Path, _names: tuple[str, ...]
                ) -> None:
                    (payload / "sample").write_text("tool", encoding="utf-8")

                extract.side_effect = materialize
                staged = registry._prepare_asset(tool, work)
            self.assertTrue((staged / "bin/sample").is_symlink())
            download.assert_called_once()

            with (
                patch("qa_toolkit.registry._prepare_asset", side_effect=RegistryError("bad")),
                self.assertRaisesRegex(RegistryError, "bad"),
            ):
                registry._install_asset(tool, work)

    def test_environment_views_and_command_classification(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            staged = root / "staged"
            for environment in ("python", "node", "julia-1.10.11"):
                with self.subTest(environment=environment):
                    view = registry._environment_view(environment, staged)
                    self.assertTrue((view / "toolkit").is_dir())
                    shutil.rmtree(view)
            with self.assertRaisesRegex(RegistryError, "unsupported staged"):
                registry._environment_view("other", staged)

            with patch(
                "qa_toolkit.registry.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                registry._run(["true"])
            with (
                patch("qa_toolkit.registry.subprocess.run", side_effect=OSError("bad")),
                self.assertRaisesRegex(RegistryError, "failed to execute"),
            ):
                registry._run(["bad"])
            with (
                patch(
                    "qa_toolkit.registry.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 1, "", "failure"),
                ),
                self.assertRaisesRegex(RegistryError, "exit 1"),
            ):
                registry._run(["false"])

    def test_python_node_and_julia_installers_stage_then_replace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            uv = root / "toolkit/uv/bin/uv"
            uv.parent.mkdir(parents=True)
            uv.write_text("uv", encoding="utf-8")
            with (
                patch("qa_toolkit.registry.select_tools", return_value=(_tool("uv"),)),
                patch("qa_toolkit.registry.executable_path", return_value=uv),
                patch("qa_toolkit.registry._run") as run,
                patch(
                    "qa_toolkit.registry.load_registry", return_value=(_tool(environment="python"),)
                ),
                patch("qa_toolkit.registry.tool_status", return_value=(True, "current")),
                patch("qa_toolkit.registry._replace_directory") as replace,
            ):
                registry._install_python_environment(root)
            self.assertEqual(run.call_count, 3)
            replace.assert_called_once()

            config = root / "config/cspell"
            config.mkdir(parents=True)
            (config / "package.json").write_text("{}", encoding="utf-8")
            (config / "package-lock.json").write_text("{}", encoding="utf-8")
            node = _tool("node", environment="node", archive="tar.xz", executables=("node",))
            cspell = _tool(
                "cspell", environment="node", archive=None, url=None, executables=("cspell",)
            )

            def expand_node(
                _archive: Path, _kind: str, expanded: Path, _names: tuple[str, ...]
            ) -> None:
                runtime = expanded / "node-runtime"
                (runtime / "bin").mkdir(parents=True)
                (runtime / "bin/node").write_text("node", encoding="utf-8")
                (runtime / "lib/node_modules/npm/bin").mkdir(parents=True)
                (runtime / "lib/node_modules/npm/bin/npm-cli.js").write_text(
                    "npm", encoding="utf-8"
                )

            with (
                patch("qa_toolkit.registry.select_tools", return_value=(node, cspell)),
                patch("qa_toolkit.registry._download"),
                patch("qa_toolkit.registry._verify_sha256"),
                patch("qa_toolkit.registry._extract", side_effect=expand_node),
                patch("qa_toolkit.registry._run"),
                patch("qa_toolkit.registry.tool_status", return_value=(True, "current")),
                patch("qa_toolkit.registry._replace_directory") as replace,
            ):
                registry._install_node_environment(root)
            replace.assert_called_once()

            runtime = _tool(
                "julia-1.10.11",
                environment="julia-1.10.11",
                archive="tar.gz",
                executables=("julia",),
            )

            def expand_julia(
                _archive: Path, _kind: str, expanded: Path, _names: tuple[str, ...]
            ) -> None:
                installation = expanded / "julia-runtime"
                (installation / "bin").mkdir(parents=True)
                (installation / "bin/julia").write_text("julia", encoding="utf-8")

            with (
                patch("qa_toolkit.registry._download"),
                patch("qa_toolkit.registry._verify_sha256"),
                patch("qa_toolkit.registry._extract", side_effect=expand_julia),
                patch("qa_toolkit.registry.tool_status", return_value=(True, "current")),
                patch("qa_toolkit.registry._replace_directory") as replace,
            ):
                registry._install_julia_runtime(runtime, root)
            replace.assert_called_once()

    def test_julia_qa_and_fetch_routing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "config/julia/locks/1.10").mkdir(parents=True)
            (root / "config/julia/locks/1.12").mkdir(parents=True)
            (root / "config/julia/Project.toml").write_text("[deps]\n", encoding="utf-8")
            for minor in ("1.10", "1.12"):
                (root / f"config/julia/locks/{minor}/Manifest.toml").write_text(
                    "[deps]\n", encoding="utf-8"
                )
            runtimes = (
                _tool("julia-1.10.11", environment="julia-1.10.11"),
                _tool("julia-1.12.6", environment="julia-1.12.6"),
            )
            packages = (
                _tool("juliaformatter", environment="julia", executables=()),
                _tool("aqua", environment="julia", executables=()),
                _tool("explicitimports", environment="julia", executables=()),
            )
            with (
                patch("qa_toolkit.registry.select_tools", side_effect=(runtimes, packages)),
                patch("qa_toolkit.registry.tool_status", return_value=(True, "current")),
                patch("qa_toolkit.registry.executable_path", return_value=Path("/julia")),
                patch("qa_toolkit.registry._run") as run,
                patch(
                    "qa_toolkit.registry._julia_package_status_at", return_value=(True, "current")
                ),
                patch("qa_toolkit.registry._replace_directory") as replace,
            ):
                registry._install_julia_qa(root)
            self.assertEqual(run.call_count, 2)
            replace.assert_called_once()

            with (
                patch("qa_toolkit.registry.select_tools", return_value=runtimes),
                patch("qa_toolkit.registry.tool_status", return_value=(False, "missing")),
                self.assertRaisesRegex(RegistryError, "both accepted"),
            ):
                registry._install_julia_qa(root)

        environments = ("python", "node", "julia-1.10.11", "julia")
        for environment in environments:
            tool = _tool(environment, environment=environment)
            function = {
                "python": "_install_python_environment",
                "node": "_install_node_environment",
                "julia-1.10.11": "_install_julia_runtime",
                "julia": "_install_julia_qa",
            }[environment]
            with (
                self.subTest(environment=environment),
                patch("qa_toolkit.registry.load_registry", return_value=(tool,)),
                patch("qa_toolkit.registry.tool_status", return_value=(False, "missing")),
                patch(f"qa_toolkit.registry.{function}") as install,
            ):
                registry.fetch_environment(environment, Path("/root"))
            install.assert_called_once()
        with (
            patch("qa_toolkit.registry.load_registry", return_value=()),
            self.assertRaisesRegex(RegistryError, "unsupported environment"),
        ):
            registry.fetch_environment("other", Path("/root"))
        with (
            patch("qa_toolkit.registry.load_registry", return_value=()),
            self.assertRaisesRegex(RegistryError, "missing runtime"),
        ):
            registry.fetch_environment("julia-1.9.0", Path("/root"))

    def test_fetch_short_circuits_and_update_validates_arguments(self) -> None:
        tool = _tool()
        with (
            patch("qa_toolkit.registry.tool_status", return_value=(True, "current")),
            patch("qa_toolkit.registry._install_asset") as install,
        ):
            registry.fetch_tool(tool, Path("/root"))
        install.assert_not_called()
        with (
            patch("qa_toolkit.registry.tool_status", return_value=(False, "missing")),
            patch("qa_toolkit.registry.fetch_environment") as fetch,
        ):
            registry.fetch_tool(_tool(environment="python"), Path("/root"))
            registry.fetch_tool(_tool(environment="julia"), Path("/root"))
        self.assertEqual(fetch.call_count, 2)

        nonstandalone = _tool(environment="python")
        cases = (
            (nonstandalone, "1", "0" * 64, "raw"),
            (tool, "", "0" * 64, "raw"),
            (tool, "1", "bad", "raw"),
            (tool, "1", "0" * 64, "rar"),
        )
        for selected, version, checksum, archive in cases:
            with (
                self.subTest(version=version, archive=archive),
                patch("qa_toolkit.registry.select_tools", return_value=(selected,)),
                self.assertRaises(RegistryError),
            ):
                registry.update_standalone(
                    "sample",
                    version,
                    "https://example.invalid/sample",
                    checksum,
                    archive,
                    root=Path("/root"),
                )


if __name__ == "__main__":
    unittest.main()
