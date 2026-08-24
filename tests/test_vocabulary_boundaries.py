from __future__ import annotations

import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from qa_toolkit import vocabulary
from qa_toolkit.deployment import DeploymentError
from qa_toolkit.vocabulary import Boundary, VocabularyError

ROLES = {
    "action": frozenset({"build", "get"}),
    "concept": frozenset({"project"}),
    "selector": frozenset({"id", "name"}),
}
GRAMMARS: dict[str, tuple[tuple[str, ...], ...]] = {"callable": (("{action}", "{concept}"),)}
_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()


def _boundary_data() -> dict[str, object]:
    return {
        "id": "source",
        "include": ["src/**/*.py"],
        "exclude": [],
        "symbol_types": ["function"],
        "visibility": ["public"],
        "grammars": ["callable"],
        "roles": {"action": ["build"], "concept": ["project"]},
    }


class VocabularyPrimitiveTests(unittest.TestCase):
    def test_closed_collection_and_term_parsers_reject_invalid_values(self) -> None:
        cases: tuple[Callable[[], object], ...] = (
            lambda: vocabulary._table([], "field"),
            lambda: vocabulary._closed({"extra": True}, set(), "field"),
            lambda: vocabulary._strings("bad", "field"),
            lambda: vocabulary._strings([], "field", required=True),
            lambda: vocabulary._strings(["same", "same"], "field"),
            lambda: vocabulary._terms(["BAD"], "field"),
            lambda: vocabulary._accepted_terms(["two words"], "field"),
            lambda: vocabulary._replacements({"BAD": "good"}, "field"),
            lambda: vocabulary._replacements({"bad": "BAD"}, "field"),
            lambda: vocabulary._replacements({"same": "same"}, "field"),
            lambda: vocabulary._validate_globs(("../escape",), "field"),
        )
        for call in cases:
            with self.subTest(call=call), self.assertRaises(VocabularyError):
                call()

    def test_path_resolution_wraps_missing_and_malformed_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaisesRegex(VocabularyError, "cannot resolve"):
                vocabulary._resolve_existing_policy(root / "missing")
            malformed = root / "policy.toml"
            malformed.write_text("not = [valid", encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "cannot load vocabulary"):
                vocabulary._load_vocabulary_document(malformed, root)
            outside = root.parent / "outside-vocabulary.toml"
            outside.write_text("schema_version = 3", encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "escapes target"):
                vocabulary._resolve_vocabulary_path(outside, root)
            link = root / "link.toml"
            link.symlink_to(outside)
            with self.assertRaisesRegex(VocabularyError, "symlinked vocabulary"):
                vocabulary._resolve_vocabulary_path(link, None)

    def test_terminology_identifier_and_role_conflicts_are_rejected(self) -> None:
        terminology = {
            "terminology": {
                "accepted": [],
                "rejected": ["bad"],
                "replacements": {"worse": "bad"},
            }
        }
        with self.assertRaisesRegex(VocabularyError, "targets may not"):
            vocabulary._load_terminology(terminology)
        identifiers = {"identifiers": {"rejected": ["bad"], "replacements": {"worse": "bad"}}}
        with self.assertRaisesRegex(VocabularyError, "identifier replacement targets"):
            vocabulary._load_identifier_terms(identifiers)
        with self.assertRaisesRegex(VocabularyError, "at least one semantic role"):
            vocabulary._load_roles({"roles": {}}, set())
        with self.assertRaisesRegex(VocabularyError, "invalid role name"):
            vocabulary._load_roles({"roles": {"BAD": ["term"]}}, set())
        with self.assertRaisesRegex(VocabularyError, "rejected terminology"):
            vocabulary._load_roles({"roles": {"concept": ["term"]}}, {"term"})

    def test_grammar_parser_rejects_empty_unknown_and_invalid_elements(self) -> None:
        with self.assertRaisesRegex(VocabularyError, "at least one named grammar"):
            vocabulary._load_grammars({"grammars": {}}, ROLES)
        cases: tuple[tuple[object, object, str], ...] = (
            ("BAD", [["{action}"]], "invalid grammar name"),
            ("callable", [], "must contain shapes"),
            ("callable", [["{unknown}"]], "unknown role"),
            ("callable", [["not-valid!"]], "invalid literal"),
        )
        for name, shapes, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(VocabularyError, message):
                vocabulary._load_grammar(name, shapes, ROLES)


class BoundarySchemaTests(unittest.TestCase):
    def test_boundaries_require_unique_valid_entries(self) -> None:
        with self.assertRaisesRegex(VocabularyError, "non-empty"):
            vocabulary._load_boundaries({}, ROLES, GRAMMARS, set())
        invalid = _boundary_data()
        invalid["id"] = "BAD"
        with self.assertRaisesRegex(VocabularyError, "lowercase identifier"):
            vocabulary._load_boundary(invalid, 0, ROLES, GRAMMARS, set())
        first = _boundary_data()
        with self.assertRaisesRegex(VocabularyError, "duplicate boundary"):
            vocabulary._load_boundaries({"boundaries": [first, first]}, ROLES, GRAMMARS, set())

    def test_boundary_values_grammars_roles_and_exceptions_are_closed(self) -> None:
        data = _boundary_data()
        data["symbol_types"] = ["class"]
        with self.assertRaisesRegex(VocabularyError, "unsupported values"):
            vocabulary._load_boundary(data, 0, ROLES, GRAMMARS, set())
        data = _boundary_data()
        data["grammars"] = ["missing"]
        with self.assertRaisesRegex(VocabularyError, "unknown grammars"):
            vocabulary._load_boundary(data, 0, ROLES, GRAMMARS, set())
        data = _boundary_data()
        data["roles"] = {"unknown": ["term"]}
        with self.assertRaisesRegex(VocabularyError, "unknown roles"):
            vocabulary._load_boundary(data, 0, ROLES, GRAMMARS, set())
        data = _boundary_data()
        data["roles"] = {"action": ["get"]}
        data["allowed_identifier_terms"] = ["stuff"]
        with self.assertRaisesRegex(VocabularyError, "not rejected"):
            vocabulary._load_boundary(data, 0, ROLES, GRAMMARS, set())

    def test_action_grammar_and_selector_rules_validate_ownership(self) -> None:
        allowed = {"action": frozenset({"build"})}
        with self.assertRaisesRegex(VocabularyError, "unknown action"):
            vocabulary._boundary_action_grammars(
                {"action_grammars": {"delete": ["callable"]}},
                "boundary",
                ROLES,
                GRAMMARS,
                allowed,
            )
        with self.assertRaisesRegex(VocabularyError, "not owned"):
            vocabulary._boundary_action_grammars(
                {"action_grammars": {"get": ["callable"]}},
                "boundary",
                ROLES,
                GRAMMARS,
                allowed,
            )
        with self.assertRaisesRegex(VocabularyError, "unknown grammars"):
            vocabulary._boundary_action_grammars(
                {"action_grammars": {"build": ["missing"]}},
                "boundary",
                ROLES,
                GRAMMARS,
                allowed,
            )
        with self.assertRaisesRegex(VocabularyError, "unknown selectors"):
            vocabulary._boundary_action_selectors(
                {"action_selectors": {"build": ["slug"]}},
                "boundary",
                ROLES,
                allowed,
            )


class OutlineAdapterTests(unittest.TestCase):
    def test_adapter_requires_binary_and_classifies_invocation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with (
                patch("qa_toolkit.vocabulary.shutil.which", return_value=None),
                self.assertRaisesRegex(VocabularyError, "ast-grep is required"),
            ):
                vocabulary.extract_python_identifiers(root)
            with (
                patch("qa_toolkit.vocabulary.shutil.which", return_value="/bin/sg"),
                patch("qa_toolkit.vocabulary._tracked_python_files", return_value=("src/main.py",)),
                patch("qa_toolkit.vocabulary._run_captured", side_effect=OSError("failed")),
                self.assertRaisesRegex(VocabularyError, "invocation failed"),
            ):
                vocabulary.extract_python_identifiers(root)
            failed = subprocess.CompletedProcess((), 2, "", "parse failed")
            with (
                patch("qa_toolkit.vocabulary.shutil.which", return_value="/bin/sg"),
                patch("qa_toolkit.vocabulary._tracked_python_files", return_value=("src/main.py",)),
                patch("qa_toolkit.vocabulary._run_captured", return_value=failed),
                self.assertRaisesRegex(VocabularyError, "parse failed"),
            ):
                vocabulary.extract_python_identifiers(root)

    def test_adapter_selection_and_git_errors_are_explicit(self) -> None:
        self.assertEqual(vocabulary.extract_identifiers(_TEMP_ROOT, ("julia",)), ())
        with self.assertRaisesRegex(VocabularyError, "at least one supported"):
            vocabulary.extract_identifiers(_TEMP_ROOT, ())
        with self.assertRaisesRegex(VocabularyError, "unsupported semantic"):
            vocabulary.extract_identifiers(_TEMP_ROOT, ("rust",))
        records = (
            vocabulary.IdentifierRecord(
                "solve", "python", "function", "public", "src/main.py", 1, 1
            ),
        )
        with patch(
            "qa_toolkit.vocabulary.extract_python_identifiers", return_value=records
        ) as extract_python:
            self.assertEqual(
                vocabulary.extract_identifiers(_TEMP_ROOT, ("python", "julia")), records
            )
        extract_python.assert_called_once_with(_TEMP_ROOT, executable="ast-grep")
        with (
            patch(
                "qa_toolkit.vocabulary.tracked_regular_files",
                side_effect=DeploymentError("bad git"),
            ),
            self.assertRaisesRegex(VocabularyError, "tracked Python"),
        ):
            vocabulary._tracked_python_files(_TEMP_ROOT)

    def test_outline_payload_and_members_reject_malformed_shapes(self) -> None:
        expected = ("src/main.py",)
        invalid = (
            ("[]", "unsupported outline"),
            ('{"language":"Rust"}', "unsupported outline"),
            ('{"language":"Python","path":"other","items":[]}', "unexpected outline path"),
            ('{"language":"Python","path":"src/main.py","items":{}}', "items are malformed"),
        )
        for line, message in invalid:
            with self.subTest(message=message), self.assertRaisesRegex(VocabularyError, message):
                vocabulary._outline_payload(line, 1, expected, set())
        with self.assertRaisesRegex(VocabularyError, "class members"):
            vocabulary._outline_members({"symbolType": "class", "members": "bad"}, "src/main.py")
        with self.assertRaisesRegex(VocabularyError, "outline item"):
            vocabulary._outline_record([], "src/main.py", "function")
        with self.assertRaisesRegex(VocabularyError, "identifier is malformed"):
            vocabulary._outline_record(
                {"symbolType": "function", "name": 1, "range": {}},
                "src/main.py",
                "function",
            )
        with self.assertRaisesRegex(VocabularyError, "range is malformed"):
            vocabulary._outline_position({"range": {}}, "src/main.py")
        with self.assertRaisesRegex(VocabularyError, "position is malformed"):
            vocabulary._outline_position(
                {"range": {"start": {"line": "one", "column": 0}}}, "src/main.py"
            )

    def test_outline_stream_skips_blank_lines_and_magic_methods(self) -> None:
        payload = (
            '{"language":"Python","path":"src/main.py","items":'
            '[{"symbolType":"function","name":"__repr__",'
            '"range":{"start":{"line":0,"column":0}}}]}\n'
        )
        self.assertEqual(vocabulary._parse_outline_stream("\n" + payload, ("src/main.py",)), ())


class EvaluatorHelperTests(unittest.TestCase):
    def test_shape_matching_literals_roles_and_selector_helpers(self) -> None:
        self.assertIsNone(vocabulary._match_shape(("literal",), ("other",), ROLES))
        self.assertIsNone(vocabulary._match_shape(("{action}",), ("delete",), ROLES))
        self.assertEqual(
            vocabulary._match_shape(("{action}", "{concept}"), ("build", "project"), ROLES),
            (("action", "build"), ("concept", "project")),
        )
        boundary = Boundary(
            "source",
            ("src/**/*.py",),
            (),
            frozenset({"function"}),
            frozenset({"public"}),
            ("callable",),
            {"action": frozenset({"build"})},
            frozenset(),
            {},
            {"build": frozenset({"id"})},
        )
        self.assertEqual(
            vocabulary._hard_selector_violation(
                ("build", "project", "by", "name"), boundary, _policy(boundary)
            ),
            ("build", "name", frozenset({"id"})),
        )
        with self.assertRaises(AssertionError):
            vocabulary._first_disallowed((("action", "build"),), boundary)


def _policy(boundary: Boundary) -> vocabulary.VocabularyPolicy:
    return vocabulary.VocabularyPolicy(
        accepted=(),
        rejected=(),
        replacements={},
        identifier_rejected=(),
        identifier_replacements={},
        identifier_include=("**/*.py",),
        identifier_exclude=(),
        identifier_visibility=frozenset({"private", "public"}),
        spelling_include=("**/*.py",),
        spelling_exclude=(),
        roles=ROLES,
        grammars=GRAMMARS,
        boundaries=(boundary,),
        contract_coverage="strict",
        cases=(),
    )


if __name__ == "__main__":
    unittest.main()
