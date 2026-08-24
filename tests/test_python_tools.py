"""Acceptance tests for centrally owned Python tools and consumer additions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from qa_toolkit.ast_grep import resolve_ast_grep
from qa_toolkit.config import load_consumer
from qa_toolkit.deployment import enroll, sync
from qa_toolkit.paths import toolkit_root
from qa_toolkit.python_tools import PythonToolError, owned_consumer_command, resolve_python
from qa_toolkit.runner import RunnerError, execute, resolve_plan

FIXTURE = Path(__file__).parent / "fixtures" / "python-consumer"


def _git(target: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(target), *arguments],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
    )


class PythonToolAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.target = Path(self.temporary.name) / "consumer"
        shutil.copytree(FIXTURE, self.target)
        (self.target / "scripts/test-live.sh").chmod(0o755)
        _git(self.target.parent, "init", "-b", "main", str(self.target))
        _git(self.target, "config", "user.name", "QA Toolkit")
        _git(self.target, "config", "user.email", "qat@example.invalid")
        _git(self.target, "add", ".")
        _git(self.target, "commit", "-m", "test(repo): create disposable target")
        enroll(self.target, toolkit_root())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_overlays_generate_one_config_and_conditional_gates(self) -> None:
        consumer = load_consumer(self.target)
        resolution = resolve_python(self.target, toolkit_root(), consumer)
        ruff = tomllib.loads(resolution.configurations["ruff"].read_text(encoding="utf-8"))
        pylint = tomllib.loads(resolution.configurations["pylint"].read_text(encoding="utf-8"))
        pydoclint = tomllib.loads(
            resolution.configurations["pydoclint"].read_text(encoding="utf-8")
        )

        self.assertEqual(ruff["lint"]["mccabe"]["max-complexity"], 8)
        self.assertEqual(ruff["lint"]["pylint"]["max-returns"], 4)
        self.assertIn("S603", ruff["lint"]["per-file-ignores"]["tests/**"])
        self.assertEqual(pylint["tool"]["pylint"]["similarities"]["min-similarity-lines"], 5)
        self.assertFalse(pydoclint["tool"]["pydoclint"]["skip-checking-short-docstrings"])
        self.assertTrue(pydoclint["tool"]["pydoclint"]["check-class-attributes"])
        self.assertEqual(
            [gate.identifier for gate in resolution.gates], ["python-import-directions"]
        )
        self.assertEqual(len(resolution.digests), 8)
        python_paths = resolution.environment["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(Path(python_paths[0]), toolkit_root() / "src")
        self.assertIn(str(self.target), python_paths)

        ast = resolve_ast_grep(consumer, target=self.target, root=toolkit_root())
        self.assertEqual(
            [gate.identifier for gate in ast.gates],
            ["consumer-ast-grep-tests", "consumer-ast-grep-scan"],
        )
        self.assertEqual(ast.rule_ids, ("consumer-no-print",))

        plan = resolve_plan(
            self.target,
            toolkit_root(),
            "sentinel",
            variant=None,
            include_advisory=False,
            changed=(),
        )
        identifiers = [gate.identifier for gate in plan]
        for identifier in (
            "python-import-directions",
            "consumer-ast-grep-tests",
            "consumer-ast-grep-scan",
            "consumer-live-proof",
        ):
            self.assertEqual(identifiers.count(identifier), 1)
        self.assertEqual(identifiers.count("python-tests"), 1)

    def test_consumer_cannot_run_a_centrally_owned_tool(self) -> None:
        for argv in (
            ("ruff", "check", "."),
            ("uv", "run", "--frozen", "ruff", "check", "."),
            ("uv", "run", "--project", ".", "lint-imports"),
        ):
            with self.subTest(argv=argv):
                self.assertIsNotNone(owned_consumer_command(argv))
        self.assertIsNone(owned_consumer_command(("scripts/test-live.sh",)))

    def test_disposable_target_passes_central_check_and_sentinel(self) -> None:
        tracked = {
            path: (self.target / path).read_bytes()
            for path in subprocess.run(
                ["git", "-C", str(self.target), "ls-files"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            ).stdout.splitlines()
            if (self.target / path).is_file()
        }
        check_exit, check_evidence = execute(self.target, "check", root=toolkit_root())
        self._assert_success(check_exit, check_evidence)
        sentinel_exit, sentinel_evidence = execute(self.target, "sentinel", root=toolkit_root())
        self._assert_success(sentinel_exit, sentinel_evidence)
        self.assertEqual(
            tracked,
            {path: (self.target / path).read_bytes() for path in tracked},
        )

    def _assert_success(self, exit_code: int, evidence: Path) -> None:
        if exit_code == 0:
            return
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        details: list[str] = []
        for result in summary["results"]:
            if result["result"] != "pass":
                stdout = (evidence / result["stdout"]).read_text(encoding="utf-8")
                stderr = (evidence / result["stderr"]).read_text(encoding="utf-8")
                details.append(f"{result['id']} ({result['result']}):\n{stdout}{stderr}")
        self.fail("\n".join(details))

    def test_weaker_threshold_is_rejected_without_rewriting_consumer_files(self) -> None:
        declaration = self.target / ".qat.toml"
        original = declaration.read_bytes()
        declaration.write_text(
            declaration.read_text(encoding="utf-8").replace(
                "max_complexity = 8", "max_complexity = 11"
            ),
            encoding="utf-8",
        )
        weakened = declaration.read_bytes()
        _git(self.target, "add", ".qat.toml")
        _git(self.target, "commit", "-m", "test(policy): weaken threshold")
        sync(self.target, toolkit_root())
        with self.assertRaisesRegex(PythonToolError, "weaker"):
            resolve_python(self.target, toolkit_root(), load_consumer(self.target))
        self.assertNotEqual(weakened, original)
        self.assertEqual(declaration.read_bytes(), weakened)

    def test_raw_consumer_gate_is_rejected_by_the_resolved_plan(self) -> None:
        declaration = self.target / ".qat.toml"
        declaration.write_text(
            declaration.read_text(encoding="utf-8")
            + """

[[gates]]
id = "copied-ruff"
phase = "check"
argv = ["uv", "run", "--frozen", "ruff", "check", "."]
triggers = ["**"]
timeout = 60
severity = "blocking"
variants = []
finding_exit_codes = [1]
execution_error_exit_codes = [2]
""",
            encoding="utf-8",
        )
        _git(self.target, "add", ".qat.toml")
        _git(self.target, "commit", "-m", "test(policy): copy central Ruff action")
        sync(self.target, toolkit_root())

        with self.assertRaisesRegex(RunnerError, "central ownership of ruff"):
            resolve_plan(
                self.target,
                toolkit_root(),
                "check",
                variant=None,
                include_advisory=False,
                changed=(),
            )


if __name__ == "__main__":
    unittest.main()
