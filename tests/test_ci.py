"""Static checks for repository-owned CI."""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
ACTION = re.compile(r"^\s*uses:\s+([^\s]+)@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)


class WorkflowTests(unittest.TestCase):
    def test_gridform_audits_the_installed_product_environment(self) -> None:
        profile = tomllib.loads((ROOT / "profiles/gridform.toml").read_text(encoding="utf-8"))
        gate = next(item for item in profile["gates"] if item["id"] == "python-dependencies")
        self.assertEqual(
            gate["argv"],
            [
                "{tool:pip-audit}",
                "--path",
                ".venv/lib/python3.11/site-packages",
                "--skip-editable",
                "--cache-dir",
                ".git/qat/cache/pip-audit",
                "--progress-spinner",
                "off",
            ],
        )

    def test_self_workflow_executes_only_the_checked_out_repository(self) -> None:
        content = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertNotIn("workflow_call:", content)
        self.assertNotIn("toolkit_revision", content)
        self.assertNotIn("repository: amaurigmartins/qa-toolkit", content)
        self.assertNotIn("reusable-sentinel", content)
        self.assertIn("Julia 1.10.11 / 1.12.6", content)
        self.assertEqual(content.count("name: Run local Sentinel once"), 1)
        self.assertIn("./bin/qat sentinel --target .", content)
        self.assertIn("path: .git/qat/evidence", content)
        references = ACTION.findall(content)
        self.assertEqual(len(references), 2)
        self.assertTrue(all(len(revision) == 40 for _action, revision in references))

    def test_qat_exposes_no_remote_consumer_ci_runtime(self) -> None:
        self.assertFalse((ROOT / ".github/workflows/reusable-sentinel.yml").exists())
        self.assertFalse((ROOT / ".github/actions/sentinel/action.yml").exists())


if __name__ == "__main__":
    unittest.main()
