"""Acceptance tests for exact-runtime Julia execution."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from qa_toolkit import julia_source, julia_tools
from qa_toolkit.deployment import enroll
from qa_toolkit.julia_source import findings
from qa_toolkit.julia_tools import (
    JuliaProject,
    JuliaToolError,
    _eligible,
    _environment,
    _invoke,
    _julia_argv,
    _package_identity,
    _run_native,
    _run_trivy,
    _tracked_snapshot,
    discover_projects,
)
from qa_toolkit.paths import toolkit_root
from qa_toolkit.runner import execute

FIXTURE = Path(__file__).parent / "fixtures" / "julia-consumer"


def _git(target: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(target), *arguments],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
    )


def _target(runtime: str, parent: Path) -> Path:
    target = parent / "consumer"
    shutil.copytree(FIXTURE, target)
    minor = ".".join(runtime.split(".")[:2])
    shutil.copy2(target / f"locks/{minor}/root/Manifest.toml", target / "Manifest.toml")
    shutil.copy2(
        target / f"locks/{minor}/nested/Manifest.toml",
        target / "packages/QATNestedConsumer/Manifest.toml",
    )
    _git(parent, "init", "-b", "main", str(target))
    _git(target, "config", "user.name", "QA Toolkit")
    _git(target, "config", "user.email", "qat@example.invalid")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "test(repo): create disposable Julia target")
    return target


class JuliaToolAcceptanceTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("QAT_RUN_TRIVY_ACCEPTANCE") == "1",
        "set QAT_RUN_TRIVY_ACCEPTANCE=1 for the network-backed Trivy proof",
    )
    def test_trivy_scans_only_copied_julia_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = _target("1.12.6", Path(raw))
            before = subprocess.run(
                ["git", "-C", str(target), "status", "--porcelain=v1", "-z"],
                check=True,
                capture_output=True,
                timeout=30,
                shell=False,
            ).stdout
            self.assertEqual(_run_trivy(target, toolkit_root()), 0)
            after = subprocess.run(
                ["git", "-C", str(target), "status", "--porcelain=v1", "-z"],
                check=True,
                capture_output=True,
                timeout=30,
                shell=False,
            ).stdout
            self.assertEqual(before, after)

    def test_docstring_projection_and_scientific_identifiers_fail_closed(self) -> None:
        source = """module Example
export x, zz
\"\"\"Reader-facing documentation.\"\"\"
x(value) = value
zz(value) = value
end
"""
        self.assertEqual(len(findings("src/Example.jl", source)), 1)
        with self.assertRaisesRegex(ValueError, "Julia syntax tree contains an error"):
            findings("src/Invalid.jl", '"""Unclosed documentation.\nfunction solve()\n')

    def test_both_runtimes_run_format_tests_aqua_and_import_checks(self) -> None:
        for runtime in ("1.10.11", "1.12.6"):
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as raw:
                target = _target(runtime, Path(raw))
                enroll(target, toolkit_root())
                before = {
                    path: (target / path).read_bytes()
                    for path in subprocess.run(
                        ["git", "-C", str(target), "ls-files"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=False,
                    ).stdout.splitlines()
                }
                sentinel_exit, evidence = execute(
                    target,
                    "sentinel",
                    variant=runtime,
                    changed=("src/QATJuliaConsumer.jl",),
                    root=toolkit_root(),
                )
                self.assertEqual(sentinel_exit, 0, evidence)
                summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
                expected = (
                    "julia-source",
                    f"julia-format-{runtime}",
                    "text-spelling",
                    "text-prose",
                    f"julia-tests-{runtime}",
                    f"julia-aqua-{runtime}",
                    f"julia-explicit-imports-{runtime}",
                )
                self.assertEqual(tuple(summary["planned_order"]), expected)
                self.assertEqual(
                    tuple(result["id"] for result in summary["results"]),
                    expected,
                )
                for result in summary["results"]:
                    expected_runtime = (
                        runtime
                        if result["id"]
                        in {
                            f"julia-format-{runtime}",
                            f"julia-tests-{runtime}",
                            f"julia-aqua-{runtime}",
                            f"julia-explicit-imports-{runtime}",
                        }
                        else None
                    )
                    self.assertEqual(result["julia_runtime"], expected_runtime)
                self.assertEqual(before, {path: (target / path).read_bytes() for path in before})

    def test_nested_projects_are_discovered_and_missing_manifests_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = _target("1.12.6", Path(raw))
            copied = tuple(
                subprocess.run(
                    ["git", "-C", str(target), "ls-files"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,
                ).stdout.splitlines()
            )
            projects = discover_projects(target, copied)
            self.assertEqual(
                [project.name for project in projects],
                ["QATJuliaConsumer", "QATNestedConsumer"],
            )
            (target / "Manifest.toml").unlink()
            _git(target, "add", "Manifest.toml")
            _git(target, "commit", "-m", "test(julia): remove root manifest")
            with self.assertRaisesRegex(JuliaToolError, "missing manifest"):
                _run_native("tests", "1.12.6", target, toolkit_root())


class JuliaToolBoundaryTests(unittest.TestCase):
    def test_snapshot_refuses_gitlinks_and_irregular_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            snapshot = Path(raw) / "snapshot"
            target.mkdir()
            snapshot.mkdir()
            (target / "source.jl").write_text("x = 1\n", encoding="utf-8")
            with (
                patch(
                    "qa_toolkit.julia_tools.tracked_entries",
                    return_value=(("160000", "source.jl"),),
                ),
                self.assertRaisesRegex(JuliaToolError, "non-regular tracked input"),
            ):
                _tracked_snapshot(target, snapshot)
            (target / "source.jl").unlink()
            (target / "source.jl").symlink_to(target)
            with (
                patch(
                    "qa_toolkit.julia_tools.tracked_entries",
                    return_value=(("100644", "source.jl"),),
                ),
                self.assertRaisesRegex(JuliaToolError, "input is not regular"),
            ):
                _tracked_snapshot(target, snapshot)

    def test_project_discovery_and_identity_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            project = root / "Project.toml"
            project.write_text('name = "Example"\n', encoding="utf-8")
            with self.assertRaisesRegex(JuliaToolError, "invalid package UUID"):
                discover_projects(root, ("Project.toml",))
            project.write_text("[broken\n", encoding="utf-8")
            with self.assertRaisesRegex(JuliaToolError, "cannot parse Julia project"):
                discover_projects(root, ("Project.toml",))
            project.write_bytes(b"x" * 262_145)
            with self.assertRaisesRegex(JuliaToolError, "too large"):
                discover_projects(root, ("Project.toml",))
        self.assertIsNone(_package_identity({}, "Project.toml"))
        identity_cases: tuple[tuple[dict[str, object], str], ...] = (
            ({"name": "bad-name", "uuid": "x", "version": "1"}, "package name"),
            ({"name": "Good", "uuid": "x", "version": "1"}, "package UUID"),
            (
                {
                    "name": "Good",
                    "uuid": "12345678-1234-1234-1234-123456789abc",
                    "version": "",
                },
                "package version",
            ),
        )
        for value, message in identity_cases:
            with self.subTest(message=message), self.assertRaisesRegex(JuliaToolError, message):
                _package_identity(value, "Project.toml")

    def test_project_eligibility_requires_loadable_tests_and_manifests(self) -> None:
        invalid = JuliaProject(PurePosixPath("nested"), "Nested", False, None, True)
        with self.assertRaisesRegex(JuliaToolError, "loadable package"):
            _eligible((invalid,), "tests")
        unloaded = JuliaProject(PurePosixPath("nested"), "Nested", False, None, False)
        self.assertEqual(_eligible((unloaded,), "aqua"), ())
        no_tests = JuliaProject(PurePosixPath("nested"), "Nested", True, None, False)
        self.assertEqual(_eligible((no_tests,), "tests"), ())
        missing = JuliaProject(PurePosixPath("nested"), "Nested", True, None, True)
        with self.assertRaisesRegex(JuliaToolError, "missing manifest"):
            _eligible((missing,), "aqua")

    def test_private_environment_argv_and_invocation_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            run = Path(raw) / "run"
            root = Path(raw) / "root"
            run.mkdir()
            environment = _environment(run, root, "1.12.6")
            self.assertTrue(environment["JULIA_DEPOT_PATH"].startswith(str(run / "depot")))
            argv = _julia_argv(Path("julia"), Path("project"), Path("script.jl"), "argument")
            self.assertIn("--startup-file=no", argv)
            completed = subprocess.CompletedProcess((), 1, f"{run}/source\n", f"{run}/error")
            output = io.StringIO()
            error = io.StringIO()
            with (
                patch("qa_toolkit.julia_tools.subprocess.run", return_value=completed),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(error),
            ):
                self.assertEqual(_invoke(("julia",), root, environment, run, 1), 1)
            self.assertIn("<julia-run>", output.getvalue())
            self.assertIn("<julia-run>", error.getvalue())
            with (
                patch("qa_toolkit.julia_tools.subprocess.run", side_effect=OSError("missing")),
                self.assertRaisesRegex(JuliaToolError, "cannot execute Julia command"),
            ):
                _invoke(("julia",), root, environment, run, 1)

    def _native_root(self, parent: Path) -> tuple[Path, Path]:
        root = parent / "root"
        target = parent / "target"
        executable = root / "toolkit/julia/1.12.6/bin/julia"
        executable.parent.mkdir(parents=True)
        executable.write_text("binary", encoding="utf-8")
        formatter = root / "config/julia/.JuliaFormatter.toml"
        formatter.parent.mkdir(parents=True)
        formatter.write_text("", encoding="utf-8")
        target.mkdir()
        return root, target

    def test_native_format_and_instantiate_statuses_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root, target = self._native_root(Path(raw))
            with (
                patch("qa_toolkit.julia_tools._tracked_snapshot", return_value=()),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=()),
                patch("qa_toolkit.julia_tools._invoke", return_value=7),
            ):
                self.assertEqual(_run_native("format", "1.12.6", target, root), 1)

            project = JuliaProject(
                PurePosixPath(),
                "Example",
                True,
                PurePosixPath("Manifest.toml"),
                True,
            )
            with (
                patch(
                    "qa_toolkit.julia_tools._tracked_snapshot",
                    return_value=(".JuliaFormatter.toml",),
                ),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=(project,)),
                patch("qa_toolkit.julia_tools._dependency_identity", return_value=("one", "two")),
                patch("qa_toolkit.julia_tools._invoke", return_value=2),
            ):
                self.assertEqual(_run_native("tests", "1.12.6", target, root), 2)
            with (
                patch(
                    "qa_toolkit.julia_tools._tracked_snapshot",
                    return_value=(".JuliaFormatter.toml",),
                ),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=(project,)),
                patch(
                    "qa_toolkit.julia_tools._dependency_identity",
                    side_effect=(("before", "before"), ("after", "after")),
                ),
                patch("qa_toolkit.julia_tools._invoke", side_effect=(0, 0)),
                self.assertRaisesRegex(JuliaToolError, "modified copied dependency"),
            ):
                _run_native("aqua", "1.12.6", target, root)
            with (
                patch(
                    "qa_toolkit.julia_tools._tracked_snapshot",
                    return_value=(".JuliaFormatter.toml",),
                ),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=(project,)),
                patch(
                    "qa_toolkit.julia_tools._dependency_identity",
                    return_value=("same", "same"),
                ),
                patch("qa_toolkit.julia_tools._invoke", side_effect=(0, 1)),
            ):
                self.assertEqual(_run_native("explicit-imports", "1.12.6", target, root), 1)

    def test_missing_runtime_trivy_empty_scan_and_command_main(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "root"
            target = Path(raw) / "target"
            target.mkdir()
            with self.assertRaisesRegex(JuliaToolError, "missing accepted Julia runtime"):
                _run_native("tests", "1.12.6", target, root)
            with self.assertRaisesRegex(JuliaToolError, "missing accepted Trivy"):
                _run_trivy(target, root)
            trivy = root / "toolkit/trivy/bin/trivy"
            trivy.parent.mkdir(parents=True)
            trivy.write_text("binary", encoding="utf-8")
            with (
                patch("qa_toolkit.julia_tools._tracked_snapshot", return_value=()),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=()),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(_run_trivy(target, root), 0)
            self.assertIn("no tracked manifests", output.getvalue())

            def snapshot(_target: Path, destination: Path) -> tuple[str, ...]:
                (destination / "Project.toml").write_text("", encoding="utf-8")
                (destination / "Manifest.toml").write_text("", encoding="utf-8")
                return "Project.toml", "Manifest.toml"

            project = JuliaProject(
                PurePosixPath(),
                None,
                False,
                PurePosixPath("Manifest.toml"),
                False,
            )
            with (
                patch("qa_toolkit.julia_tools._tracked_snapshot", side_effect=snapshot),
                patch("qa_toolkit.julia_tools.discover_projects", return_value=(project,)),
                patch("qa_toolkit.julia_tools._invoke", return_value=7),
            ):
                self.assertEqual(_run_trivy(target, root), 2)

        with (
            patch("qa_toolkit.julia_tools.resolve_target", return_value=Path("/target")),
            patch("qa_toolkit.julia_tools._run_trivy", return_value=1),
            self.assertRaises(SystemExit) as exited,
        ):
            julia_tools.main(["vulnerabilities"])
        self.assertEqual(exited.exception.code, 1)
        with (
            patch("qa_toolkit.julia_tools.resolve_target", return_value=Path("/target")),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as exited,
        ):
            julia_tools.main(["tests"])
        self.assertEqual(exited.exception.code, 2)

    def test_julia_source_main_reports_findings_and_errors(self) -> None:
        target = Path("/target")
        with (
            patch("qa_toolkit.julia_source.resolve_target", return_value=target),
            patch("qa_toolkit.julia_source.tracked_regular_files", return_value=("src/file.jl",)),
            patch.object(Path, "read_text", return_value="export zz\n"),
            patch("qa_toolkit.julia_source.findings", return_value=("finding",)),
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaises(SystemExit) as exited,
        ):
            julia_source.main([])
        self.assertEqual(exited.exception.code, 1)
        self.assertIn("finding", output.getvalue())
        with (
            patch("qa_toolkit.julia_source.resolve_target", side_effect=OSError("missing")),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as exited,
        ):
            julia_source.main([])
        self.assertEqual(exited.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
