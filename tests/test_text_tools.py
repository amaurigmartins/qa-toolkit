"""Real-engine acceptance tests for tracked prose and spelling inputs."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from test_deployment import _git

from qa_toolkit.deployment import enroll, sync
from qa_toolkit.text_tools import run_cspell, run_vale

ROOT = Path(__file__).parents[1]


def _consumer(parent: Path) -> Path:
    target = parent / "consumer"
    target.mkdir()
    _git(parent, "init", "-b", "main", str(target))
    (target / ".qat.toml").write_text(
        """schema_version = 1
profile = "disposable-documentation"
native_configurations = []
protected_paths = []

[vocabulary]
file = ".qat-vocabulary.toml"
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
""",
        encoding="utf-8",
    )
    (target / ".qat-vocabulary.toml").write_text(
        """schema_version = 1

[terminology]
accepted = ["Gridform"]
rejected = ["robust"]

[terminology.replacements]

[[allowances]]
term = "robust"
paths = ["quoted.md"]
reason = "The fixture checks one bounded quoted spelling."
""",
        encoding="utf-8",
    )
    (target / "README.md").write_text("Gridform reads the input data.\n", encoding="utf-8")
    _git(target, "add", "-A")
    _git(
        target,
        "-c",
        "user.name=QA Toolkit Test",
        "-c",
        "user.email=qa-toolkit@example.invalid",
        "commit",
        "-m",
        "test(repo): create text consumer",
    )
    enroll(target, ROOT)
    return target


class TextToolAcceptanceTests(unittest.TestCase):
    def test_cspell_uses_the_resolved_repository_vocabulary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _consumer(Path(directory))
            self.assertEqual(run_cspell(target), 0)
            (target / "README.md").write_text(
                "Gridform reads a misspeled input.\n", encoding="utf-8"
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_cspell(target)

            self.assertEqual(code, 1)
            self.assertIn("misspeled", output.getvalue())

    def test_vale_applies_bounded_allowances_and_advisory_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _consumer(Path(directory))
            (target / "quoted.md").write_text("A robust solver returns one.\n", encoding="utf-8")
            _git(target, "add", "-A")
            self.assertEqual(run_vale(target), 0)
            (target / "other.md").write_text("A robust solver returns one.\n", encoding="utf-8")
            _git(target, "add", "-A")
            self.assertEqual(run_vale(target), 1)
            (target / "other.md").write_text("Let's unpack the input.\n", encoding="utf-8")

            self.assertEqual(run_vale(target, advisory=True), 1)

    def test_vale_maps_markdown_latex_python_and_julia_reader_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _consumer(Path(directory))
            (target / "README.md").write_text(
                "The business rule selects the value.\n\nThe formula $business rule$ equals one.\n",
                encoding="utf-8",
            )
            (target / "guide.tex").write_text(
                "\\section{Method}\nThe middleware converts the value.\n",
                encoding="utf-8",
            )
            (target / "sample.py").write_text(
                "def value() -> int:\n"
                '    """The service layer returns the value."""\n'
                "    return 1\n",
                encoding="utf-8",
            )
            (target / "sample.jl").write_text(
                '"""The business logic returns the value."""\nvalue() = 1\n',
                encoding="utf-8",
            )
            _git(target, "add", "-A")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_vale(target)

            rendered = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("README.md:1", rendered)
            self.assertIn("guide.tex:2", rendered)
            self.assertIn("sample.py:2", rendered)
            self.assertIn("sample.jl:1", rendered)
            self.assertNotIn("README.md:3", rendered)

    def test_vale_prose_include_scans_only_matching_tracked_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _consumer(Path(directory))
            declaration = target / ".qat.toml"
            declaration.write_text(
                declaration.read_text(encoding="utf-8")
                + '\n[text.prose]\ninclude = ["**/*.tex"]\n',
                encoding="utf-8",
            )
            (target / "README.md").write_text("Let's unpack the business rule.\n", encoding="utf-8")
            (target / "guide.tex").write_text(
                "\\section{Method}\nThe middleware converts the value.\n",
                encoding="utf-8",
            )
            _git(target, "add", "-A")
            sync(target, ROOT)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_vale(target)

            rendered = output.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("guide.tex:2", rendered)
            self.assertNotIn("README.md", rendered)

            advisory_output = io.StringIO()
            with contextlib.redirect_stdout(advisory_output):
                advisory_code = run_vale(target, advisory=True)
            self.assertEqual(advisory_code, 0)
            self.assertNotIn("README.md", advisory_output.getvalue())

    def test_vale_directive_detection_is_limited_to_reader_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _consumer(Path(directory))
            (target / "sample.py").write_text(
                'TOKEN = "# vale off"\n\n'
                "def value() -> int:\n"
                '    """Return one."""\n'
                "    return 1\n",
                encoding="utf-8",
            )
            _git(target, "add", "-A")
            self.assertEqual(run_vale(target), 0)
            (target / "sample.py").write_text(
                'def value() -> int:\n    """# vale off\n\nReturn one.\n"""\n    return 1\n',
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_vale(target)

            self.assertEqual(code, 1)
            self.assertIn("sample.py:2: QTX001", output.getvalue())


if __name__ == "__main__":
    unittest.main()
