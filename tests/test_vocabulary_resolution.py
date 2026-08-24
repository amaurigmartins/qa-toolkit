"""Integration tests for schema-3 consumer vocabulary ownership."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_corpus import _consumer
from test_vocabulary import POLICY

from qa_toolkit.config import load_consumer
from qa_toolkit.corpus import build_corpus, load_consumer_vocabulary
from qa_toolkit.deployment import enroll
from qa_toolkit.paths import toolkit_root
from qa_toolkit.vocabulary import resolve_vocabulary


class VocabularyResolutionTests(unittest.TestCase):
    def _target(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "consumer"
        target.mkdir()
        _consumer(target, POLICY)
        return target

    def test_schema_three_drives_corpus_and_one_semantic_gate(self) -> None:
        target = self._target()
        consumer = load_consumer(target)
        vocabulary = load_consumer_vocabulary(target)
        resolution = resolve_vocabulary(consumer, target=target, root=toolkit_root())

        self.assertIn("design", vocabulary.roles["selector"])
        self.assertEqual(
            [gate.identifier for gate in resolution.gates],
            ["python-semantic-vocabulary"],
        )
        self.assertEqual(len(resolution.digest or ""), 64)

        enroll(target, toolkit_root())
        _digest, destination = build_corpus(target)
        resolved = json.loads((destination / "resolved.json").read_text(encoding="utf-8"))
        self.assertIn("Gridform", resolved["accepted"])
        self.assertIn("design", resolved["roles"]["selector"])
        self.assertEqual(resolved["locale"], "en-US")
        self.assertIn("Gridform", resolved["literal_allowances"])


if __name__ == "__main__":
    unittest.main()
