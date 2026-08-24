"""Tests for single-corpus resolution and generated tool inputs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.corpus import CorpusError, build_corpus, load_corpus
from qa_toolkit.deployment import enroll, sync
from qa_toolkit.paths import toolkit_root
from test_deployment import _git


def _consumer(target: Path, vocabulary: str) -> None:
    _git(target, "init", "-b", "main")
    (target / ".qat.toml").write_text(
        """schema_version = 1
profile = "disposable-documentation"
native_configurations = []
protected_paths = []

[vocabulary]
file = ".qat-vocabulary.toml"
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
""",
        encoding="utf-8",
    )
    (target / ".qat-vocabulary.toml").write_text(vocabulary, encoding="utf-8")
    _git(target, "add", "-A")
    _git(
        target,
        "-c",
        "user.name=QA Toolkit Test",
        "-c",
        "user.email=qa-toolkit@example.invalid",
        "commit",
        "-m",
        "test(repo): create corpus consumer",
    )


VALID_VOCABULARY = """schema_version = 1

[terminology]
accepted = ["Gridform"]
rejected = ["robust", "project puff"]

[terminology.replacements]
utilize = "use"

[acronyms]
accepted = ["RLS"]

[roles]
concept = ["form_entry"]

[[allowances]]
term = "robust"
paths = ["docs/quoted-source.md"]
reason = "The document quotes a retained external title."

[sources]
generated_patterns = ["generated-api/**"]
"""


class CorpusTests(unittest.TestCase):
    def test_corpus_retains_source_and_advisory_rule_inventory(self) -> None:
        corpus = load_corpus()
        self.assertGreaterEqual(len(corpus.terms), 20)
        self.assertIn("GPL-3.0", corpus.sources["license_families"])
        self.assertIn("**/uv.lock", corpus.sources["generated_patterns"])
        rules = list((toolkit_root() / corpus.ai_tells_directory).glob("*.yml"))
        self.assertGreaterEqual(len(rules), 100)

    def test_build_promotes_shared_warning_without_duplicate_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "consumer"
            target.mkdir()
            _consumer(target, VALID_VOCABULARY)
            enroll(target, toolkit_root())

            digest, destination = build_corpus(target)

            self.assertEqual(len(digest), 64)
            resolved = json.loads((destination / "resolved.json").read_text(encoding="utf-8"))
            self.assertNotIn("robust", resolved["shared_warnings"])
            self.assertIn("robust", resolved["repository_errors"])
            self.assertIn("Gridform", resolved["accepted"])
            self.assertIn("RLS", resolved["acronyms"])
            self.assertIn("form_entry", resolved["roles"]["concept"])
            self.assertTrue((destination / "vale/styles/ai-tells").is_symlink())
            cspell = json.loads((destination / "cspell.json").read_text(encoding="utf-8"))
            self.assertIn("Gridform", cspell["words"])

    def test_invalid_consumer_rule_leaves_previous_generated_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "consumer"
            target.mkdir()
            _consumer(target, VALID_VOCABULARY)
            enroll(target, toolkit_root())
            _, destination = build_corpus(target)
            before = (destination / "resolved.json").read_bytes()
            (target / ".qat-vocabulary.toml").write_text(
                """schema_version = 1
[terminology]
accepted = []
rejected = ["orchestration"]
""",
                encoding="utf-8",
            )
            sync(target, toolkit_root())

            with self.assertRaisesRegex(CorpusError, "copies shared errors"):
                build_corpus(target)

            self.assertEqual((destination / "resolved.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
