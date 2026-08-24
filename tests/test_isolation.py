"""Acceptance proof that enrolled repositories share no mutable state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_work import _fixture, _initialize

from qa_toolkit.guardrail_state import breaker_status, open_breaker, proof_status
from qa_toolkit.hook_deployment import set_enabled
from qa_toolkit.runner import execute

ROOT = Path(__file__).parents[1]


class RepositoryIsolationTests(unittest.TestCase):
    def test_two_enrolled_repositories_keep_independent_mutable_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            first_parent = parent / "first"
            second_parent = parent / "second"
            first_parent.mkdir()
            second_parent.mkdir()
            first, _first_remote, first_base = _fixture(first_parent)
            second, _second_remote, second_base = _fixture(second_parent)
            first_work = _initialize(first, first_parent, first_base)
            second_work = _initialize(second, second_parent, second_base)
            first_record = json.loads(
                (first / ".git/qat/deployment.json").read_text(encoding="utf-8")
            )
            second_record = json.loads(
                (second / ".git/qat/deployment.json").read_text(encoding="utf-8")
            )

            set_enabled(first, first_record["hooks"], False, kind="codex", event="PreToolUse")
            open_breaker(first, ROOT, "first repository mutation")
            code, evidence = execute(second, "sentinel", root=ROOT)

            self.assertEqual(code, 0, evidence)
            self.assertTrue(breaker_status(first, ROOT)["open"])
            self.assertFalse(breaker_status(second, ROOT)["open"])
            self.assertFalse(proof_status(first, ROOT)["present"])
            self.assertTrue(proof_status(second, ROOT)["current"])
            self.assertFalse((first / ".git/qat/hooks/codex/PreToolUse/enabled/guardrail").exists())
            self.assertTrue(
                (second / ".git/qat/hooks/codex/PreToolUse/enabled/guardrail").is_symlink()
            )
            self.assertNotEqual(first_record["target_root"], second_record["target_root"])
            self.assertNotEqual(first_work.root, second_work.root)
            self.assertTrue((first_work.root / "state.json").is_file())
            self.assertTrue((second_work.root / "state.json").is_file())
            self.assertTrue(str(evidence).startswith(str(second / ".git/qat/evidence")))
            self.assertFalse((first / ".git/qat/evidence").exists())


if __name__ == "__main__":
    unittest.main()
