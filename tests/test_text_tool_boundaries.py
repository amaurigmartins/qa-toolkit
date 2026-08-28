"""Boundary tests for tracked text selection and finding normalization."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import tokenize
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qa_toolkit.text_tools import (
    TextToolError,
    _Alert,
    _Alias,
    _allowance,
    _directive_view,
    _map_cspell_output,
    _mapped_path,
    _parse_alerts,
    _python_docstring_view,
    _resolve_acronyms,
    _run,
    _source_paths,
    _stage_view,
    main,
    run_cspell,
    run_vale,
)


class TextSourceBoundaryTests(unittest.TestCase):
    def test_source_selection_reports_classified_files_and_wraps_read_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            generated = target / "docs/generated/README.md"
            generated.parent.mkdir(parents=True)
            generated.write_text("generated", encoding="utf-8")
            output = io.StringIO()
            with (
                patch(
                    "qa_toolkit.text_tools.tracked_regular_files",
                    return_value=("docs/generated/README.md",),
                ),
                contextlib.redirect_stderr(output),
            ):
                self.assertEqual(_source_paths(target, frozenset({".md"})), ())
            self.assertIn("source-decision", output.getvalue())
            with (
                patch("qa_toolkit.text_tools.load_corpus", return_value=object()),
                patch("qa_toolkit.text_tools.tracked_regular_files", return_value=("README.md",)),
                patch.object(Path, "read_text", side_effect=UnicodeError("bad encoding")),
                self.assertRaisesRegex(TextToolError, "cannot read tracked text"),
            ):
                _source_paths(target, frozenset({".md"}))

    def test_stage_and_directive_views_cover_plain_python_and_license_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            stage = Path(directory) / "stage"
            target.mkdir()
            stage.mkdir()
            python = "TOKEN = 'ordinary string'\n"
            (target / "module.py").write_text(python, encoding="utf-8")
            self.assertEqual(_stage_view(target, "module.py", stage), ("module.py", None, python))
            (target / "NOTICE").write_text("Plain notice.\n", encoding="utf-8")
            name, alias, _ = _stage_view(target, "NOTICE", stage)
            self.assertTrue(Path(name).is_file())
            self.assertEqual(alias, _Alias("NOTICE", (0,)))
            self.assertEqual(_directive_view("NOTICE", "plain"), "plain")
            self.assertNotIn("ordinary string", _python_docstring_view(python))

    def test_unsupported_python_docstring_token_is_explicit(self) -> None:
        token = tokenize.TokenInfo(tokenize.STRING, "not-literal", (1, 0), (1, 11), "")
        with (
            patch("qa_toolkit.text_tools.tokenize.generate_tokens", return_value=(token,)),
            self.assertRaisesRegex(TextToolError, "unsupported Python docstring literal"),
        ):
            _python_docstring_view("'docstring'\n")

    def test_process_errors_are_normalized(self) -> None:
        with (
            patch("qa_toolkit.text_tools.subprocess.run", side_effect=OSError("missing")),
            self.assertRaisesRegex(TextToolError, "cannot execute vale"),
        ):
            _run(("vale", "file"), Path("."))


class FindingMappingBoundaryTests(unittest.TestCase):
    def test_paths_are_relative_or_declared_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            alias = _Alias("source.tex", (0,))
            staged = target / "stage.md"
            self.assertEqual(
                _mapped_path(str(staged), target, {str(staged): alias}), ("source.tex", alias)
            )
            self.assertEqual(_mapped_path("README.md", target, {}), ("README.md", None))
            with self.assertRaisesRegex(TextToolError, "unknown input path"):
                _mapped_path("/outside/file.md", target, {})

    def test_vale_json_rejects_each_malformed_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            cases = (
                ("{", "invalid JSON"),
                ("[]", "invalid finding document"),
                ('{"README.md": [1]}', "invalid finding"),
                ('{"README.md": [{"Line": 0, "Span": [1]}]}', "invalid finding location"),
                (
                    '{"README.md": [{"Line": 1, "Span": [1], "Check": 1, '
                    '"Severity": "error", "Match": "x", "Message": "m"}]}',
                    "incomplete finding",
                ),
            )
            for value, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(TextToolError, message):
                    _parse_alerts(value, target, {})
            alias = _Alias("source.tex", ())
            value = json.dumps(
                {
                    str(target / "stage.md"): [
                        {
                            "Line": 1,
                            "Span": [1],
                            "Check": "rule",
                            "Severity": "error",
                            "Match": "x",
                            "Message": "message",
                        }
                    ]
                }
            )
            with self.assertRaisesRegex(TextToolError, "exceeds the staged source map"):
                _parse_alerts(value, target, {str(target / "stage.md"): alias})

    def test_allowances_and_acronyms_are_bounded(self) -> None:
        allowed = _Alert("docs/source.md", 1, 1, "rule", "error", "Term", "message")
        self.assertTrue(
            _allowance(
                allowed,
                {"allowances": [{"term": "term", "paths": ["**/*.md"]}]},
            )
        )
        self.assertFalse(_allowance(allowed, {"allowances": [None, {"term": 1}]}))
        acronym = _Alert(
            "README.md",
            1,
            1,
            "STECode.UnexpandedAcronyms",
            "warning",
            "RLS",
            "spell out",
        )
        retained = _resolve_acronyms((acronym,), {"README.md": "RLS applies."}, {})
        self.assertEqual(retained, (acronym,))
        removed = _resolve_acronyms(
            (acronym,),
            {"README.md": "RLS applies."},
            {"acronyms": ["RLS"], "accepted": [1]},
        )
        self.assertEqual(removed, ())
        ordinary = _Alert("README.md", 1, 1, "other", "warning", "RLS", "message")
        self.assertEqual(_resolve_acronyms((ordinary,), {}, {}), (ordinary,))

    def test_cspell_output_maps_aliases_and_preserves_other_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            staged = target / "stage.md"
            aliases = {str(staged): _Alias("source.tex", (3,))}
            output = f"{staged}:1:2 - Unknown word\nsummary\n"
            self.assertEqual(
                _map_cspell_output(output, target, aliases),
                "source.tex:1:5 - Unknown word\nsummary\n",
            )
            with self.assertRaisesRegex(TextToolError, "exceeds the staged source map"):
                _map_cspell_output(f"{staged}:2:1 - Unknown\n", target, aliases)


class TextCommandBoundaryTests(unittest.TestCase):
    def test_empty_selection_passes_without_spawning_tools(self) -> None:
        with (
            patch("qa_toolkit.text_tools.resolve_target", return_value=Path("/target")),
            patch(
                "qa_toolkit.text_tools.build_corpus",
                return_value=("digest", Path("/generated")),
            ),
            patch(
                "qa_toolkit.text_tools.load_consumer",
                return_value=SimpleNamespace(
                    text=SimpleNamespace(prose=SimpleNamespace(include=(), exclude=()))
                ),
            ),
            patch("qa_toolkit.text_tools._source_paths", return_value=()),
        ):
            self.assertEqual(run_vale(Path(".")), 0)
            self.assertEqual(run_cspell(Path(".")), 0)

    def test_unclassified_tool_statuses_are_execution_errors(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name)
        (target / ".git/qat").mkdir(parents=True)
        (target / "README.md").write_text("text\n", encoding="utf-8")
        generated = target / "generated"
        (generated / "vale").mkdir(parents=True)
        (generated / "resolved.json").write_text("{}", encoding="utf-8")
        common = (
            patch("qa_toolkit.text_tools.resolve_target", return_value=target),
            patch("qa_toolkit.text_tools.build_corpus", return_value=("digest", generated)),
            patch(
                "qa_toolkit.text_tools.load_consumer",
                return_value=SimpleNamespace(
                    text=SimpleNamespace(prose=SimpleNamespace(include=(), exclude=()))
                ),
            ),
            patch("qa_toolkit.text_tools._source_paths", return_value=("README.md",)),
            patch("qa_toolkit.text_tools.select_tools", return_value=(object(),)),
            patch("qa_toolkit.text_tools.executable_path", return_value=Path("/tool")),
        )
        with contextlib.ExitStack() as stack:
            for manager in common:
                stack.enter_context(manager)
            stack.enter_context(
                patch(
                    "qa_toolkit.text_tools._run",
                    return_value=SimpleNamespace(returncode=2, stdout="", stderr="error\n"),
                )
            )
            with self.assertRaisesRegex(TextToolError, "Vale exited with unclassified status"):
                run_vale(target)
        with contextlib.ExitStack() as stack:
            for manager in common:
                stack.enter_context(manager)
            stack.enter_context(
                patch(
                    "qa_toolkit.text_tools._run",
                    return_value=SimpleNamespace(
                        returncode=2,
                        stdout="line\n",
                        stderr="error\n",
                    ),
                )
            )
            with self.assertRaisesRegex(TextToolError, "CSpell exited with unclassified status"):
                run_cspell(target)

    def test_main_dispatches_and_normalizes_errors(self) -> None:
        with (
            patch("qa_toolkit.text_tools.run_vale", return_value=1),
            self.assertRaises(SystemExit) as exited,
        ):
            main(["vale", "--advisory"])
        self.assertEqual(exited.exception.code, 1)
        with (
            patch("qa_toolkit.text_tools.run_cspell", side_effect=TextToolError("failed")),
            self.assertRaises(SystemExit) as exited,
        ):
            main(["cspell"])
        self.assertEqual(exited.exception.code, 2)
        with self.assertRaises(SystemExit) as exited:
            main(["cspell", "--advisory"])
        self.assertEqual(exited.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
