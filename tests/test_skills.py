"""Distribution checks for explicit repository-local work-package skills."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILLS = (
    "plan-work-package",
    "stage-work-item",
    "execute-work-item",
    "reconcile-work-item",
    "run-work-package",
    "close-work-package",
    "release-work-package",
)


class WorkSkillTests(unittest.TestCase):
    def test_skills_are_closed_explicit_and_invoke_structured_utilities(self) -> None:
        for name in SKILLS:
            with self.subTest(skill=name):
                root = ROOT / "library" / "skills" / name
                content = (root / "SKILL.md").read_text(encoding="utf-8")
                match = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", content)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.group(1), name)
                self.assertNotIn("<", match.group(2))
                self.assertNotIn("[TODO:", content)
                self.assertIn("qat ", content)
                metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
                self.assertIn("allow_implicit_invocation: false", metadata)
                self.assertIn(f"${name}", metadata)

    def test_work_templates_are_bounded_human_inputs(self) -> None:
        templates = ROOT / "library" / "work-packages" / "templates"
        self.assertEqual(
            {item.stem for item in templates.glob("*.md")},
            {"plan", "breakdown", "reconcile", "cleanup", "release"},
        )
        for path in templates.glob("*.md"):
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.strip())
            self.assertLess(len(content.encode()), 262_144)
            self.assertNotIn("[TODO:", content)


if __name__ == "__main__":
    unittest.main()
