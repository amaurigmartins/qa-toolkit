"""Boundary tests for corpus parsing and atomic generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_corpus import VALID_VOCABULARY, _consumer

from qa_toolkit.corpus import (
    ConsumerVocabulary,
    CorpusError,
    TermRule,
    _load_toml,
    _resolved,
    _strings,
    _table,
    _term,
    _write_outputs,
    build_corpus,
    load_consumer_vocabulary,
)
from qa_toolkit.deployment import enroll
from qa_toolkit.paths import toolkit_root


class CorpusPrimitiveTests(unittest.TestCase):
    def test_toml_table_and_string_parsers_wrap_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.toml"
            path.write_text("[broken\n", encoding="utf-8")
            with self.assertRaisesRegex(CorpusError, "cannot read vocabulary"):
                _load_toml(path)
            with self.assertRaisesRegex(CorpusError, "cannot read vocabulary"):
                _load_toml(path.with_name("missing.toml"))
        with self.assertRaisesRegex(CorpusError, "expected a table"):
            _table([], "value")
        with self.assertRaisesRegex(CorpusError, "expected an array of non-empty strings"):
            _strings([1], "terms")
        with self.assertRaisesRegex(CorpusError, "may not be empty"):
            _strings([], "terms", required=True)
        with self.assertRaisesRegex(CorpusError, "duplicate values"):
            _strings(["Term", "term"], "terms")

    def test_term_parser_rejects_each_invalid_identity(self) -> None:
        base: dict[str, object] = {
            "id": "valid-term",
            "forms": ["valid term"],
            "guidance": "Name the exact operation.",
            "prose": "error",
            "identifier": "warning",
            "commit": "off",
        }
        cases = (
            ({**base, "id": "Not Valid"}, "lowercase kebab-case"),
            ({**base, "guidance": ""}, "non-empty string"),
            ({**base, "prose": "fatal"}, "invalid severity"),
            ({**base, "forms": []}, "may not be empty"),
        )
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(CorpusError, message):
                _term(value, 0, set(), set())
        with self.assertRaisesRegex(CorpusError, "duplicate term ID"):
            _term(base, 0, set(), {"valid-term"})
        with self.assertRaisesRegex(CorpusError, "duplicate term forms"):
            _term(base, 0, {"valid term"}, set())

    def test_resolution_rejects_shared_rule_weakening(self) -> None:
        corpus = type("CorpusStub", (), {})()
        corpus.terms = (
            TermRule("blocked", ("blocked",), "Use a precise term.", (), "error", "off", "off"),
            TermRule("weak", ("weak",), "Use a precise term.", (), "warning", "off", "off"),
            TermRule("ignored", ("ignored",), "No prose rule.", (), "off", "off", "off"),
        )
        corpus.locale = "en-GB"
        corpus.accepted = ()
        corpus.acronyms = ()
        corpus.hedges = ()
        corpus.fillers = ()
        corpus.roles = {}
        corpus.sources = {}
        corpus.identifier_accepted = ()
        corpus.documents = {}
        with self.assertRaisesRegex(CorpusError, "cannot disable shared rules"):
            _resolved(corpus, ConsumerVocabulary(("blocked",), (), {}, (), {}, (), None, {}))
        with self.assertRaisesRegex(CorpusError, "copies shared errors"):
            _resolved(corpus, ConsumerVocabulary((), ("blocked",), {}, (), {}, (), None, {}))
        resolved = _resolved(
            corpus,
            ConsumerVocabulary((), ("weak",), {}, (), {}, (), "en-US", {}),
        )
        self.assertEqual(resolved["locale"], "en-US")
        self.assertEqual(resolved["repository_errors"], ["weak"])
        shared_warnings = resolved["shared_warnings"]
        self.assertIsInstance(shared_warnings, list)
        assert isinstance(shared_warnings, list)
        self.assertNotIn("weak", shared_warnings)
        shared_rules = resolved["shared_prose_rules"]
        repository_rules = resolved["repository_prose_rules"]
        assert isinstance(shared_rules, list)
        assert isinstance(repository_rules, list)
        self.assertEqual(shared_rules[0]["id"], "blocked")
        self.assertEqual(repository_rules[0]["id"], "promoted-weak")
        self.assertEqual(repository_rules[0]["guidance"], "Use a precise term.")


class ConsumerVocabularyBoundaryTests(unittest.TestCase):
    def _load(self, value: str) -> ConsumerVocabulary:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "consumer"
        target.mkdir()
        _consumer(target, VALID_VOCABULARY)
        (target / ".qat-vocabulary.toml").write_text(value, encoding="utf-8")
        return load_consumer_vocabulary(target)

    def test_consumer_schema_rejects_invalid_sections(self) -> None:
        cases = (
            ("schema_version = 2\n", "schema_version must be 1"),
            ("schema_version = 1\n[terminology]\nreplacements = []\n", "expected a table"),
            (
                "schema_version = 1\n[terminology.replacements]\nterm = 1\n",
                "expected string values",
            ),
            ('schema_version = 1\n[settings]\nlocale = ""\n', "non-empty string"),
            ("schema_version = 1\nallowances = {}\n", "array of tables"),
        )
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(CorpusError, message):
                self._load(value)

    def test_allowances_require_identity_and_bounded_paths(self) -> None:
        cases = (
            (
                'schema_version = 1\n[[allowances]]\nterm = "x"\npaths = ["docs/**"]\n',
                "term and reason",
            ),
            (
                'schema_version = 1\n[[allowances]]\nterm = "x"\nreason = "quote"\npaths = []\n',
                "may not be empty",
            ),
            (
                'schema_version = 1\n[[allowances]]\nterm = "x"\n'
                'reason = "quote"\npaths = ["../outside"]\n',
                "relative",
            ),
        )
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(CorpusError, message):
                self._load(value)


class CorpusGenerationBoundaryTests(unittest.TestCase):
    def test_output_generation_selects_us_locale_and_rejects_unknown_locale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "us"
            stage.mkdir()
            resolved: dict[str, object] = {
                "locale": "en-US",
                "shared_errors": [],
                "shared_warnings": [],
                "repository_errors": [],
                "accepted": [],
                "identifier_accepted": [],
                "identifier_rejections": [],
                "roles": {},
                "commit_rules": [],
                "sources": {},
                "documents": {},
                "allowances": [],
            }
            digest = _write_outputs(stage, toolkit_root(), resolved)
            self.assertEqual(len(digest), 64)
            configuration = (stage / "vale/.vale.ini").read_text(encoding="utf-8")
            self.assertIn("STECode.BritishSpelling = NO", configuration)
            invalid = Path(directory) / "invalid"
            invalid.mkdir()
            with self.assertRaisesRegex(CorpusError, "unsupported corpus locale"):
                _write_outputs(invalid, toolkit_root(), {**resolved, "locale": "fr-BE"})

    def test_stale_deployment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "consumer"
            target.mkdir()
            _consumer(target, VALID_VOCABULARY)
            enroll(target, toolkit_root())
            with (
                patch("qa_toolkit.corpus.status", return_value={"current": False}),
                self.assertRaisesRegex(CorpusError, "deployment is stale"),
            ):
                build_corpus(target)

    def test_failed_atomic_generation_restores_previous_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "consumer"
            target.mkdir()
            _consumer(target, VALID_VOCABULARY)
            enroll(target, toolkit_root())
            _, destination = build_corpus(target)
            before = (destination / "resolved.json").read_bytes()

            def fail_after_write(stage: Path, root: Path, resolved: dict[str, object]) -> str:
                (stage / "partial").write_text(json.dumps(resolved), encoding="utf-8")
                raise CorpusError("forced generation failure")

            with (
                patch("qa_toolkit.corpus._write_outputs", side_effect=fail_after_write),
                self.assertRaisesRegex(CorpusError, "forced generation failure"),
            ):
                build_corpus(target)
            self.assertEqual((destination / "resolved.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
