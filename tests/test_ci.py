"""Static checks for exact-revision reusable CI."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
ACTION = re.compile(r"^\s*uses:\s+([^\s]+)@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)


class WorkflowTests(unittest.TestCase):
    def test_reusable_workflow_requires_and_verifies_exact_revision(self) -> None:
        path = ROOT / ".github/workflows/reusable-sentinel.yml"
        content = path.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", content)
        self.assertIn("toolkit_revision:", content)
        self.assertIn('test "${#TOOLKIT_REVISION}" -eq 40', content)
        self.assertIn("git -C toolkit rev-parse HEAD)", content)
        self.assertIn("repository: amaurigmartins/qa-toolkit", content)
        self.assertIn("github.repository == 'amaurigmartins/qa-toolkit'", content)
        self.assertIn("ln -s ../toolkit/toolkit target/toolkit", content)
        self.assertEqual(content.count("name: Run Sentinel once"), 1)
        self.assertIn("target/.git/qat/evidence", content)
        self.assertNotIn("unslopifier", content.casefold())
        references = ACTION.findall(content)
        self.assertEqual(len(references), 3)
        self.assertTrue(all(len(revision) == 40 for _action, revision in references))

    def test_self_workflow_calls_only_the_local_reusable_workflow(self) -> None:
        content = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/reusable-sentinel.yml", content)
        self.assertIn("github.event.pull_request.head.sha || github.sha", content)
        self.assertIn("Julia 1.10.11 / 1.12.6", content)
        self.assertNotIn("bin/qat sentinel", content)


if __name__ == "__main__":
    unittest.main()
