"""Closed-schema and digest boundary tests for profiles and consumers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_deployment import _central, _consumer

from qa_toolkit import config
from qa_toolkit.models import (
    ConfigurationError,
    ConsumerGate,
    Gate,
    closed_keys,
    relative_path,
    string,
    string_list,
)


def _gate() -> dict[str, object]:
    return {
        "id": "quality",
        "phase": "check",
        "argv": ["true"],
        "triggers": ["**"],
        "timeout": 30,
        "severity": "blocking",
        "variants": [],
        "finding_exit_codes": [1],
        "execution_error_exit_codes": [2],
    }


class ModelHelperTests(unittest.TestCase):
    def test_closed_primitives_accept_only_their_declared_shape(self) -> None:
        closed_keys({"name": "value"}, {"name"}, "item")
        self.assertEqual(string({"name": "value"}, "name", "item"), "value")
        self.assertEqual(string_list(["one", "two"], "items"), ("one", "two"))
        self.assertEqual(relative_path("directory/file", "path"), Path("directory/file"))
        cases = (
            lambda: closed_keys({"extra": True}, set(), "item"),
            lambda: string({}, "name", "item"),
            lambda: string_list([""], "items"),
            lambda: relative_path("../file", "path"),
        )
        for operation in cases:
            with self.subTest(operation=operation), self.assertRaises(ConfigurationError):
                operation()

    def test_config_helpers_reject_wrong_types_duplicates_and_paths(self) -> None:
        self.assertEqual(config._unique_strings(None, "values"), ())
        self.assertEqual(config._optional_path(None, "path"), None)
        self.assertEqual(config._optional_path(".", "consumer.python.project"), Path("."))
        invalid = (
            lambda: config._schema({}, Path("config.toml")),
            lambda: config._table_array({}, "tables"),
            lambda: config._positive_integer(True, "number"),
            lambda: config._boolean(1, "flag"),
            lambda: config._unique_strings(["one", "one"], "values"),
            lambda: config._python_paths(["../source"], "paths"),
            lambda: config._python_paths(["src/**"], "paths"),
            lambda: config._optional_path("", "path"),
            lambda: config._exit_codes([1, 1], "exits"),
            lambda: config._exit_codes([True], "exits"),
        )
        for operation in invalid:
            with self.subTest(operation=operation), self.assertRaises(ConfigurationError):
                operation()


class PythonDeclarationTests(unittest.TestCase):
    def test_typed_python_settings_accept_strict_values(self) -> None:
        ruff = config._ruff_settings(
            {
                "extend_select": ["C90"],
                "enforce": ["S603"],
                "paths": ["src"],
                "known_first_party": ["package.core"],
                "thresholds": {"max_complexity": 8, "max_args": 5, "max_returns": 4},
            },
            "python.ruff",
        )
        self.assertEqual(ruff.thresholds.max_complexity, 8)
        pylint = config._pylint_settings(
            {"enable": ["invalid-name"], "paths": ["src"], "min_similarity_lines": 4},
            "python.pylint",
        )
        self.assertEqual(pylint.min_similarity_lines, 4)
        pydoclint = config._pydoclint_settings(
            {
                "paths": ["src"],
                "skip_checking_short_docstrings": False,
                "check_class_attributes": True,
            },
            "python.pydoclint",
        )
        self.assertTrue(pydoclint.check_class_attributes)
        mypy = config._mypy_settings(
            {
                "plugins": ["pydantic.mypy"],
                "mypy_path": ["src"],
                "explicit_package_bases": True,
                "namespace_packages": True,
            },
            "python.mypy",
        )
        self.assertEqual(mypy.plugins, ("pydantic.mypy",))
        exceptions = config._python_exceptions(
            [{"tool": "ruff", "rule": "S603", "path": "tests/**", "reason": "Tests run arrays."}],
            "python.exceptions",
        )
        self.assertEqual(exceptions[0].rule, "S603")

    def test_python_settings_fail_closed_for_each_typed_field(self) -> None:
        cases = (
            lambda: config._ruff_settings([], "ruff"),
            lambda: config._ruff_settings({"extend_select": ["bad"]}, "ruff"),
            lambda: config._ruff_settings({"known_first_party": ["bad-name"]}, "ruff"),
            lambda: config._ruff_settings({"thresholds": []}, "ruff"),
            lambda: config._pylint_settings([], "pylint"),
            lambda: config._pylint_settings({"enable": ["Bad"]}, "pylint"),
            lambda: config._pydoclint_settings([], "pydoclint"),
            lambda: config._pydoclint_settings({"check_class_attributes": "yes"}, "pydoclint"),
            lambda: config._mypy_settings({"plugins": ["bad-name"]}, "mypy"),
            lambda: config._mypy_settings({"explicit_package_bases": "yes"}, "mypy"),
            lambda: config._python_exceptions({}, "exceptions"),
            lambda: config._python_exceptions(
                [{"tool": "mypy", "rule": "S603", "path": "tests/**", "reason": "Reason"}],
                "exceptions",
            ),
            lambda: config._python_exceptions(
                [{"tool": "ruff", "rule": "bad", "path": "tests/**", "reason": "Reason"}],
                "exceptions",
            ),
            lambda: config._python_exceptions(
                [{"tool": "ruff", "rule": "S603", "path": "../tests", "reason": "Reason"}],
                "exceptions",
            ),
            lambda: config._python_exceptions(
                [{"tool": "ruff", "rule": "S603", "path": "tests/**", "reason": " "}], "exceptions"
            ),
            lambda: config._python_exceptions(
                [
                    {"tool": "ruff", "rule": "S603", "path": "tests/**", "reason": "One"},
                    {"tool": "ruff", "rule": "S603", "path": "tests/**", "reason": "Two"},
                ],
                "exceptions",
            ),
        )
        for operation in cases:
            with self.subTest(operation=operation), self.assertRaises(ConfigurationError):
                operation()


class GateDeclarationTests(unittest.TestCase):
    def test_profile_and_consumer_gates_have_distinct_types(self) -> None:
        self.assertIsInstance(config._gate(_gate(), "gate", consumer=False), Gate)
        consumer = _gate()
        consumer["before"] = "later"
        parsed = config._gate(consumer, "gate", consumer=True)
        self.assertIsInstance(parsed, ConsumerGate)
        self.assertEqual(parsed.before, "later")

        with self.assertRaises(ConfigurationError):
            config._gate(consumer, "gate", consumer=False)

    def test_gate_fields_and_exit_classes_are_closed(self) -> None:
        changes = (
            ("phase", "other"),
            ("severity", "other"),
            ("timeout", 0),
            ("finding_exit_codes", [0]),
            ("execution_error_exit_codes", [1]),
        )
        for key, value in changes:
            raw = _gate()
            raw[key] = value
            if key == "execution_error_exit_codes":
                raw["finding_exit_codes"] = [1]
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                config._gate(raw, "gate", consumer=False)


class ProfileBoundaryTests(unittest.TestCase):
    def _profile(self, parent: Path) -> tuple[Path, Path]:
        root = parent / "central"
        root.mkdir()
        _central(root)
        return root, root / "profiles/fixture.toml"

    def test_profile_identity_tools_and_configuration_links_are_closed(self) -> None:
        replacements = (
            ('name = "fixture"', 'name = "other"'),
            ('tools = ["jq"]', 'tools = ["jq", "jq"]'),
            ('tools = ["jq"]', 'tools = ["unknown"]'),
            ('mode = "symlink"', 'mode = "other"'),
            ('destination = ".qat/config/link.txt"', 'destination = "config/link.txt"'),
            ('source = "config/sample/link.txt"', 'source = "config/sample/missing.txt"'),
            ('id = "copied"', 'id = "linked"'),
            ('destination = ".qat/config/copy.txt"', 'destination = ".qat/config/link.txt"'),
        )
        for old, new in replacements:
            with self.subTest(new=new), tempfile.TemporaryDirectory() as raw:
                root, path = self._profile(Path(raw))
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
                )
                with self.assertRaises(ConfigurationError):
                    config.load_profile("fixture", root)

    def test_profile_gate_hook_and_skill_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root, path = self._profile(Path(raw))
            gate = _gate()
            gate_text = "\n".join(
                (
                    "[[gates]]",
                    *(f"{key} = {json.dumps(value)}" for key, value in gate.items()),
                    "",
                    "[[gates]]",
                    *(f"{key} = {json.dumps(value)}" for key, value in gate.items()),
                )
            )
            document = path.read_text(encoding="utf-8").replace("gates = []", "")
            path.write_text(f"{document}\n{gate_text}\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "duplicate ID"):
                config.load_profile("fixture", root)

        hook_cases = (
            ('kind = "other"\nevent = "pre-commit"', "kind"),
            ('kind = "git"\nevent = "other"', "event"),
            ('kind = "git"\nevent = "pre-commit"\nentry = "other/hook"', "entry"),
        )
        for declaration, _label in hook_cases:
            with tempfile.TemporaryDirectory() as raw:
                root, path = self._profile(Path(raw))
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "hooks = []",
                        f"[[hooks]]\n{declaration}\nenabled = true",
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigurationError):
                    config.load_profile("fixture", root)

        with tempfile.TemporaryDirectory() as raw:
            root, path = self._profile(Path(raw))
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    'skills = ["library/skills/sample"]', 'skills = ["other/sample"]'
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                config.load_profile("fixture", root)

    def test_valid_hooks_and_remaining_profile_conflicts(self) -> None:
        declaration = (
            '[[hooks]]\nkind = "git"\nevent = "pre-commit"\n'
            'entry = "library/git-hooks/pre-commit/quality"\nenabled = false\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            root, path = self._profile(Path(raw))
            hook = root / "library/git-hooks/pre-commit/quality"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\n", encoding="utf-8")
            hook.chmod(0o755)
            document = path.read_text(encoding="utf-8").replace("hooks = []", "")
            path.write_text(f"{document}\n{declaration}", encoding="utf-8")
            profile = config.load_profile("fixture", root)
            self.assertFalse(profile.hooks[0].enabled)

            path.write_text(f"{document}\n{declaration}\n{declaration}", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "duplicate kind"):
                config.load_profile("fixture", root)

        for missing_entry in (False, True):
            with self.subTest(missing_entry=missing_entry), tempfile.TemporaryDirectory() as raw:
                root, path = self._profile(Path(raw))
                if missing_entry:
                    (root / "library/skills/sample/SKILL.md").unlink()
                else:
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            'skills = ["library/skills/sample"]',
                            'skills = ["library/skills/sample", "library/skills/sample"]',
                        ),
                        encoding="utf-8",
                    )
                with self.assertRaises(ConfigurationError):
                    config.load_profile("fixture", root)

        with tempfile.TemporaryDirectory() as raw:
            root, path = self._profile(Path(raw))
            hook = root / "library/git-hooks/pre-commit/quality"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\n", encoding="utf-8")
            document = path.read_text(encoding="utf-8").replace("hooks = []", "")
            path.write_text(f"{document}\n{declaration}", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "not executable"):
                config.load_profile("fixture", root)


class ConsumerBoundaryTests(unittest.TestCase):
    def _consumer(self, parent: Path) -> tuple[Path, Path]:
        target = parent / "consumer"
        target.mkdir()
        _consumer(target)
        return target, target / ".qat.toml"

    def test_consumer_tables_and_work_directory_are_closed(self) -> None:
        additions = (
            "\nvocabulary = []\n",
            "\nast_grep = []\n",
            "\npython = []\n",
        )
        for addition in additions:
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as raw:
                target, path = self._consumer(Path(raw))
                path.write_text(path.read_text(encoding="utf-8") + addition, encoding="utf-8")
                with self.assertRaises(ConfigurationError):
                    config.load_consumer(target)

    def test_consumer_rejects_non_table_sections_after_valid_toml_parsing(self) -> None:
        sections = ("vocabulary", "ast_grep", "python", "work")
        for section in sections:
            with self.subTest(section=section), tempfile.TemporaryDirectory() as raw:
                target = Path(raw)
                (target / ".qat.toml").write_text(
                    "\n".join(
                        (
                            "schema_version = 1",
                            'profile = "fixture"',
                            "native_configurations = []",
                            "protected_paths = []",
                            f"{section} = []",
                            *(
                                (
                                    "work = { "
                                    'state_directory = ".git/qat/work", '
                                    "require_allowed_paths = true }",
                                )
                                if section != "work"
                                else ()
                            ),
                        )
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigurationError):
                    config.load_consumer(target)

        replacements = (
            ("require_allowed_paths = true", 'require_allowed_paths = "yes"'),
            ('state_directory = ".git/qat/work"', 'state_directory = "work"'),
        )
        for old, new in replacements:
            with tempfile.TemporaryDirectory() as raw:
                target, path = self._consumer(Path(raw))
                path.write_text(
                    path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
                )
                with self.assertRaises(ConfigurationError):
                    config.load_consumer(target)

    def test_consumer_duplicate_gate_and_digest_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target, path = self._consumer(Path(raw))
            gate = _gate()
            rendered = "\n".join(f"{key} = {json.dumps(value)}" for key, value in gate.items())
            path.write_text(
                path.read_text(encoding="utf-8")
                + f"\n[[gates]]\n{rendered}\n[[gates]]\n{rendered}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigurationError, "duplicate ID"):
                config.load_consumer(target)

            path.write_text(
                path.read_text(encoding="utf-8").split("\n[[gates]]", maxsplit=1)[0]
                + '\n\n[ast_grep]\nconfig = "rules.yml"\ntests = "rule-tests"\n',
                encoding="utf-8",
            )
            (target / "rules.yml").write_text("rule", encoding="utf-8")
            (target / "rule-tests").mkdir()
            (target / "rule-tests/case.yml").write_text("case", encoding="utf-8")
            consumer = config.load_consumer(target)
            first = config.digest_consumer(consumer)
            (target / "rule-tests/case.yml").write_text("changed", encoding="utf-8")
            self.assertNotEqual(first, config.digest_consumer(consumer))


if __name__ == "__main__":
    unittest.main()
