"""Tests for Git checkout and immutable action source identities."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.source_identity import SourceIdentityError, toolkit_facts, toolkit_revision


class SourceIdentityTests(unittest.TestCase):
    def test_action_marker_supplies_clean_exact_identity_without_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            revision = "a" * 40
            (root / ".qat-toolkit-revision").write_text(f"{revision}\n", encoding="ascii")
            self.assertEqual(toolkit_revision(root), revision)
            self.assertEqual(
                toolkit_facts(root),
                (revision, False, hashlib.sha256(b"").hexdigest()),
            )

    def test_action_marker_rejects_mutable_or_malformed_identity(self) -> None:
        for value in ("main\n", "A" * 40, "a" * 39, "a" * 41):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / ".qat-toolkit-revision").write_text(value, encoding="ascii")
                with self.assertRaises(SourceIdentityError):
                    toolkit_revision(root)

    def test_missing_marker_outside_git_is_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaises(SourceIdentityError),
        ):
            toolkit_revision(Path(temporary))


if __name__ == "__main__":
    unittest.main()
