"""Acceptance tests for exact-runtime Julia execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.deployment import enroll
from qa_toolkit.julia_source import findings
from qa_toolkit.julia_tools import JuliaToolError, _run_native, _run_trivy, discover_projects
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
                    f"julia-tests-{runtime}",
                    f"julia-aqua-{runtime}",
                    f"julia-explicit-imports-{runtime}",
                )
                self.assertEqual(tuple(summary["planned_order"]), expected)
                self.assertEqual(
                    tuple(result["id"] for result in summary["results"]),
                    expected,
                )
                for result in summary["results"][1:]:
                    self.assertEqual(result["julia_runtime"], runtime)
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


if __name__ == "__main__":
    unittest.main()
