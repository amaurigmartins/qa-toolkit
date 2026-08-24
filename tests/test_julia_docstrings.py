from __future__ import annotations

import unittest

from qa_toolkit.julia_docstrings import julia_docstring_view


class JuliaDocstringViewTests(unittest.TestCase):
    def test_projection_selects_attached_block_raw_and_field_docstrings(self) -> None:
        source = (
            '"""\nModule prose uses a business rule.\n"""\nmodule Example\n\n'
            'ordinary = "An ordinary service layer string."\n'
            '@warn "A middleware warning."\n\n'
            '"Constant prose uses a business rule."\n'
            "const VALUE = 1\n\n"
            '@doc raw"""\nRaw prose uses middleware.\n""" solve\n\n'
            "struct Model\n"
            '    "Field prose uses a service layer."\n'
            "    field::Int\n"
            "end\n"
            "end\n"
        )

        view = julia_docstring_view(source)

        self.assertIn("Module prose uses a business rule.", view.text)
        self.assertIn("Constant prose uses a business rule.", view.text)
        self.assertIn("Raw prose uses middleware.", view.text)
        self.assertIn("Field prose uses a service layer.", view.text)
        self.assertNotIn("ordinary service layer", view.text)
        self.assertNotIn("middleware warning", view.text)
        self.assertEqual(len(view.text.splitlines()), len(source.splitlines()))
        field_line = source.splitlines().index('    "Field prose uses a service layer."')
        self.assertEqual(view.column_offsets[field_line], 5)
        self.assertEqual(view.text.splitlines()[field_line], "Field prose uses a service layer.")

    def test_projection_masks_interpolation_and_retains_markdown_code_structure(self) -> None:
        source = (
            '"""\n'
            "$(TYPEDEF)\n"
            "Reader prose uses a business rule and $(FUNCTIONNAME).\n\n"
            "    solve(Grid; kwargs...)\n\n"
            "```julia\n"
            "A = [1.0 0.1; 0.1 2.0]\n"
            "value::Union{Int, Nothing}\n"
            "```\n"
            '"""\n'
            "function solve()\n"
            "    nothing\n"
            "end\n"
        )

        view = julia_docstring_view(source)

        self.assertNotIn("TYPEDEF", view.text)
        self.assertNotIn("FUNCTIONNAME", view.text)
        self.assertIn("Reader prose uses a business rule and", view.text)
        self.assertIn("    solve(Grid; kwargs...)", view.text)
        self.assertIn("```julia", view.text)
        self.assertIn("value::Union{Int, Nothing}", view.text)

    def test_projection_preserves_unicode_lines_and_original_columns(self) -> None:
        source = (
            'θ = π / 2\nstruct Model\n    "Field prose uses middleware."\n    field::Int\nend\n'
        )

        view = julia_docstring_view(source)

        self.assertEqual(view.text.splitlines()[0], "")
        self.assertEqual(view.text.splitlines()[2], "Field prose uses middleware.")
        self.assertEqual(view.column_offsets, (0, 0, 5, 0, 0))

    def test_projection_rejects_invalid_julia_syntax(self) -> None:
        with self.assertRaisesRegex(ValueError, "syntax tree contains an error"):
            julia_docstring_view('"""Unclosed documentation.\nfunction solve()\n')


if __name__ == "__main__":
    unittest.main()
