"""Boundary tests for commit selection and managed message policy."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_hooks import _target

from qa_toolkit.commit_cli import (
    CommitCheckError,
    _cog,
    _git,
    _message_file,
    _revisions,
    check_messages,
    main,
)
from qa_toolkit.commit_policy import render, structural_findings, terminology_findings

ROOT = Path(__file__).parents[1]


class CommitSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = _target(Path(temporary.name))

    def test_git_selection_failures_are_classified(self) -> None:
        with self.assertRaisesRegex(CommitCheckError, "Git selection failed"):
            _git(self.target / "missing", "status")
        for selection in ("", "bad\nrevision", "x" * 513):
            with (
                self.subTest(selection=selection[:20]),
                self.assertRaisesRegex(CommitCheckError, "invalid commit selection"),
            ):
                _revisions(self.target, selection, False)

    def test_revision_and_range_selection_retain_complete_messages(self) -> None:
        one = _revisions(self.target, "HEAD", False)
        ranged = _revisions(self.target, "HEAD", True)
        self.assertEqual(len(one), 1)
        self.assertEqual(one, ranged)
        self.assertIn("create disposable hook target", one[0][1])

    def test_message_file_must_be_small_regular_and_git_local(self) -> None:
        message = self.target / ".git/COMMIT_EDITMSG"
        message.write_text("test(commits): read local message\n", encoding="utf-8")
        self.assertEqual(
            _message_file(self.target, Path(".git/COMMIT_EDITMSG"))[0][0], "COMMIT_EDITMSG"
        )
        outside = self.target / "message"
        outside.write_text("test(commits): reject outside file\n", encoding="utf-8")
        with self.assertRaisesRegex(CommitCheckError, "below target .git"):
            _message_file(self.target, outside)
        link = self.target / ".git/message-link"
        link.symlink_to(message)
        with self.assertRaisesRegex(CommitCheckError, "regular file"):
            _message_file(self.target, link)
        message.write_bytes(b"x" * 1_048_577)
        with self.assertRaisesRegex(CommitCheckError, "exceeds one MiB"):
            _message_file(self.target, message)


class CocogittoBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = _target(Path(temporary.name))

    def test_unclassified_and_execution_failures_are_errors(self) -> None:
        for result, message in (
            (SimpleNamespace(returncode=2), "unclassified status"),
            (OSError("missing"), "cannot execute Cocogitto"),
        ):
            with self.subTest(message=message):
                effect = result if isinstance(result, OSError) else None
                with (
                    patch("qa_toolkit.commit_cli.select_tools", return_value=(object(),)),
                    patch("qa_toolkit.commit_cli.executable_path", return_value=Path("/bin/cog")),
                    patch("qa_toolkit.commit_cli._git", return_value=""),
                    patch(
                        "qa_toolkit.commit_cli.subprocess.run",
                        side_effect=effect,
                        return_value=None if effect else result,
                    ),
                    self.assertRaisesRegex(CommitCheckError, message),
                ):
                    _cog(self.target, ROOT, "test(scope): validate message")

    def test_lifecycle_is_skipped_and_findings_fail(self) -> None:
        with patch("qa_toolkit.commit_cli._cog") as cog:
            self.assertEqual(
                check_messages(self.target, ROOT, (("merge", "Merge branch 'topic'"),)), 0
            )
            cog.assert_not_called()
        output = io.StringIO()
        with (
            patch("qa_toolkit.commit_cli._cog", return_value=0),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(check_messages(self.target, ROOT, (("bad", "update"),)), 1)
        self.assertIn("QCM001", output.getvalue())
        with patch("qa_toolkit.commit_cli._cog", return_value=1):
            self.assertEqual(
                check_messages(self.target, ROOT, (("cog", "test(scope): validate message"),)),
                1,
            )


class CommitPolicyBoundaryTests(unittest.TestCase):
    def test_structural_diagnostics_cover_each_owned_rule(self) -> None:
        cases = {
            "unknown(scope): perform action": "QCM002",
            "feat: perform action": "QCM003",
            "feat(scope): " + "x" * 73: "QCM004",
            "feat(scope): Add behavior": "QCM005",
            "feat(scope): added behavior": "QCM006",
            "feat(scope): update": "QCM007",
        }
        for message, code in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, {item.code for item in structural_findings(message)})
        rendered = render(structural_findings("update"), "HEAD")
        self.assertIn("HEAD: QCM001 error", rendered)

    def test_shared_and_consumer_terminology_are_reported_once(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = _target(Path(temporary.name))
        declaration = target / ".qat.toml"
        declaration.write_text(
            declaration.read_text(encoding="utf-8").replace(
                "[vocabulary]\nadditions = []\nallowances = []",
                '[vocabulary]\nadditions = []\nallowances = []\nfile = ".qat-vocabulary.toml"',
            ),
            encoding="utf-8",
        )
        (target / ".qat-vocabulary.toml").write_text(
            'schema_version = 1\n[terminology]\nrejected = ["robust"]\n'
            '[terminology.replacements]\nutilize = "use"\n',
            encoding="utf-8",
        )
        findings = terminology_findings(target, "feat(scope): utilize robust adapter", ROOT)
        self.assertEqual([item.code for item in findings], ["QCT002", "QCT002"])
        self.assertTrue(any("use" in item.message for item in findings))


class CommitMainTests(unittest.TestCase):
    def test_main_selects_message_range_and_commit_modes(self) -> None:
        for arguments, helper in (
            (["--message-file", ".git/COMMIT_EDITMSG"], "_message_file"),
            (["--range", "main..HEAD"], "_revisions"),
            (["--commit", "HEAD"], "_revisions"),
        ):
            with (
                self.subTest(arguments=arguments),
                self.assertRaises(SystemExit) as exited,
                patch("qa_toolkit.commit_cli.resolve_target", return_value=Path("/target")),
                patch("qa_toolkit.commit_cli.status", return_value={"current": True}),
                patch(
                    "qa_toolkit.commit_cli.load_consumer",
                    return_value=SimpleNamespace(profile="test"),
                ),
                patch(
                    "qa_toolkit.commit_cli.load_profile",
                    return_value=SimpleNamespace(tools=("cocogitto",)),
                ),
                patch(f"qa_toolkit.commit_cli.{helper}", return_value=(("one", "message"),)),
                patch("qa_toolkit.commit_cli.check_messages", return_value=0),
            ):
                main(arguments)
            self.assertEqual(exited.exception.code, 0)

    def test_main_reports_stale_or_unowned_configuration(self) -> None:
        for current, tools, message in (
            (False, ("cocogitto",), "deployment is stale"),
            (True, (), "does not own Cocogitto"),
        ):
            output = io.StringIO()
            with (
                patch("qa_toolkit.commit_cli.resolve_target", return_value=Path("/target")),
                patch("qa_toolkit.commit_cli.status", return_value={"current": current}),
                patch(
                    "qa_toolkit.commit_cli.load_consumer",
                    return_value=SimpleNamespace(profile="test"),
                ),
                patch(
                    "qa_toolkit.commit_cli.load_profile", return_value=SimpleNamespace(tools=tools)
                ),
                contextlib.redirect_stderr(output),
                self.assertRaises(SystemExit) as exited,
            ):
                main(["--commit", "HEAD"])
            self.assertEqual(exited.exception.code, 2)
            self.assertIn(message, output.getvalue())


if __name__ == "__main__":
    unittest.main()
