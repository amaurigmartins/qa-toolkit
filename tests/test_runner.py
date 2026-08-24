"""Tests for deterministic plans, result normalization, and local evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.deployment import enroll
from qa_toolkit.paths import toolkit_root
from qa_toolkit.runner import execute
from test_deployment import _central, _consumer, _git


def _commit(repository: Path, message: str) -> None:
    _git(repository, "add", "-A")
    _git(
        repository,
        "-c",
        "user.name=QA Toolkit Test",
        "-c",
        "user.email=qa-toolkit@example.invalid",
        "commit",
        "-m",
        message,
    )


def _runner_fixture(parent: Path) -> tuple[Path, Path]:
    root = parent / "central"
    target = parent / "consumer"
    root.mkdir()
    target.mkdir()
    _central(root)
    _consumer(target)
    (root / "profiles/fixture.toml").write_text(
        """schema_version = 1
name = "fixture"
tools = ["python"]
configurations = []
hooks = []
skills = []

[[gates]]
id = "check-pass"
phase = "check"
argv = ["{target-python}", "gate.py", "pass"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["normal"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]

[[gates]]
id = "check-advisory"
phase = "check"
argv = ["{target-python}", "gate.py", "finding"]
triggers = ["src/**"]
timeout = 30
severity = "advisory"
variants = ["normal"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]

[[gates]]
id = "sentinel-finding"
phase = "sentinel"
argv = ["{target-python}", "gate.py", "finding"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["normal"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]

[[gates]]
id = "sentinel-after"
phase = "sentinel"
argv = ["{target-python}", "gate.py", "pass"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["normal"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]

[[gates]]
id = "error-first"
phase = "check"
argv = ["{target-python}", "gate.py", "error"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["error"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]

[[gates]]
id = "error-after"
phase = "check"
argv = ["{target-python}", "gate.py", "pass"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["error"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]
""",
        encoding="utf-8",
    )
    _commit(root, "test(profile): add runner gates")
    python_directory = root / "toolkit/python/bin"
    python_directory.mkdir(parents=True)
    python_directory.joinpath("python").symlink_to(toolkit_root() / "toolkit/python/bin/python")

    (target / "gate.py").write_text(
        """import sys
mode = sys.argv[1]
print(f"stdout-{mode}")
print(f"stderr-{mode}", file=sys.stderr)
raise SystemExit({"pass": 0, "finding": 1, "error": 2}[mode])
""",
        encoding="utf-8",
    )
    consumer = (target / ".qat.toml").read_text(encoding="utf-8")
    consumer += """

[[gates]]
id = "consumer-check"
phase = "check"
argv = ["{target-python}", "gate.py", "pass"]
triggers = ["src/**"]
timeout = 30
severity = "blocking"
variants = ["normal"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]
"""
    (target / ".qat.toml").write_text(consumer, encoding="utf-8")
    _commit(target, "test(repo): add runner fixture")
    enroll(target, root)
    return root, target


class RunnerTests(unittest.TestCase):
    def test_sentinel_runs_check_once_and_retains_full_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, target = _runner_fixture(Path(directory))

            code, evidence = execute(
                target,
                "sentinel",
                variant="normal",
                include_advisory=True,
                changed=("src/example.py",),
                root=root,
            )

            self.assertEqual(code, 1)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                summary["planned_order"],
                [
                    "check-pass",
                    "check-advisory",
                    "consumer-check",
                    "sentinel-finding",
                    "sentinel-after",
                ],
            )
            self.assertEqual(
                [result["result"] for result in summary["results"]],
                ["pass", "finding", "pass", "finding", "pass"],
            )
            self.assertEqual(summary["results"][2]["execution_owner"], "consumer")
            output = evidence / summary["results"][3]["stdout"]
            self.assertEqual(output.read_text(encoding="utf-8"), "stdout-finding\n")

    def test_execution_error_stops_commands_but_preserves_planned_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, target = _runner_fixture(Path(directory))

            code, evidence = execute(
                target,
                "check",
                variant="error",
                changed=("src/example.py",),
                root=root,
            )

            self.assertEqual(code, 2)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["planned_order"], ["error-first", "error-after"])
            self.assertEqual(
                [result["result"] for result in summary["results"]],
                ["execution-error", "not-run"],
            )

    def test_advisory_findings_do_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, target = _runner_fixture(Path(directory))

            code, evidence = execute(
                target,
                "advisory",
                variant="normal",
                changed=("src/example.py",),
                root=root,
            )

            self.assertEqual(code, 0)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["planned_order"], ["check-advisory"])
            self.assertEqual(summary["results"][0]["result"], "finding")

    def test_nonmatching_triggers_produce_an_empty_successful_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, target = _runner_fixture(Path(directory))

            code, evidence = execute(
                target,
                "check",
                variant="normal",
                changed=("docs/readme.md",),
                root=root,
            )

            self.assertEqual(code, 0)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["planned_order"], [])


if __name__ == "__main__":
    unittest.main()
