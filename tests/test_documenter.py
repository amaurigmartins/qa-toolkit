from __future__ import annotations

import unittest

from qa_toolkit import documenter
from qa_toolkit.documenter import documenter_markdown_view


class DocumenterMarkdownTests(unittest.TestCase):
    def test_masks_documenter_math_and_directive_blocks_without_moving_text(self) -> None:
        source = (
            "Reader prose uses a business rule.\n"
            "Inline ``MIMO + CIL = GC2`` remains hidden.\n"
            "Deprecated $MIMO + CIL$ remains hidden.\n"
            "$$\nMIMO + CIL;\n$$\n"
            "```math\nMIMO + CIL;\n```\n"
            "```@docs\nMIMO.solve\n```\n"
            "Reader prose uses a service layer.\n"
        )
        view = documenter_markdown_view(source)

        self.assertEqual(len(view.text), len(source))
        self.assertEqual(view.text.count("\n"), source.count("\n"))
        self.assertIn("Reader prose uses a business rule.", view.text)
        self.assertIn("Reader prose uses a service layer.", view.text)
        self.assertNotIn("MIMO", view.text)
        self.assertNotIn("CIL", view.text)
        for original, rendered in zip(source, view.text, strict=True):
            if original in {"\r", "\n"}:
                self.assertEqual(rendered, original)

    def test_preserves_ordinary_code_and_unmatched_or_escaped_dollars(self) -> None:
        source = (
            "`price = $5` and ``unterminated math stay visible.\n"
            "The escaped \\$MIMO token and unmatched $CIL remain visible.\n"
            '```julia\nvalue = "$GC2"\n```\n'
        )
        view = documenter_markdown_view(source)

        self.assertEqual(view.text, source)

    def test_masks_non_reader_link_and_citation_data(self) -> None:
        source = (
            "[MIMO method](@ref MIMO-target) remains reader prose.\n"
            "[MIMO](@cite) is a key-only citation.\n"
            "[CIL, GC2; Eq. (1)](@citep) retains its reader note.\n"
            "[the GC2 method](@citet GC2Key) retains its reader label.\n"
            "[RLC; Appendix A](@cite*) retains another reader note.\n"
            "[Section title](@id internal-anchor) remains reader prose.\n"
        )
        view = documenter_markdown_view(source)

        self.assertIn("[MIMO method]", view.text)
        self.assertNotIn("MIMO-target", view.text)
        self.assertNotIn("[MIMO]", view.text)
        self.assertNotIn("CIL", view.text)
        self.assertNotIn("GC2;", view.text)
        self.assertIn("Eq. (1)", view.text)
        self.assertIn("[the GC2 method]", view.text)
        self.assertNotIn("GC2Key", view.text)
        self.assertNotIn("RLC", view.text)
        self.assertIn("Appendix A", view.text)
        self.assertIn("[Section title]", view.text)
        self.assertNotIn("internal-anchor", view.text)
        self.assertEqual(len(view.text), len(source))

    def test_does_not_interpret_documenter_syntax_inside_code(self) -> None:
        source = (
            "`[MIMO](@cite)` stays code.\n"
            "```text\n[MIMO](@cite) and $CIL$ stay code.\n```\n"
            "Reader [GC2](@cite) is masked.\n"
        )
        view = documenter_markdown_view(source)

        self.assertIn("`[MIMO](@cite)`", view.text)
        self.assertIn("[MIMO](@cite) and $CIL$", view.text)
        self.assertNotIn("Reader [GC2]", view.text)
        self.assertIn("Reader", view.text)

    def test_preserves_crlf_line_endings(self) -> None:
        source = "Before mathematics.\r\n$MIMO + CIL$\r\nAfter mathematics.\r\n"
        view = documenter_markdown_view(source)

        self.assertEqual(view.text.splitlines(keepends=True)[0], "Before mathematics.\r\n")
        self.assertEqual(view.text.splitlines(keepends=True)[1][-2:], "\r\n")
        self.assertEqual(view.text.splitlines(keepends=True)[2], "After mathematics.\r\n")
        self.assertEqual(len(view.text), len(source))


class DocumenterBoundaryTests(unittest.TestCase):
    def test_empty_unclosed_and_nested_constructs_preserve_positions(self) -> None:
        cases = (
            "",
            "```@docs\nunclosed directive\n",
            "``unclosed inline code",
            "$ leading space",
            "$value \\$ still open",
            "[label without destination]\n",
            "[label](@ref nested(value)\n",
            "[label\n](@ref target)\n",
            "[escaped \\] label](@ref target)\n",
        )
        for source in cases:
            with self.subTest(source=source):
                view = documenter_markdown_view(source)
                self.assertEqual(len(view.text), len(source))
                self.assertEqual(view.text.count("\n"), source.count("\n"))

    def test_dollar_closing_rejects_protected_escaped_and_whitespace_boundaries(self) -> None:
        source = "$a$"
        protected = [False] * len(source)
        protected[2] = True
        self.assertIsNone(documenter._dollar_math_end(source, 0, protected))
        self.assertEqual(
            documenter._find_dollar_closing("$a\\$ b$", 1, "$", [False] * 7, multiline=False),
            6,
        )
        self.assertIsNone(
            documenter._find_dollar_closing("$a \n$", 1, "$", [False] * 5, multiline=False)
        )
        self.assertFalse(documenter._valid_dollar_closing("$a $", 1, 3, 4, "$", [False] * 4))

    def test_balanced_end_handles_escaping_protection_and_unclosed_input(self) -> None:
        source = "[a\\]b]"
        self.assertEqual(
            documenter._balanced_end(
                source, 0, "[", "]", [False] * len(source), allow_newline=False
            ),
            len(source) - 1,
        )
        protected = [False] * len("[a]b]")
        protected[2] = True
        self.assertEqual(
            documenter._balanced_end("[a]b]", 0, "[", "]", protected, allow_newline=False),
            4,
        )
        self.assertIsNone(
            documenter._balanced_end("[open", 0, "[", "]", [False] * 5, allow_newline=True)
        )


if __name__ == "__main__":
    unittest.main()
