"""Boundary tests for central Python configuration resolution."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from test_python_tools import FIXTURE, _git

from qa_toolkit.config import load_consumer
from qa_toolkit.models import PydoclintSettings, PylintSettings, PythonException, RuffSettings
from qa_toolkit.python_tools import (
    PythonToolError,
    _atomic_configs,
    _import_linter_gate,
    _resolve_pydoclint,
    _resolve_pylint,
    _resolve_ruff,
    _stricter,
    _string_list,
    _table,
    _toml_value,
    _validate_scope,
    owned_consumer_command,
)


class PythonResolverBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name) / "consumer"
        shutil.copytree(FIXTURE, self.target)
        _git(self.target.parent, "init", "-b", "main", str(self.target))
        _git(self.target, "config", "user.name", "QA Toolkit")
        _git(self.target, "config", "user.email", "qat@example.invalid")
        _git(self.target, "add", ".")
        _git(self.target, "commit", "-m", "test(repo): create Python boundary target")
        self.consumer = load_consumer(self.target)

    def test_scope_rejects_missing_paths_and_unmatched_exceptions(self) -> None:
        assert self.consumer.python.ruff is not None
        missing = replace(
            self.consumer,
            python=replace(
                self.consumer.python,
                ruff=replace(self.consumer.python.ruff, paths=("missing",)),
            ),
        )
        with self.assertRaisesRegex(PythonToolError, "match no tracked input"):
            _validate_scope(missing, self.target)
        exception = replace(self.consumer.python.exceptions[0], path="missing/**")
        unmatched = replace(
            self.consumer,
            python=replace(self.consumer.python, exceptions=(exception,)),
        )
        with self.assertRaisesRegex(PythonToolError, "match no tracked regular file"):
            _validate_scope(unmatched, self.target)

    def test_central_config_primitives_fail_closed(self) -> None:
        with self.assertRaisesRegex(PythonToolError, "not a table"):
            _table({"lint": []}, "lint")
        with self.assertRaisesRegex(PythonToolError, "array of strings"):
            _string_list({"select": [1]}, "select", "selection")
        with self.assertRaisesRegex(PythonToolError, "no central threshold"):
            _stricter(3, {"limit": True}, "limit", "threshold")
        with self.assertRaisesRegex(PythonToolError, "weaker"):
            _stricter(5, {"limit": 4}, "limit", "threshold")
        with self.assertRaisesRegex(PythonToolError, "unsupported central TOML value"):
            _toml_value(("unsupported",))

    def test_ruff_resolution_rejects_repetition_removal_and_inactive_exceptions(self) -> None:
        central = (
            "[lint]\n"
            'select = ["E", "S"]\n'
            'ignore = ["S603"]\n'
            "[lint.mccabe]\n"
            "max-complexity = 10\n"
            "[lint.pylint]\n"
            "max-args = 8\n"
            "max-returns = 6\n"
            "[lint.per-file-ignores]\n"
        )
        assert self.consumer.python.ruff is not None
        for settings, message in (
            (RuffSettings(extend_select=("E",)), "repeats central selectors"),
            (RuffSettings(enforce=("ANN401",)), "central ignored rules"),
        ):
            with self.subTest(message=message):
                candidate = replace(
                    self.consumer,
                    python=replace(self.consumer.python, ruff=settings, exceptions=()),
                )
                with self.assertRaisesRegex(PythonToolError, message):
                    _resolve_ruff(central, candidate)
        inactive_exception = replace(self.consumer.python.exceptions[0], rule="S603")
        candidate = replace(
            self.consumer,
            python=replace(
                self.consumer.python,
                ruff=RuffSettings(),
                exceptions=(inactive_exception,),
            ),
        )
        with self.assertRaisesRegex(PythonToolError, "is not active"):
            _resolve_ruff(central, candidate)
        unsupported = cast(
            PythonException,
            SimpleNamespace(tool="mypy", rule="S603", path="tests/**"),
        )
        candidate = replace(
            self.consumer,
            python=replace(self.consumer.python, ruff=RuffSettings(), exceptions=(unsupported,)),
        )
        with self.assertRaisesRegex(PythonToolError, "unsupported Python exception"):
            _resolve_ruff(central, candidate)

    def test_pylint_and_pydoclint_allow_only_stricter_values(self) -> None:
        pylint = (
            "[tool.pylint.messages_control]\n"
            'enable = ["invalid-name"]\n'
            "[tool.pylint.similarities]\n"
            "min-similarity-lines = 6\n"
        )
        self.assertEqual(_resolve_pylint(pylint, None), pylint)
        with self.assertRaisesRegex(PythonToolError, "repeats central rules"):
            _resolve_pylint(pylint, PylintSettings(enable=("invalid-name",)))
        resolved = _resolve_pylint(pylint, PylintSettings(min_similarity_lines=5))
        self.assertIn('"min-similarity-lines" = 5', resolved)
        pydoclint = "[tool.pydoclint]\nskip-checking-short-docstrings = true\n"
        self.assertEqual(_resolve_pydoclint(pydoclint, None), pydoclint)
        with self.assertRaisesRegex(PythonToolError, "tightened to false"):
            _resolve_pydoclint(
                pydoclint,
                PydoclintSettings(skip_checking_short_docstrings=True),
            )
        with self.assertRaisesRegex(PythonToolError, "tightened to true"):
            _resolve_pydoclint(pydoclint, PydoclintSettings(check_class_attributes=False))

    def test_import_linter_is_conditional_tracked_and_regular(self) -> None:
        project = self.target / "pyproject.toml"
        original = project.read_text(encoding="utf-8")
        without = original.split("[tool.importlinter]", maxsplit=1)[0]
        project.write_text(without, encoding="utf-8")
        self.assertIsNone(_import_linter_gate(self.target, self.consumer))
        project.write_text("tool = []\n", encoding="utf-8")
        with self.assertRaisesRegex(PythonToolError, "tool settings must be a table"):
            _import_linter_gate(self.target, self.consumer)
        invalid = (
            ("[tool.importlinter]\n", "non-empty table"),
            ('[tool.importlinter]\nroot_package = "app"\n', "direction rules"),
        )
        for content, message in invalid:
            project.write_text(content, encoding="utf-8")
            with self.subTest(message=message), self.assertRaisesRegex(PythonToolError, message):
                _import_linter_gate(self.target, self.consumer)
        project.unlink()
        project.symlink_to(self.target / ".qat.toml")
        with self.assertRaisesRegex(PythonToolError, "irregular"):
            _import_linter_gate(self.target, self.consumer)

    def test_untracked_import_settings_and_atomic_restore_are_rejected(self) -> None:
        project = self.target / "untracked"
        project.mkdir()
        (project / "pyproject.toml").write_text(
            '[tool.importlinter]\nroot_package = "app"\n'
            '[[tool.importlinter.contracts]]\nname = "direction"\n'
            'type = "layers"\nlayers = ["app"]\n',
            encoding="utf-8",
        )
        consumer = replace(
            self.consumer,
            python=replace(self.consumer.python, project=Path("untracked")),
        )
        with self.assertRaisesRegex(PythonToolError, "tracked pyproject"):
            _import_linter_gate(self.target, consumer)

        destination = self.target / ".qat/generated/python"
        destination.mkdir(parents=True)
        (destination / "old.toml").write_text("old", encoding="utf-8")
        real_replace = os.replace

        def fail_stage(source: str | Path, target: str | Path) -> None:
            if Path(source).name.startswith("python-"):
                raise OSError("forced replacement failure")
            real_replace(source, target)

        with (
            patch("qa_toolkit.python_tools.os.replace", side_effect=fail_stage),
            self.assertRaisesRegex(OSError, "forced replacement failure"),
        ):
            _atomic_configs(destination, {"ruff": "line-length = 100\n"})
        self.assertEqual((destination / "old.toml").read_text(encoding="utf-8"), "old")

    def test_owned_command_parser_handles_empty_uv_separator_and_options(self) -> None:
        cases = {
            (): None,
            ("uv", "sync"): None,
            ("uv", "run", "--", "ruff", "check"): "ruff",
            ("uv", "run", "--with", "thing", "pytest"): "pytest",
            ("uv", "run", "--frozen", "ordinary-command"): None,
        }
        for argv, expected in cases.items():
            with self.subTest(argv=argv):
                self.assertEqual(owned_consumer_command(argv), expected)


if __name__ == "__main__":
    unittest.main()
