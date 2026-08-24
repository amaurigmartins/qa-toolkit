"""Boundary tests for consumer-owned ast-grep rule extensions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_toolkit import ast_grep
from qa_toolkit.deployment import DeploymentError
from qa_toolkit.models import Consumer, PythonSettings


def _consumer(config: Path | None, tests: Path | None) -> Consumer:
    return Consumer(
        "profile",
        (),
        None,
        (),
        (),
        config,
        tests,
        PythonSettings(),
        (),
        (),
        Path(".git/qat/work"),
        True,
        Path("/target/.qat.toml"),
    )


class AstGrepBoundaryTests(unittest.TestCase):
    def test_resolution_requires_both_paths_and_translates_repository_errors(self) -> None:
        self.assertEqual(
            ast_grep.resolve_ast_grep(_consumer(None, None), target=Path("."), root=Path(".")),
            ast_grep.ResolvedAstGrep(),
        )
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "requires config and tests"):
            ast_grep.resolve_ast_grep(
                _consumer(Path("sgconfig.yml"), None), target=Path("."), root=Path(".")
            )
        with (
            patch(
                "qa_toolkit.ast_grep.tracked_regular_files",
                side_effect=DeploymentError("tracked input failed"),
            ),
            self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "tracked input failed"),
        ):
            ast_grep.resolve_ast_grep(
                _consumer(Path("sgconfig.yml"), Path("tests")),
                target=Path("."),
                root=Path("."),
            )

    def test_declared_rule_and_test_inputs_fail_closed(self) -> None:
        policy = ("sgconfig.yml", "sg-rule-tests")
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "tracked regular file"):
            ast_grep._declared_inputs(policy, Path("."), set())
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "YAML rule cases"):
            ast_grep._declared_inputs(policy, Path("."), {"sgconfig.yml"})
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "select tracked YAML rules"):
            ast_grep._declared_rule_files(
                policy,
                "ruleDirs:\n  - sg-rules\n",
                {"sgconfig.yml", "sg-rule-tests/case.yml"},
            )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "cannot read"):
                ast_grep._read(root, "missing.yml")
            first = root / "first.yml"
            second = root / "second.yml"
            source = "id: consumer-rule\nvalid:\n  - safe\ninvalid:\n  - blocked\n"
            first.write_text(source, encoding="utf-8")
            second.write_text(source, encoding="utf-8")
            consumer = {"consumer-rule": ("rule.yml", "digest")}
            with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "duplicate.*test id"):
                ast_grep._consumer_rule_cases(root, ("first.yml", "second.yml"), consumer)
            second.write_text(source.replace("consumer-rule", "unknown-rule"), encoding="utf-8")
            with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "unknown rule"):
                ast_grep._consumer_rule_cases(root, ("second.yml",), consumer)

    def test_consumer_rules_reject_duplicate_managed_ids_and_bodies(self) -> None:
        source = "id: consumer-rule\nrule:\n  pattern: print($A)\n"
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            target.mkdir()
            root.mkdir()
            (target / "one.yml").write_text(source, encoding="utf-8")
            (target / "two.yml").write_text(source, encoding="utf-8")
            with (
                patch("qa_toolkit.ast_grep._managed_rules", return_value={}),
                self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "duplicate consumer"),
            ):
                ast_grep._consumer_rules(target, ("one.yml", "two.yml"), root)
            body = ast_grep._content_digest("  pattern: print($A)")
            with (
                patch(
                    "qa_toolkit.ast_grep._managed_rules",
                    return_value={"consumer-rule": body},
                ),
                self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "managed rule id"),
            ):
                ast_grep._consumer_rules(target, ("one.yml",), root)
            with (
                patch("qa_toolkit.ast_grep._managed_rules", return_value={"managed": body}),
                self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "managed rule body"),
            ):
                ast_grep._consumer_rules(target, ("one.yml",), root)

    def test_yaml_subset_rejects_ambiguous_rules_and_cases(self) -> None:
        directory_cases = (
            ("ruleDirs:\n", "non-empty"),
            ("ruleDirs:\n  - ../rules\n", "unsafe"),
            ("ruleDirs:\n  - rules\n  - rules\n", "duplicate"),
            ("ruleDirs:\n  mapping: value\n", "plain YAML sequence"),
        )
        for source, message in directory_cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ast_grep.AstGrepPolicyError, message),
            ):
                ast_grep._rule_directories(source, "sgconfig.yml")
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "invalid id"):
            ast_grep._rule("id: Invalid\nrule:\n  pattern: value\n", "rule.yml")
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "no rule body"):
            ast_grep._rule("id: valid-rule\nrule:\n  # comment\n", "rule.yml")
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "invalid id"):
            ast_grep._rule_cases(
                "id: Invalid\nvalid:\n  - safe\ninvalid:\n  - blocked\n", "case.yml"
            )
        scalar_cases = (
            ("other: value\n", "exactly one"),
            ('id: "unterminated\n', "invalid quoted"),
            ("id: value:other\n", "unsupported"),
        )
        for source, message in scalar_cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ast_grep.AstGrepPolicyError, message),
            ):
                ast_grep._top_level_scalar(source, "id", "case.yml")
        self.assertEqual(
            ast_grep._top_level_scalar("id: 'consumer-rule'\n", "id", "case.yml"),
            "consumer-rule",
        )
        self.assertEqual(
            ast_grep._top_level_scalar("id: consumer-rule # note\n", "id", "case.yml"),
            "consumer-rule",
        )
        with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "one top-level rule"):
            ast_grep._top_level_block("id: consumer-rule\n", "rule")

    def test_case_completeness_paths_and_managed_inventory(self) -> None:
        consumer = {"consumer-rule": ("rule.yml", "digest")}
        for cases in ({}, {"consumer-rule": (True, False)}):
            with self.assertRaisesRegex(ast_grep.AstGrepPolicyError, "accepted and rejected"):
                ast_grep._require_complete_cases(consumer, cases)
        self.assertEqual(
            ast_grep._tracked_yaml_below(
                {"rules/a.yml", "rules/b.yaml", "rules/readme.md", "other.yml"}, "rules"
            ),
            ("rules/a.yml", "rules/b.yaml"),
        )
        for value in ("", "/rules", "../rules", "rules/**", "bad\\rules", "bad\nrules"):
            self.assertFalse(ast_grep._safe_path(value))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rules = root / "config/ast-grep/python/rules"
            rules.mkdir(parents=True)
            (rules / "one.yml").write_text(
                "id: managed-rule\nrule:\n  pattern: print($A)\n", encoding="utf-8"
            )
            (root / "config/ast-grep/ignored.yml").write_text(
                "id: ignored\nrule:\n  pattern: value\n", encoding="utf-8"
            )
            self.assertEqual(tuple(ast_grep._managed_rules(root)), ("managed-rule",))


if __name__ == "__main__":
    unittest.main()
