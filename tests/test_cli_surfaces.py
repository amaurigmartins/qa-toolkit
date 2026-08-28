"""Direct tests for the small command surfaces and dispatcher."""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_deployment import _git

from qa_toolkit import (
    agent_cli,
    corpus_cli,
    dispatch,
    evidence_cli,
    grain_adapter,
    hook_cli,
    package_version,
    repo_cli,
    run_cli,
    tool_cli,
    work_cli,
)
from qa_toolkit.deployment import DeploymentError
from qa_toolkit.hook_deployment import HookDeploymentError
from qa_toolkit.registry import RegistryError
from qa_toolkit.work import WorkError

ROOT = Path(__file__).parents[1]


class _Record:
    def __init__(self, value: object) -> None:
        self.value = value

    def as_dict(self) -> object:
        return self.value


def _output(callable_: object, arguments: list[str]) -> tuple[str, str, int | None]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code: int | None = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            callable_(arguments)  # type: ignore[operator]
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else 1
    return stdout.getvalue(), stderr.getvalue(), code


class DispatchTests(unittest.TestCase):
    def test_tracked_launcher_resolves_an_external_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            launcher = Path(raw) / "qat"
            launcher.symlink_to(ROOT / "bin/qat")
            completed = subprocess.run(
                [str(launcher), "tool", "list"],
                cwd="/",
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("uv\t", completed.stdout)

    def test_grouped_and_direct_commands_are_translated(self) -> None:
        self.assertEqual(
            dispatch._command_name(["check", "--target", "."]), ("qat-check", ["--target", "."])
        )
        self.assertEqual(dispatch._command_name(["repo", "sync", "."]), ("qat-repo-sync", ["."]))
        for arguments in ([], ["repo"]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                dispatch._command_name(arguments)

    def test_main_executes_a_local_or_path_utility_and_reports_usage(self) -> None:
        with (
            patch.object(sys, "argv", ["qat", "check", "--target", "."]),
            patch("qa_toolkit.dispatch.os.execvp", side_effect=RuntimeError("stop")) as execute,
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            dispatch.main()
        self.assertTrue(Path(execute.call_args.args[0]).name == "qat-check")

        with (
            patch.object(sys, "argv", ["qat", "unknown", "operation"]),
            patch("qa_toolkit.dispatch.Path.is_file", return_value=False),
            patch("qa_toolkit.dispatch.os.execvp", side_effect=RuntimeError("stop")) as execute,
            self.assertRaisesRegex(RuntimeError, "stop"),
        ):
            dispatch.main()
        self.assertEqual(execute.call_args.args[0], "qat-unknown-operation")

        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["qat"]),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            dispatch.main()
        self.assertEqual(raised.exception.code, 2)
        rendered = stderr.getvalue()
        self.assertIn("usage", rendered)
        self.assertIn("Quality gates:", rendered)
        self.assertIn("docs mermaid", rendered)
        self.assertIn("repo enroll | sync | status | unenroll", rendered)
        self.assertIn("work report | retire | release | template", rendered)

        stdout = io.StringIO()
        with patch.object(sys, "argv", ["qat", "--help"]), contextlib.redirect_stdout(stdout):
            dispatch.main()
        self.assertIn("Central tools:", stdout.getvalue())


class RunCliTests(unittest.TestCase):
    def test_run_modes_forward_all_bounded_options(self) -> None:
        with (
            patch(
                "qa_toolkit.run_cli.guarded_execute",
                return_value=(1, Path("evidence")),
            ) as run,
            self.assertRaises(SystemExit) as exited,
        ):
            run_cli.main(
                [
                    "sentinel",
                    "--target",
                    ".",
                    "--variant",
                    "full",
                    "--advisory",
                    "--changed",
                    "src/module.py",
                ]
            )
        self.assertEqual(exited.exception.code, 1)
        self.assertEqual(run.call_args.kwargs["variant"], "full")
        self.assertTrue(run.call_args.kwargs["include_advisory"])
        self.assertEqual(run.call_args.kwargs["changed"], ("src/module.py",))


class GrainAdapterTests(unittest.TestCase):
    def test_adapter_selects_tracked_sources_and_uses_grain_exit_status(self) -> None:
        with (
            patch(
                "qa_toolkit.grain_adapter.tracked_regular_files",
                return_value=("source.py", "README.md", "data.json"),
            ),
            patch("qa_toolkit.grain_adapter.load_config", return_value="configuration") as load,
            patch("qa_toolkit.grain_adapter.run_checks", return_value=("finding",)) as checks,
            patch("qa_toolkit.grain_adapter.format_violations", return_value="reported\n"),
            patch("qa_toolkit.grain_adapter.determine_exit_code", return_value=1),
            patch("qa_toolkit.grain_adapter.Path.cwd", return_value=Path("/target")),
            self.assertRaises(SystemExit) as exited,
        ):
            grain_adapter.main(["--config", "grain.toml"])
        self.assertEqual(exited.exception.code, 1)
        load.assert_called_once_with(Path("grain.toml"))
        self.assertEqual(checks.call_args.args[0], ["source.py", "README.md"])


class PackageVersionTests(unittest.TestCase):
    def test_version_command_reports_success_usage_and_missing_package(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", ["package-version", "demo"]),
            patch("qa_toolkit.package_version.importlib.metadata.version", return_value="1.2.3"),
            contextlib.redirect_stdout(stdout),
        ):
            package_version.main()
        self.assertEqual(stdout.getvalue(), "1.2.3\n")

        for arguments, error in (
            (["package-version"], None),
            (
                ["package-version", "missing"],
                importlib.metadata.PackageNotFoundError(),
            ),
        ):
            stderr = io.StringIO()
            context = patch.object(sys, "argv", arguments)
            lookup = (
                patch("qa_toolkit.package_version.importlib.metadata.version", side_effect=error)
                if error
                else contextlib.nullcontext()
            )
            with (
                context,
                lookup,
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as raised,
            ):
                package_version.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertTrue(stderr.getvalue())


class CorpusCliTests(unittest.TestCase):
    def test_build_reports_digest_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "generated"
            with patch("qa_toolkit.corpus_cli.build_corpus", return_value=("abc", destination)):
                stdout, _stderr, code = _output(corpus_cli.main, ["--target", raw])
            self.assertIsNone(code)
            self.assertEqual(stdout, f"corpus\tabc\t{destination}\n")
            with patch("qa_toolkit.corpus_cli.build_corpus", side_effect=DeploymentError("bad")):
                _stdout, stderr, code = _output(corpus_cli.main, ["--target", raw])
            self.assertEqual(code, 2)
            self.assertIn("bad", stderr)


class EvidenceCliTests(unittest.TestCase):
    def test_show_export_and_bounded_failures(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "repo"
            target.mkdir()
            _git(Path(raw), "init", "-b", "main", str(target))
            evidence = target / ".git/qat/evidence/001"
            evidence.mkdir(parents=True)
            (evidence / "summary.json").write_text('{"exit_code": 0}', encoding="utf-8")

            stdout, _stderr, code = _output(evidence_cli.main, ["show", "--target", str(target)])
            self.assertIsNone(code)
            self.assertEqual(json.loads(stdout), {"exit_code": 0})

            destination = Path(raw) / "export"
            stdout, _stderr, code = _output(
                evidence_cli.main,
                ["export", "--target", str(target), "--destination", str(destination)],
            )
            self.assertIsNone(code)
            self.assertEqual(Path(stdout.strip()), destination)
            self.assertTrue((destination / "summary.json").is_file())

            cases = (
                ["export", "--target", str(target)],
                ["show", "--target", str(target), "--run", str(target)],
                ["export", "--target", str(target), "--destination", str(destination)],
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    _stdout, stderr, code = _output(evidence_cli.main, arguments)
                    self.assertEqual(code, 2)
                    self.assertIn("qat-evidence", stderr)

            (evidence / "summary.json").write_text("not json", encoding="utf-8")
            _stdout, _stderr, code = _output(evidence_cli.main, ["show", "--target", str(target)])
            self.assertEqual(code, 2)

    def test_latest_rejects_an_empty_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            (target / ".git/qat/evidence").mkdir(parents=True)
            with self.assertRaisesRegex(DeploymentError, "no evidence"):
                evidence_cli._latest(target)


class AgentCliTests(unittest.TestCase):
    def test_thread_names_are_bounded(self) -> None:
        self.assertEqual(
            agent_cli.thread_name("owner/repository", 7, "C01", "Build tools"),
            "[repository#7 C01] Build tools",
        )
        invalid = (
            ("repository", 1, "C01", "Title"),
            ("owner/repository", 0, "C01", "Title"),
            ("owner/repository", 1, "task", "Title"),
            ("owner/repository", 1, "C01", ""),
            ("owner/repository", 1, "C01", "x" * 200),
            ("owner/repository", 1, "C01", "bad\ntitle"),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                agent_cli.thread_name(*values)

    def test_main_covers_every_github_operation(self) -> None:
        client = MagicMock()
        client.repository.return_value = "owner/repo"
        for name in (
            "issue",
            "create_issue",
            "update_issue",
            "pull_request",
            "create_pull_request",
            "update_pull_request",
            "comment",
            "ready",
        ):
            getattr(client, name).return_value = _Record({"operation": name})
        client.checks.return_value = (_Record({"name": "quality"}),)
        body = Path("body.md")
        commands = (
            ["github", "repository", "--repository", "owner/repo"],
            ["github", "issue-view", "--repository", "owner/repo", "--number", "1"],
            [
                "github",
                "issue-create",
                "--repository",
                "owner/repo",
                "--title",
                "Title",
                "--body-file",
                str(body),
            ],
            [
                "github",
                "issue-update",
                "--repository",
                "owner/repo",
                "--number",
                "1",
                "--title",
                "Title",
                "--body-file",
                str(body),
            ],
            ["github", "pr-view", "--repository", "owner/repo", "--number", "2"],
            [
                "github",
                "pr-create",
                "--repository",
                "owner/repo",
                "--head",
                "topic",
                "--base",
                "main",
                "--title",
                "Title",
                "--body-file",
                str(body),
            ],
            [
                "github",
                "pr-update",
                "--repository",
                "owner/repo",
                "--number",
                "2",
                "--title",
                "Title",
                "--body-file",
                str(body),
            ],
            ["github", "pr-checks", "--repository", "owner/repo", "--number", "2"],
            [
                "github",
                "pr-comment",
                "--repository",
                "owner/repo",
                "--number",
                "2",
                "--body-file",
                str(body),
            ],
            ["github", "pr-ready", "--repository", "owner/repo", "--number", "2"],
        )
        with patch("qa_toolkit.agent_cli.GitHubClient.discover", return_value=client):
            for arguments in commands:
                with self.subTest(command=arguments[1]):
                    stdout, _stderr, code = _output(agent_cli.main, list(arguments))
                    self.assertIsNone(code)
                    self.assertIsNotNone(json.loads(stdout))

    def test_main_reports_missing_arguments_and_remote_errors(self) -> None:
        stdout, _stderr, code = _output(
            agent_cli.main,
            [
                "thread-name",
                "--repository",
                "owner/repo",
                "--issue",
                "1",
                "--task",
                "C01",
                "--title",
                "Title",
            ],
        )
        self.assertIsNone(code)
        self.assertIn("[repo#1 C01] Title", stdout)
        with patch(
            "qa_toolkit.agent_cli.GitHubClient.discover", side_effect=RuntimeError("offline")
        ):
            _stdout, stderr, code = _output(
                agent_cli.main, ["github", "repository", "--repository", "owner/repo"]
            )
        self.assertEqual(code, 2)
        self.assertIn("offline", stderr)
        for arguments in (
            ["github", "issue-view", "--repository", "owner/repo"],
            ["github", "issue-create", "--repository", "owner/repo", "--title", "Title"],
            [
                "github",
                "pr-create",
                "--repository",
                "owner/repo",
                "--head",
                "topic",
                "--base",
                "main",
                "--title",
                "Title",
            ],
        ):
            with patch("qa_toolkit.agent_cli.GitHubClient.discover", return_value=MagicMock()):
                _stdout, _stderr, code = _output(agent_cli.main, arguments)
            self.assertEqual(code, 2)


class ToolCliTests(unittest.TestCase):
    def test_list_status_fetch_and_update_surfaces(self) -> None:
        rows = (("demo", "1.0", "standalone"),)
        with patch("qa_toolkit.tool_cli.list_rows", return_value=rows):
            for extra in ([], ["--json"]):
                stdout, _stderr, code = _output(tool_cli.main, ["list", *extra])
                self.assertEqual(code, 0)
                self.assertTrue(stdout)

        standalone = SimpleNamespace(tool_id="one", version="1", environment="standalone")
        python = SimpleNamespace(tool_id="python", version="1", environment="python")
        duplicate = SimpleNamespace(tool_id="ruff", version="1", environment="python")
        with (
            patch("qa_toolkit.tool_cli.select_tools", return_value=(standalone,)),
            patch("qa_toolkit.tool_cli.tool_status", return_value=(True, "current")),
        ):
            for extra in ([], ["--json"]):
                stdout, _stderr, code = _output(tool_cli.main, ["status", "one", *extra])
                self.assertEqual(code, 0)
                self.assertTrue(stdout)
        with (
            patch("qa_toolkit.tool_cli.select_tools", return_value=(standalone,)),
            patch("qa_toolkit.tool_cli.tool_status", return_value=(False, "missing")),
        ):
            _stdout, _stderr, code = _output(tool_cli.main, ["status", "one"])
        self.assertEqual(code, 1)

        with (
            patch("qa_toolkit.tool_cli.select_tools", return_value=(standalone, python, duplicate)),
            patch("qa_toolkit.tool_cli.fetch_tool") as fetch,
        ):
            stdout, _stderr, code = _output(
                tool_cli.main, ["fetch", "one", "python", "ruff", "--force"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("current", stdout)

        with (
            patch("qa_toolkit.tool_cli.load_registry", return_value=(standalone,)),
            patch("qa_toolkit.tool_cli.fetch_tool"),
        ):
            _stdout, _stderr, code = _output(tool_cli.main, ["fetch", "--all"])
        self.assertEqual(code, 0)

        with patch("qa_toolkit.tool_cli.update_standalone") as update:
            _stdout, _stderr, code = _output(
                tool_cli.main,
                [
                    "update",
                    "demo",
                    "2",
                    "https://example.invalid/demo",
                    "a" * 64,
                    "--archive",
                    "raw",
                ],
            )
        self.assertEqual(code, 0)
        update.assert_called_once()

    def test_registry_errors_exit_two(self) -> None:
        for arguments in (["fetch"], ["fetch", "one", "--all"]):
            _stdout, stderr, code = _output(tool_cli.main, list(arguments))
            self.assertEqual(code, 2)
            self.assertIn("fetch requires", stderr)
        with patch("qa_toolkit.tool_cli.select_tools", side_effect=RegistryError("unknown")):
            _stdout, stderr, code = _output(tool_cli.main, ["status", "bad"])
        self.assertEqual(code, 2)
        self.assertIn("unknown", stderr)


class RepoCliTests(unittest.TestCase):
    def test_every_repository_operation_has_one_surface(self) -> None:
        profile = SimpleNamespace(name="demo")
        with (
            patch("qa_toolkit.repo_cli.validate_profile", return_value=profile),
            patch("qa_toolkit.repo_cli.profile_summary", return_value='{"name":"demo"}'),
        ):
            stdout, _stderr, code = _output(repo_cli.main, ["profile-validate", "demo"])
        self.assertIsNone(code)
        self.assertIn("demo", stdout)

        operations = (
            ("enroll", "enroll", {"current": True}, ["--adopt-hooks"]),
            ("sync", "sync", {"current": True}, ["--hard-reset", "--adopt-hooks"]),
        )
        for operation, symbol, result, extra in operations:
            with patch(f"qa_toolkit.repo_cli.{symbol}", return_value=result):
                stdout, _stderr, code = _output(repo_cli.main, [operation, ".", *extra])
            self.assertIsNone(code)
            self.assertTrue(json.loads(stdout)["current"])

        with patch("qa_toolkit.repo_cli.status", return_value={"current": True}):
            _stdout, _stderr, code = _output(repo_cli.main, ["status", "."])
        self.assertIsNone(code)
        with patch("qa_toolkit.repo_cli.status", return_value={"current": False}):
            _stdout, _stderr, code = _output(repo_cli.main, ["status", "."])
        self.assertEqual(code, 1)
        with patch("qa_toolkit.repo_cli.unenroll") as remove:
            _stdout, _stderr, code = _output(
                repo_cli.main,
                ["unenroll", ".", "--backup", "backup", "--hard-reset", "--purge-config"],
            )
        self.assertIsNone(code)
        remove.assert_called_once()

    def test_repository_errors_exit_two(self) -> None:
        with patch("qa_toolkit.repo_cli.status", side_effect=HookDeploymentError("foreign")):
            _stdout, stderr, code = _output(repo_cli.main, ["status", "."])
        self.assertEqual(code, 2)
        self.assertIn("foreign", stderr)


class HookCliTests(unittest.TestCase):
    def test_dispatch_status_and_toggle_surfaces(self) -> None:
        with (
            patch(
                "qa_toolkit.hook_cli.invocation_context",
                return_value=(Path("."), "git", "pre-commit"),
            ),
            patch("qa_toolkit.hook_cli.dispatch", return_value=1) as run,
        ):
            _stdout, _stderr, code = _output(
                hook_cli.main,
                ["dispatch", "--kind", "git", "--event", "pre-commit", "--", "arg"],
            )
        self.assertEqual(code, 1)
        self.assertEqual(run.call_args.args[-1], ("arg",))

        record: dict[str, object] = {"entries": []}
        with (
            patch("qa_toolkit.hook_cli.resolve_target", return_value=Path("/target")),
            patch("qa_toolkit.hook_cli._load", return_value=(Path("/central"), record)),
            patch("qa_toolkit.hook_cli.hook_status", return_value={"current": True}),
            patch("qa_toolkit.hook_cli.breaker_status", return_value={"open": False}),
            patch("qa_toolkit.hook_cli.proof_status", return_value={"current": True}),
        ):
            stdout, _stderr, code = _output(hook_cli.main, ["status", "."])
        self.assertIsNone(code)
        self.assertTrue(json.loads(stdout)["current"])

        with (
            patch("qa_toolkit.hook_cli.resolve_target", return_value=Path("/target")),
            patch("qa_toolkit.hook_cli._load", return_value=(Path("/central"), record)),
            patch(
                "qa_toolkit.hook_cli.set_enabled", return_value=("git:pre-commit:quality",)
            ) as toggle,
        ):
            stdout, _stderr, code = _output(
                hook_cli.main,
                ["disable", ".", "--kind", "git", "--event", "pre-commit", "--entry", "quality"],
            )
        self.assertIsNone(code)
        self.assertIn("quality", stdout)
        self.assertFalse(toggle.call_args.args[2])

    def test_hook_status_and_load_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            with self.assertRaises(HookDeploymentError):
                hook_cli._load(target)
            record = target / ".git/qat/deployment.json"
            record.parent.mkdir(parents=True)
            record.write_text("{}", encoding="utf-8")
            with self.assertRaises(HookDeploymentError):
                hook_cli._load(target)

        with patch("qa_toolkit.hook_cli.resolve_target", side_effect=DeploymentError("bad")):
            _stdout, stderr, code = _output(hook_cli.main, ["status", "."])
        self.assertEqual(code, 2)
        self.assertIn("bad", stderr)


class WorkCliTests(unittest.TestCase):
    def test_initialize_and_transition_surfaces(self) -> None:
        state = _Record({"status": "active"})
        package = SimpleNamespace(state=state)
        arguments = [
            "init",
            "work",
            "--repository",
            "owner/repo",
            "--issue",
            "1",
            "--kind",
            "feature",
            "--branch",
            "feat/work",
            "--base-branch",
            "main",
            "--base-sha",
            "a" * 40,
            "--plan-revision",
            "1",
            "--task",
            "C01",
            "--title",
            "Task",
            "--expected-parent",
            "b" * 40,
            "--subject",
            "feat(core): add work",
            "--allow-path",
            "src/**",
            "--validation-json",
            '["true"]',
            "--proof",
            "check",
            "--plan-file",
            "plan.md",
            "--task-file",
            "task.md",
            "--retire-after-finish",
        ]
        with patch("qa_toolkit.work_cli.initialize", return_value=package) as initialize:
            stdout, _stderr, code = _output(work_cli.main, arguments)
        self.assertIsNone(code)
        self.assertEqual(json.loads(stdout)["status"], "active")
        self.assertTrue(initialize.call_args.kwargs["retire_after_finish"])

        symbols = ("stage", "bind", "reconcile", "finish", "status")
        for symbol in symbols:
            arguments = [symbol, "work"]
            if symbol == "bind":
                arguments.extend(["--pull-request", "2"])
            if symbol == "reconcile":
                arguments.extend(["--pull-request", "2"])
            with patch(
                f"qa_toolkit.work_cli.{symbol}", return_value=_Record({"operation": symbol})
            ):
                stdout, _stderr, code = _output(work_cli.main, arguments)
            self.assertIsNone(code)
            self.assertEqual(json.loads(stdout)["operation"], symbol)

        with patch("qa_toolkit.work_cli.retire", return_value="c" * 40):
            stdout, _stderr, code = _output(work_cli.main, ["retire", "work"])
        self.assertIsNone(code)
        self.assertEqual(json.loads(stdout)["status"], "retired")

    def test_report_template_release_and_errors(self) -> None:
        with patch("qa_toolkit.work_cli.report", return_value="report\n"):
            stdout, _stderr, code = _output(work_cli.main, ["report", "work"])
        self.assertIsNone(code)
        self.assertEqual(stdout, "report\n")

        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "report.md"
            with patch("qa_toolkit.work_cli.report", return_value="report\n"):
                stdout, _stderr, code = _output(
                    work_cli.main, ["report", "work", "--output", str(output)]
                )
            self.assertIsNone(code)
            self.assertEqual(output.read_text(encoding="utf-8"), "report\n")
            self.assertEqual(Path(stdout.strip()), output)

            missing = Path(raw) / "central"
            with (
                patch("qa_toolkit.work_cli.toolkit_root", return_value=missing),
                self.assertRaisesRegex(WorkError, "unavailable"),
            ):
                work_cli._template("plan")
            template = missing / "library/work-packages/templates/plan.md"
            template.parent.mkdir(parents=True)
            template.write_text("", encoding="utf-8")
            with (
                patch("qa_toolkit.work_cli.toolkit_root", return_value=missing),
                self.assertRaisesRegex(WorkError, "empty"),
            ):
                work_cli._template("plan")

        stdout, _stderr, code = _output(work_cli.main, ["template", "plan"])
        self.assertIsNone(code)
        self.assertTrue(stdout)
        with patch(
            "qa_toolkit.work_cli.calculate_release", return_value=_Record({"version": "1.0.0"})
        ):
            stdout, _stderr, code = _output(
                work_cli.main,
                ["release", "--base-version", "0.1.0", "--message", "feat(core): add work"],
            )
        self.assertIsNone(code)
        self.assertEqual(json.loads(stdout)["version"], "1.0.0")
        with patch("qa_toolkit.work_cli.status", side_effect=WorkError("bad state")):
            _stdout, stderr, code = _output(work_cli.main, ["status", "work"])
        self.assertEqual(code, 2)
        self.assertIn("bad state", stderr)


if __name__ == "__main__":
    unittest.main()
