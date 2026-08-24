"""Tests for position-preserving LaTeX prose extraction."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pylatexenc.latexwalker import LatexWalkerParseError  # type: ignore[import-untyped]

from qa_toolkit import latex
from qa_toolkit.latex import latex_prose_view, latex_prose_view_with_map


class LatexProseTests(unittest.TestCase):
    def test_reader_prose_survives_while_math_and_references_are_masked(self) -> None:
        source = (
            "\\section{Measured response}\n"
            "The line uses \\qty{3}{\\ohm} and cites \\ref{eq:model}.\n"
            "\\begin{equation}x = y + z\\end{equation}\n"
        )

        view = latex_prose_view_with_map(source)

        self.assertIn("Measured response", view.text)
        self.assertIn("The line uses", view.text)
        self.assertNotIn("eq:model", view.text)
        self.assertNotIn("x = y + z", view.text)
        self.assertEqual(view.text.count("\n"), source.count("\n"))
        self.assertEqual(len(view.column_offsets), len(source.splitlines(keepends=True)))

    def test_invalid_latex_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unterminated LaTeX inline literal"):
            latex_prose_view_with_map("Reader prose \\verb|unterminated")

    def test_groups_literals_lists_headings_and_spacing_retain_reader_text(self) -> None:
        source = (
            "{Grouped prose remains.}\n"
            "\\section{Heading}\n"
            "\\begin{itemize}\\item Plain~text & another cell.\\end{itemize}\n"
            "Use \\verb|hidden words| and \\lstinline[language=Julia]!hidden! now.\n"
            "\\verb \\verb{code} \\verb\n"
        )
        view = latex_prose_view_with_map(source)
        self.assertIn("Grouped prose remains.", view.text)
        self.assertIn("Heading", view.text)
        self.assertIn("Plain text", " ".join(view.text.split()))
        self.assertNotIn("hidden words", view.text)
        self.assertEqual(latex_prose_view("Plain prose."), "Plain prose.")

    def test_parser_and_position_invariants_fail_closed(self) -> None:
        parse_error = LatexWalkerParseError("bad input", pos=0)
        with (
            patch("qa_toolkit.latex.LatexWalker") as walker,
            self.assertRaisesRegex(ValueError, "cannot parse LaTeX input"),
        ):
            walker.return_value.get_latex_nodes.side_effect = parse_error
            latex_prose_view_with_map("text")
        with (
            patch("qa_toolkit.latex._render_nodes", side_effect=lambda *args: args[2].pop()),
            self.assertRaisesRegex(RuntimeError, "did not preserve source positions"),
        ):
            latex_prose_view_with_map("text")

    def test_inline_literal_and_markup_boundaries_are_closed(self) -> None:
        self.assertEqual(latex._inline_literal_positions("\\verb"), bytearray(5))
        self.assertEqual(latex._inline_literal_positions("\\verb "), bytearray(6))
        self.assertEqual(latex._inline_literal_positions("\\verb{code}"), bytearray(11))
        self.assertTrue(all(latex._inline_literal_positions("\\verb|code|")))
        output = ["\n"]
        latex._fill_markup(0, 1, output, "- ")
        self.assertEqual(output, ["\n"])


if __name__ == "__main__":
    unittest.main()
