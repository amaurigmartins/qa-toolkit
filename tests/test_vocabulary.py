from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_toolkit.vocabulary import (
    IdentifierRecord,
    VocabularyError,
    _parse_outline_stream,
    evaluate_vocabulary,
    load_vocabulary,
)

POLICY = """schema_version = 3

[terminology]
accepted = ["Gridform", "Supabase"]
rejected = ["data"]
include = ["src/**/*.py", "tests/**/*.py"]
exclude = ["tests/fixtures/generated/**"]

[terminology.replacements]
create = "build"
module_version = "module_definition"
workspace = "project"

[identifiers]
rejected = ["thing"]

[identifiers.replacements]
manager = "controller"

[roles]
action = ["build", "load", "parse"]
concept = ["project", "system", "module_definition"]
selector = ["design", "id", "slug"]
state = ["active"]

[grammars]
callable = [
  ["{action}", "{concept}"],
  ["{action}", "{concept}", "by", "{selector}"],
]

[[boundaries]]
id = "source"
include = ["src/**/*.py"]
exclude = []
symbol_types = ["function", "method"]
visibility = ["public", "private"]
grammars = ["callable"]

[boundaries.roles]
action = ["build", "load"]
concept = ["project", "system", "module_definition"]
selector = ["design", "id"]

[boundaries.action_selectors]
build = ["design"]
load = ["id"]

[boundaries.action_grammars]
build = ["callable"]
load = ["callable"]

[[boundaries]]
id = "tests"
include = ["tests/**/*.py"]
exclude = ["tests/fixtures/generated/**"]
symbol_types = ["function", "method"]
visibility = ["public", "private"]
grammars = ["callable"]

[boundaries.roles]
action = ["parse"]
concept = ["project"]
selector = ["slug"]

[contract]
coverage = "strict"

[[cases]]
id = "source-accepts-build-system"
path = "src/core/names.py"
identifier = "build_system"
symbol_type = "function"
visibility = "public"
boundary = "source"
expect = "pass"

[[cases]]
id = "source-rejects-parse-project"
path = "src/core/names.py"
identifier = "parse_project"
symbol_type = "function"
visibility = "public"
boundary = "source"
expect = "USV003"

[[cases]]
id = "tests-accept-parse-project"
path = "tests/unit/test_names.py"
identifier = "parse_project"
symbol_type = "function"
visibility = "public"
boundary = "tests"
expect = "pass"

[[cases]]
id = "tests-reject-build-project"
path = "tests/unit/test_names.py"
identifier = "build_project"
symbol_type = "function"
visibility = "public"
boundary = "tests"
expect = "USV003"
"""


def _record(name: str, path: str = "src/core/names.py") -> IdentifierRecord:
    return IdentifierRecord(
        text=name,
        language="python",
        symbol_type="function",
        visibility="public",
        path=path,
        line=3,
        column=1,
    )


class VocabularyPolicyTests(unittest.TestCase):
    def _policy(self, root: Path):  # type: ignore[no-untyped-def]
        path = root / "vocabulary.toml"
        path.write_text(POLICY, encoding="utf-8")
        return load_vocabulary(path, target=root)

    def test_compounds_replacements_and_valid_grammar_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = self._policy(Path(raw))
            findings = evaluate_vocabulary(
                policy,
                (
                    _record("build_module_definition_by_design"),
                    _record("create_system"),
                    _record("build_module_version_by_design"),
                ),
            )
        self.assertEqual(findings, ())

    def test_action_specific_grammar_restricts_one_owned_action(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = POLICY.replace(
                "[grammars]\ncallable = [",
                '[grammars]\nshort = [["{action}", "{concept}"]]\ncallable = [',
                1,
            ).replace('build = ["callable"]', 'build = ["short"]', 1)
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            policy = load_vocabulary(path, target=root)
            findings = evaluate_vocabulary(
                policy,
                (_record("build_module_definition_by_design"),),
            )
        self.assertEqual(tuple(finding.code for finding in findings), ("USV004",))

    def test_magic_methods_are_outside_callable_grammar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = self._policy(Path(raw))
            findings = evaluate_vocabulary(policy, (_record("__call__"), _record("__init__")))
        self.assertEqual(findings, ())

    def test_identifier_scope_limits_paths_and_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = POLICY.replace(
                "[identifiers]\nrejected",
                '[identifiers]\ninclude = ["src/**/*.py", "tests/**/*.py"]\n'
                'exclude = ["tests/excluded/**"]\nvisibility = ["public"]\nrejected',
                1,
            )
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            policy = load_vocabulary(path, target=root)
            findings = evaluate_vocabulary(
                policy,
                (
                    _record("mystery"),
                    _record("mystery", "scripts/check.py"),
                    _record("mystery", "tests/excluded/test_names.py"),
                    IdentifierRecord(
                        text="_mystery",
                        language="python",
                        symbol_type="function",
                        visibility="private",
                        path="src/core/names.py",
                        line=3,
                        column=1,
                    ),
                ),
            )
        self.assertEqual(tuple(finding.code for finding in findings), ("USV002",))

    def test_contract_case_must_be_inside_identifier_scope(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = POLICY.replace(
                "[identifiers]\nrejected",
                '[identifiers]\ninclude = ["src/**/*.py"]\nvisibility = ["public"]\nrejected',
                1,
            )
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "outside identifier scope"):
                load_vocabulary(path, target=root)

    def test_identifier_scope_rejects_unknown_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = POLICY.replace(
                "[identifiers]\nrejected",
                '[identifiers]\nvisibility = ["package"]\nrejected',
                1,
            )
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "unsupported values: package"):
                load_vocabulary(path, target=root)

    def test_stable_findings_cover_unknown_owned_grammar_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = self._policy(Path(raw))
            findings = evaluate_vocabulary(
                policy,
                (
                    _record("build_mystery"),
                    _record("build_thing"),
                    _record("parse_project"),
                    _record("system_build"),
                    _record("load_project_by_design"),
                ),
            )
        self.assertEqual(
            tuple(finding.code for finding in findings),
            ("USV002", "USV006", "USV005", "USV003", "USV004"),
        )
        self.assertTrue(all(finding.hint for finding in findings))

    def test_specific_boundary_wins_and_ties_fail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = (
                POLICY.replace(
                    '[[boundaries]]\nid = "tests"',
                    '[[boundaries]]\nid = "specific"\ninclude = ["src/core/*.py"]\nexclude = []\n'
                    'symbol_types = ["function", "method"]\nvisibility = ["public", "private"]\n'
                    'grammars = ["callable"]\n[boundaries.roles]\naction = ["parse"]\n'
                    'concept = ["project"]\nselector = ["slug"]\n\n[[boundaries]]\nid = "tests"',
                )
                .replace(
                    '[contract]\ncoverage = "strict"',
                    '''[contract]
coverage = "strict"

[[cases]]
id = "specific-accepts-parse-project"
path = "src/core/names.py"
identifier = "parse_project"
symbol_type = "function"
visibility = "public"
boundary = "specific"
expect = "pass"

[[cases]]
id = "specific-rejects-build-project"
path = "src/core/names.py"
identifier = "build_project"
symbol_type = "function"
visibility = "public"
boundary = "specific"
expect = "USV003"''',
                )
                .replace(
                    'id = "source-accepts-build-system"\npath = "src/core/names.py"',
                    'id = "source-accepts-build-system"\npath = "src/other/names.py"',
                )
                .replace(
                    'id = "source-rejects-parse-project"\npath = "src/core/names.py"',
                    'id = "source-rejects-parse-project"\npath = "src/other/names.py"',
                )
            )
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            policy = load_vocabulary(path, target=root)
            self.assertEqual(evaluate_vocabulary(policy, (_record("parse_project"),)), ())

            duplicate = policy_text.replace('id = "specific"', 'id = "specific"', 1).replace(
                '[[boundaries]]\nid = "tests"',
                '[[boundaries]]\nid = "tie"\ninclude = ["src/core/*.py"]\nexclude = []\n'
                'symbol_types = ["function", "method"]\nvisibility = ["public", "private"]\n'
                'grammars = ["callable"]\n[boundaries.roles]\naction = ["parse"]\n'
                'concept = ["project"]\nselector = ["slug"]\n\n[[boundaries]]\nid = "tests"',
            )
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "ambiguous"):
                load_vocabulary(path, target=root)

    def test_uncovered_boundary_is_a_setup_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = self._policy(Path(raw))
            with self.assertRaisesRegex(VocabularyError, "USV001"):
                evaluate_vocabulary(policy, (_record("build_system", "other/file.py"),))

    def test_schema_rejects_legacy_language_selection_and_invalid_grammar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "vocabulary.toml"
            path.write_text(
                POLICY.replace("schema_version = 3", "schema_version = 2", 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "schema_version = 3"):
                load_vocabulary(path, target=root)
            path.write_text(
                POLICY.replace(
                    "schema_version = 3",
                    'schema_version = 3\nlanguages = ["python"]',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "unknown keys: languages"):
                load_vocabulary(path, target=root)
            path.write_text(
                POLICY.replace('["{action}", "{concept}"]', '["{missing}"]', 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "unknown role"):
                load_vocabulary(path, target=root)

    def test_contract_cases_and_strict_boundary_coverage_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "vocabulary.toml"
            path.write_text(
                POLICY.replace('expect = "USV003"', 'expect = "USV004"', 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "UVP201"):
                load_vocabulary(path, target=root)
            without_negative = POLICY.rsplit('[[cases]]\nid = "tests-reject-build-project"', 1)[0]
            path.write_text(without_negative, encoding="utf-8")
            with self.assertRaisesRegex(VocabularyError, "UVP202"):
                load_vocabulary(path, target=root)

    def test_schema_rejects_rejected_role_terms_and_invalid_action_grammars(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "vocabulary.toml"
            path.write_text(
                POLICY.replace(
                    'concept = ["project", "system", "module_definition"]',
                    'concept = ["data", "project", "system", "module_definition"]',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "may not be assigned semantic roles"):
                load_vocabulary(path, target=root)
            path.write_text(
                POLICY.replace('build = ["callable"]', 'build = ["missing"]', 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "unknown grammars"):
                load_vocabulary(path, target=root)

    def test_locally_rejected_identifier_term_cannot_become_role(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "vocabulary.toml"
            path.write_text(
                POLICY.replace(
                    'concept = ["project", "system", "module_definition"]',
                    'concept = ["project", "system", "module_definition", "thing"]',
                    1,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VocabularyError, "may not be assigned semantic roles"):
                load_vocabulary(path, target=root)

    def test_shared_identifier_terms_are_roles_with_boundary_scoped_allowance(self) -> None:
        shared_terms = ("boundary", "contract", "lifecycle", "platform", "policy")
        shared_concepts = (
            'concept = ["boundary", "contract", "lifecycle", "platform", "policy", '
            '"project", "system", "module_definition"]'
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "vocabulary.toml"
            policy_text = POLICY.replace(
                'concept = ["project", "system", "module_definition"]',
                shared_concepts,
                2,
            )
            path.write_text(policy_text, encoding="utf-8")

            with patch(
                "qa_toolkit.vocabulary._central_identifier_terms", return_value=shared_terms
            ):
                policy = load_vocabulary(path, target=root)
                findings = evaluate_vocabulary(
                    policy,
                    tuple(_record(f"build_{term}") for term in shared_terms),
                )

            self.assertEqual(
                tuple(finding.code for finding in findings),
                tuple("USV006" for _ in shared_terms),
            )

            allowed_text = policy_text.replace(
                'grammars = ["callable"]\n\n[boundaries.roles]',
                'grammars = ["callable"]\n'
                'allowed_identifier_terms = ["platform"]\n\n[boundaries.roles]',
                1,
            )
            path.write_text(allowed_text, encoding="utf-8")
            with patch(
                "qa_toolkit.vocabulary._central_identifier_terms", return_value=shared_terms
            ):
                allowed_policy = load_vocabulary(path, target=root)
                platform_findings = evaluate_vocabulary(
                    allowed_policy,
                    (_record("build_platform"),),
                )
                contract_findings = evaluate_vocabulary(
                    allowed_policy,
                    (_record("build_contract"),),
                )

            self.assertEqual(platform_findings, ())
            self.assertEqual(tuple(item.code for item in contract_findings), ("USV006",))

    def test_boundary_can_allow_one_identifier_only_term(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            policy_text = POLICY.replace(
                "[grammars]\ncallable = [",
                '[grammars]\nprotocol_member = [["thing"]]\ncallable = [',
                1,
            ).replace(
                'grammars = ["callable"]\n\n[boundaries.roles]',
                'grammars = ["callable", "protocol_member"]\n'
                'allowed_identifier_terms = ["thing"]\n\n[boundaries.roles]',
                1,
            )
            path = root / "vocabulary.toml"
            path.write_text(policy_text, encoding="utf-8")
            policy = load_vocabulary(path, target=root)
            self.assertEqual(evaluate_vocabulary(policy, (_record("thing"),)), ())

            path.write_text(
                policy_text.replace(
                    'allowed_identifier_terms = ["thing"]',
                    'allowed_identifier_terms = ["mystery"]',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VocabularyError, "terms that are not rejected"):
                load_vocabulary(path, target=root)

    def test_policy_traversal_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            outside = root.parent / f"{root.name}-vocabulary.toml"
            outside.write_text(POLICY, encoding="utf-8")
            try:
                with self.assertRaisesRegex(VocabularyError, "escapes"):
                    load_vocabulary(outside, target=root)
                link = root / "vocabulary.toml"
                link.symlink_to(outside)
                with self.assertRaisesRegex(VocabularyError, "symlinked"):
                    load_vocabulary(link, target=root)
                link.unlink()
                real = root / "real"
                real.mkdir()
                (real / "vocabulary.toml").write_text(POLICY, encoding="utf-8")
                linked = root / "linked"
                linked.symlink_to(real, target_is_directory=True)
                with self.assertRaisesRegex(VocabularyError, "symlinked"):
                    load_vocabulary(linked / "vocabulary.toml", target=root)
            finally:
                outside.unlink()


class OutlineAdapterTests(unittest.TestCase):
    def test_outline_flattens_functions_and_methods(self) -> None:
        payload = {
            "path": "src/example.py",
            "language": "Python",
            "items": [
                {
                    "symbolType": "function",
                    "name": "build_system",
                    "range": {"start": {"line": 1, "column": 2}},
                },
                {
                    "symbolType": "class",
                    "name": "Builder",
                    "range": {"start": {"line": 3, "column": 0}},
                    "members": [
                        {
                            "symbolType": "method",
                            "name": "_load_project",
                            "range": {"start": {"line": 4, "column": 4}},
                        }
                    ],
                },
            ],
        }
        records = _parse_outline_stream(json.dumps(payload), ("src/example.py",))
        self.assertEqual(tuple(record.symbol_type for record in records), ("function", "method"))
        self.assertEqual(records[1].visibility, "private")

    def test_malformed_and_empty_success_are_rejected(self) -> None:
        with self.assertRaisesRegex(VocabularyError, "malformed"):
            _parse_outline_stream("not-json", ("src/example.py",))
        with self.assertRaisesRegex(VocabularyError, "empty success"):
            _parse_outline_stream("", ("src/example.py",))


if __name__ == "__main__":
    unittest.main()
