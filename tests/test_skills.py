"""Distribution checks for explicit repository-local work-package skills."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from qa_toolkit.config import load_profile
from qa_toolkit.deployment import enroll, status

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
JULIA_SKILLS = (
    "julia-structural-design",
    "julia-convergence-review",
)
JULIA_READERS = {
    "julia-structural-design": "read_structural_sections.py",
    "julia-convergence-review": "read_convergence_sections.py",
}
PROSE_REVIEW_SKILL = "review-technical-prose"
MINIMAL_TASK_SKILL = "minimal-task-preflight"
REFERENCE_READER = ROOT / "library/skills/_support/read_sections.py"
EXCERPT_INDEXES = (
    ROOT / "library/skills/julia-structural-design/references/sections.toml",
    ROOT / "library/skills/julia-convergence-review/references/sections.toml",
    ROOT / "library/skills/minimal-task-preflight/references/sections.toml",
)


def _git(target: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(target), *arguments],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
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


class JuliaSkillTests(unittest.TestCase):
    def test_julia_skills_are_explicit_and_use_the_section_reader(self) -> None:
        for name in JULIA_SKILLS:
            with self.subTest(skill=name):
                root = ROOT / "library/skills" / name
                content = (root / "SKILL.md").read_text(encoding="utf-8")
                match = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", content)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.group(1), name)
                self.assertNotIn("[TODO:", content)
                metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
                self.assertIn("allow_implicit_invocation: false", metadata)
                self.assertIn(f"${name}", metadata)
                reader = root / "scripts" / JULIA_READERS[name]
                self.assertTrue(reader.is_symlink())
                self.assertEqual(reader.resolve(), REFERENCE_READER.resolve())
                self.assertTrue((root / "references/sections.toml").is_file())
                self.assertEqual(
                    {path.name for path in (root / "references").iterdir()},
                    {"sections.toml"},
                )

    def test_julia_profiles_select_both_repository_local_skills(self) -> None:
        expected = {Path("library/skills") / name for name in JULIA_SKILLS}
        for profile_name in ("disposable-julia", "linecablemodels"):
            with self.subTest(profile=profile_name):
                profile = load_profile(profile_name, ROOT)
                self.assertTrue(expected.issubset(set(profile.skills)))

    def test_disposable_julia_enrollment_owns_selected_skill_links(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "consumer"
            target.mkdir()
            _git(target, "init", "-b", "main")
            (target / ".qat.toml").write_text(
                """schema_version = 1
profile = "disposable-julia"
native_configurations = []
protected_paths = []

[vocabulary]
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
""",
                encoding="utf-8",
            )
            _git(target, "add", ".qat.toml")
            _git(
                target,
                "-c",
                "user.name=QA Toolkit Test",
                "-c",
                "user.email=qa-toolkit@example.invalid",
                "commit",
                "-m",
                "test(repo): create disposable Julia consumer",
            )

            enroll(target, ROOT)

            deployed = status(target, ROOT)["skills"]
            self.assertTrue(all(item["current"] for item in deployed))
            self.assertEqual(
                {Path(item["path"]).name for item in deployed},
                {*JULIA_SKILLS, PROSE_REVIEW_SKILL, MINIMAL_TASK_SKILL},
            )
            for name in (*JULIA_SKILLS, PROSE_REVIEW_SKILL, MINIMAL_TASK_SKILL):
                path = target / ".agents/skills" / name
                self.assertTrue(path.is_symlink())
                self.assertEqual(path.resolve(), (ROOT / "library/skills" / name).resolve())

            invocations = (
                (
                    "julia-structural-design",
                    "read_structural_sections.py",
                    "native-admission",
                    "## 4. Abstraction admission procedure",
                ),
                (
                    "julia-convergence-review",
                    "read_convergence_sections.py",
                    "cleanup-reconstruct",
                    "## 1. First reconstruct the repository truth",
                ),
                (
                    MINIMAL_TASK_SKILL,
                    "read_task_sections.py",
                    "task-authority",
                    "## 1. Treat the supplied task as the authority",
                ),
            )
            for skill, script, excerpt_name, heading in invocations:
                skill_root = target / ".agents/skills" / skill
                result = subprocess.run(
                    [
                        sys.executable,
                        str(skill_root / "scripts" / script),
                        "--index",
                        str(skill_root / "references/sections.toml"),
                        excerpt_name,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    shell=False,
                )
                self.assertTrue(result.stdout.startswith(heading))


class ExcerptReaderTests(unittest.TestCase):
    @staticmethod
    def _expected(source: Path, start: str, end: str | None) -> str:
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
        first = next(index for index, line in enumerate(lines) if line.rstrip("\r\n") == start)
        last = (
            len(lines)
            if end is None
            else next(
                index
                for index, line in enumerate(lines)
                if index > first and line.rstrip("\r\n") == end
            )
        )
        return "".join(lines[first:last]).rstrip() + "\n"

    def test_every_excerpt_is_exact_bounded_and_small(self) -> None:
        for index in EXCERPT_INDEXES:
            document = tomllib.loads(index.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], 1)
            for name, raw in document["chunk"].items():
                with self.subTest(index=index.parent.parent.name, excerpt=name):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(REFERENCE_READER),
                            "--index",
                            str(index),
                            name,
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=False,
                    )
                    source = (index.parent / raw["source"]).resolve()
                    self.assertEqual(
                        result.stdout,
                        self._expected(source, raw["start"], raw.get("end")),
                    )
                    self.assertLessEqual(len(result.stdout.splitlines()), 320)

    def test_reader_rejects_an_unknown_excerpt(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REFERENCE_READER),
                "--index",
                str(EXCERPT_INDEXES[0]),
                "missing-excerpt",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown excerpt", result.stderr)


class ProseReviewSkillTests(unittest.TestCase):
    def test_skill_is_explicit_and_references_the_owned_guide(self) -> None:
        root = ROOT / "library/skills" / PROSE_REVIEW_SKILL
        content = (root / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", content)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), PROSE_REVIEW_SKILL)
        self.assertNotIn("[TODO:", content)
        self.assertIn("qat advisory --target TARGET", content)

        metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn(f"${PROSE_REVIEW_SKILL}", metadata)

        reference = root / "references/writing-guidelines.md"
        self.assertTrue(reference.is_symlink())
        self.assertEqual(
            reference.resolve(),
            (ROOT / "library/instructions/writing-guidelines.md").resolve(),
        )

    def test_prose_profiles_select_the_explicit_review_skill(self) -> None:
        expected = Path("library/skills") / PROSE_REVIEW_SKILL
        for profile_name in (
            "qa-toolkit",
            "gridform",
            "linecablemodels",
            "disposable-python",
            "disposable-julia",
            "disposable-documentation",
        ):
            with self.subTest(profile=profile_name):
                profile = load_profile(profile_name, ROOT)
                self.assertIn(expected, profile.skills)


class MinimalTaskSkillTests(unittest.TestCase):
    def test_skill_is_explicit_and_uses_the_retained_prompt_by_excerpt(self) -> None:
        root = ROOT / "library/skills" / MINIMAL_TASK_SKILL
        content = (root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python scripts/read_task_sections.py", content)
        self.assertNotIn("[TODO:", content)
        metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn(f"${MINIMAL_TASK_SKILL}", metadata)
        reader = root / "scripts/read_task_sections.py"
        self.assertTrue(reader.is_symlink())
        self.assertEqual(reader.resolve(), REFERENCE_READER.resolve())

        index = tomllib.loads((root / "references/sections.toml").read_text(encoding="utf-8"))
        sources = {
            (root / "references" / raw["source"]).resolve() for raw in index["chunk"].values()
        }
        self.assertEqual(
            sources,
            {ROOT / "library/prompts/prompt-newtask-minimal.md"},
        )

    def test_repository_profiles_select_the_manual_preflight(self) -> None:
        expected = Path("library/skills") / MINIMAL_TASK_SKILL
        for profile_name in (
            "qa-toolkit",
            "gridform",
            "linecablemodels",
            "disposable-python",
            "disposable-julia",
            "disposable-documentation",
            "disposable-hooks",
        ):
            with self.subTest(profile=profile_name):
                self.assertIn(expected, load_profile(profile_name, ROOT).skills)


if __name__ == "__main__":
    unittest.main()
