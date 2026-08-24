from __future__ import annotations

import unittest

from qa_toolkit.acronyms import (
    GLOBAL_ACRONYMS,
    AcronymOccurrence,
    established_acronyms,
    unresolved_first_uses,
)


def _occurrences(path: str, source: str, term: str) -> tuple[AcronymOccurrence, ...]:
    found: list[AcronymOccurrence] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        cursor = 0
        while True:
            column = line.find(term, cursor)
            if column < 0:
                break
            found.append(AcronymOccurrence(path, line_number, column + 1, term))
            cursor = column + len(term)
    return tuple(found)


class AcronymFirstUseTests(unittest.TestCase):
    def test_retains_only_the_first_unresolved_use_per_term_and_document(self) -> None:
        first = "The QXZ routine starts.\nThe QXZ routine continues.\n"
        second = "Another QXZ routine starts.\n"
        occurrences = _occurrences("first.md", first, "QXZ") + _occurrences(
            "second.md", second, "QXZ"
        )

        retained = unresolved_first_uses(
            occurrences,
            {"first.md": first, "second.md": second},
        )

        self.assertEqual(
            retained,
            (
                AcronymOccurrence("first.md", 1, 5, "QXZ"),
                AcronymOccurrence("second.md", 1, 9, "QXZ"),
            ),
        )

    def test_recognizes_both_definition_orders_and_matching_initials(self) -> None:
        source = (
            "A modular multilevel converter (MMC) is selected.\n"
            "The MMC remains selected.\n"
            "A VSC (voltage source converter) is selected.\n"
            "The VSC remains selected.\n"
            "A QXZ (ordinary unrelated phrase) remains unresolved.\n"
        )
        occurrences = tuple(
            occurrence
            for term in ("MMC", "VSC", "QXZ")
            for occurrence in _occurrences("guide.md", source, term)
        )

        retained = unresolved_first_uses(occurrences, {"guide.md": source})

        self.assertEqual(retained, (AcronymOccurrence("guide.md", 5, 3, "QXZ"),))

    def test_reports_a_use_that_precedes_a_later_definition(self) -> None:
        source = (
            "The TLC model is selected.\n"
            "A transmission line cable (TLC) model follows.\n"
            "The TLC model remains selected.\n"
        )

        retained = unresolved_first_uses(
            _occurrences("guide.md", source, "TLC"),
            {"guide.md": source},
        )

        self.assertEqual(retained, (AcronymOccurrence("guide.md", 1, 5, "TLC"),))

    def test_recognizes_hyphenated_and_numeric_expansions(self) -> None:
        source = (
            "High-voltage direct current (HVDC) is used.\n"
            "A P2P (point-to-point) connection is used.\n"
        )
        occurrences = _occurrences("guide.md", source, "HVDC") + _occurrences(
            "guide.md", source, "P2P"
        )

        self.assertEqual(unresolved_first_uses(occurrences, {"guide.md": source}), ())

    def test_repository_accepted_acronyms_are_established(self) -> None:
        source = "The PSCAD model and PSCAD result are available.\n"
        established = established_acronyms(("Gridform", "PSCAD", "lowercase"))

        retained = unresolved_first_uses(
            _occurrences("guide.md", source, "PSCAD"),
            {"guide.md": source},
            established,
        )

        self.assertEqual(established, frozenset({"pscad"}))
        self.assertEqual(retained, ())

    def test_repository_report_can_require_a_global_acronym(self) -> None:
        source = "The API routine starts.\nThe API routine continues.\n"
        occurrences = _occurrences("guide.md", source, "API")

        retained = unresolved_first_uses(
            occurrences,
            {"guide.md": source},
            GLOBAL_ACRONYMS,
            frozenset({occurrences[0]}),
        )

        self.assertEqual(retained, (occurrences[0],))

    def test_invalid_source_locations_fail_closed(self) -> None:
        occurrence = AcronymOccurrence("guide.md", 1, 5, "QXZ")
        with self.assertRaisesRegex(ValueError, "does not match source text"):
            unresolved_first_uses((occurrence,), {"guide.md": "The ABC routine.\n"})
        with self.assertRaisesRegex(ValueError, "source is unavailable"):
            unresolved_first_uses((occurrence,), {})
        with self.assertRaisesRegex(ValueError, "invalid source location"):
            unresolved_first_uses(
                (AcronymOccurrence("guide.md", 2, 1, "QXZ"),),
                {"guide.md": "QXZ\n"},
            )


if __name__ == "__main__":
    unittest.main()
