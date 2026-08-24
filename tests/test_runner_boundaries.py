"""Boundary tests for gate argument resolution and retained execution evidence."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qa_toolkit import runner
from qa_toolkit.python_tools import PythonResolution


def _gate(identifier: str = "gate") -> runner.PlannedGate:
    return runner.PlannedGate(
        identifier,
        "check",
        ("command",),
        30,
        "blocking",
        (1,),
        (2,),
        "central",
        "profile.toml",
    )


class ArgumentResolutionTests(unittest.TestCase):
    def test_python_selection_prefers_consumer_and_requires_an_executable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            consumer = target / "project/.venv/bin/python"
            consumer.parent.mkdir(parents=True)
            consumer.write_text("binary", encoding="utf-8")
            consumer.chmod(0o755)
            self.assertEqual(runner._target_python(target, Path("project"), root), consumer)
            consumer.unlink()
            with self.assertRaisesRegex(runner.RunnerError, "cannot resolve"):
                runner._target_python(target, Path("project"), root)

    def test_argument_placeholders_are_explicit_and_fail_closed(self) -> None:
        target = Path("/target")
        root = Path("/root")
        python = Path("/python")
        self.assertEqual(runner._resolve_argument("{target}", target, root, python), "/target")
        self.assertEqual(
            runner._resolve_argument("{target-python}", target, root, python), "/python"
        )
        self.assertEqual(runner._resolve_argument("{toolkit}", target, root, python), "/root")
        self.assertTrue(
            runner._resolve_argument("{qat-python}", target, root, python).endswith("python")
        )
        with self.assertRaisesRegex(runner.RunnerError, "unsupported argument placeholder"):
            runner._resolve_argument("{unknown}", target, root, python)
        tool = SimpleNamespace(tool_id="missing")
        with (
            patch("qa_toolkit.runner.select_tools", return_value=(tool,)),
            patch("qa_toolkit.runner.executable_path", return_value=Path("/missing")),
            self.assertRaisesRegex(runner.RunnerError, "selected tool is unavailable"),
        ):
            runner._resolve_argument("{tool:missing}", target, root, python)

    def test_python_and_central_configuration_placeholders_require_resolved_inputs(self) -> None:
        target = Path("/target")
        root = Path("/root")
        executable = Path("/python")
        for argv, message in (
            (("{python-config:ruff}",), "unavailable Python configuration"),
            (("{python-paths:ruff}",), "unavailable Python paths"),
            (("{central-config:../outside}",), "unavailable central configuration"),
        ):
            with self.subTest(argv=argv), self.assertRaisesRegex(runner.RunnerError, message):
                runner._resolve_arguments(argv, target, root, executable, None)
        resolution = PythonResolution(
            {"ruff": Path("/config/ruff.toml")},
            {},
            {"ruff": ("src", "tests")},
            (),
            {},
        )
        self.assertEqual(
            runner._resolve_arguments(
                ("{python-config:ruff}", "{python-paths:ruff}"),
                target,
                root,
                executable,
                resolution,
            ),
            ("/config/ruff.toml", "src", "tests"),
        )


class ExecutionBoundaryTests(unittest.TestCase):
    def _execute(
        self,
        target: Path,
        root: Path,
        plan: tuple[runner.PlannedGate, ...],
        *,
        mode: str = "check",
        process: object,
        identities: tuple[object, ...] = (),
        proof_error: Exception | None = None,
    ) -> tuple[int, Path]:
        resolved = runner.ResolvedPlan(plan, {"configuration": "digest"})
        consumer = SimpleNamespace(profile="fixture")
        profile = SimpleNamespace(name="fixture")
        managers = (
            patch("qa_toolkit.runner.resolve_target", return_value=target),
            patch("qa_toolkit.runner._resolve_plan", return_value=resolved),
            patch("qa_toolkit.runner.load_consumer", return_value=consumer),
            patch("qa_toolkit.runner.load_profile", return_value=profile),
            patch("qa_toolkit.runner.digest_consumer", return_value="consumer"),
            patch("qa_toolkit.runner.digest_profile", return_value="profile"),
            patch("qa_toolkit.runner._git_facts", return_value=("a" * 40, False, "clean")),
            patch("qa_toolkit.runner.subprocess.run", side_effect=process),
        )
        with contextlib.ExitStack() as stack:
            for manager in managers:
                stack.enter_context(manager)
            if identities:
                stack.enter_context(patch("qa_toolkit.runner.identity", side_effect=identities))
            if proof_error is not None:
                stack.enter_context(
                    patch("qa_toolkit.runner.record_proof", side_effect=proof_error)
                )
            with contextlib.redirect_stdout(io.StringIO()):
                return runner.execute(target, mode, root=root)  # type: ignore[arg-type]

    def test_spawn_failure_stops_later_gates_and_retains_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            (target / ".git/qat").mkdir(parents=True)
            root.mkdir()
            code, evidence = self._execute(
                target,
                root,
                (_gate("first"), _gate("after")),
                process=OSError("missing executable"),
            )
            self.assertEqual(code, 2)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [item["result"] for item in summary["results"]], ["execution-error", "not-run"]
            )
            self.assertIn(
                "missing executable", (evidence / summary["results"][0]["stderr"]).read_text()
            )

    def test_sentinel_detects_identity_change_and_proof_write_failure(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            (target / ".git/qat").mkdir(parents=True)
            root.mkdir()
            code, evidence = self._execute(
                target,
                root,
                (_gate(),),
                mode="sentinel",
                process=(completed,),
                identities=("before", "after"),
            )
            self.assertEqual(code, 2)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("identity changed", summary["proof_error"])

            code, evidence = self._execute(
                target,
                root,
                (_gate(),),
                mode="sentinel",
                process=(completed,),
                identities=("same", "same"),
                proof_error=OSError("read-only state"),
            )
            self.assertEqual(code, 2)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("cannot retain Sentinel proof", summary["proof_error"])

    def test_guarded_execution_converts_planning_errors_to_exit_two(self) -> None:
        with (
            patch("qa_toolkit.runner.execute", side_effect=runner.RunnerError("bad plan")),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(runner.guarded_execute(Path("."), "check"), (2, None))
        self.assertIn("bad plan", error.getvalue())


if __name__ == "__main__":
    unittest.main()
