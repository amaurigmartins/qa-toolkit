"""Tests for position-preserving LaTeX prose extraction."""

from __future__ import annotations

import unittest

from qa_toolkit.latex import latex_prose_view_with_map


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


if __name__ == "__main__":
    unittest.main()
