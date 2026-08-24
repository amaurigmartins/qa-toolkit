"""Tests for source decisions owned by the central corpus."""

from __future__ import annotations

import unittest

from qa_toolkit.corpus import load_corpus
from qa_toolkit.source_decisions import classify_source, is_gitlab_cache_key


class SourceDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = load_corpus()

    def test_generated_patterns_cover_root_and_nested_lock_files(self) -> None:
        for path in ("uv.lock", "docs/package-lock.json", "src/generated/table.py"):
            with self.subTest(path=path):
                self.assertEqual(classify_source(path, "", self.corpus).classification, "generated")

    def test_license_name_alone_does_not_exempt_unverified_prose(self) -> None:
        decision = classify_source("LICENSE", "A bespoke statement.", self.corpus)
        self.assertEqual(decision.classification, "source")

    def test_standard_mit_markers_are_recognized(self) -> None:
        text = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""
        decision = classify_source("LICENSE.md", text, self.corpus)
        self.assertEqual(decision.classification, "standard-license")
        self.assertIn("MIT", decision.reason)

    def test_gitlab_cache_keys_are_explicit(self) -> None:
        self.assertTrue(is_gitlab_cache_key("files_commits", self.corpus))
        self.assertFalse(is_gitlab_cache_key("fallback_keys", self.corpus))


if __name__ == "__main__":
    unittest.main()
