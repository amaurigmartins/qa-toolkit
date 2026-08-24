"""Tests for exact repository enrollment, synchronization, and removal."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.deployment import DeploymentError, enroll, status, sync, unenroll
from qa_toolkit.paths import toolkit_root


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return result.stdout.strip()


def _commit(repository: Path) -> None:
    _git(repository, "add", "-A")
    _git(
        repository,
        "-c",
        "user.name=QA Toolkit Test",
        "-c",
        "user.email=qa-toolkit@example.invalid",
        "commit",
        "-m",
        "test(repo): create fixture",
    )


def _central(root: Path) -> None:
    (root / "registry").mkdir(parents=True)
    (root / "registry/tools.json").write_bytes(
        (toolkit_root() / "registry/tools.json").read_bytes()
    )
    (root / "config/sample").mkdir(parents=True)
    (root / "config/sample/link.txt").write_text("linked\n", encoding="utf-8")
    (root / "config/sample/copy.txt").write_text("alpha\nbase\ngamma\n", encoding="utf-8")
    (root / "profiles").mkdir()
    (root / "profiles/fixture.toml").write_text(
        """schema_version = 1
name = "fixture"
tools = ["jq"]
gates = []
hooks = []
skills = []

[[configurations]]
id = "linked"
source = "config/sample/link.txt"
destination = ".qat/config/link.txt"
mode = "symlink"

[[configurations]]
id = "copied"
source = "config/sample/copy.txt"
destination = ".qat/config/copy.txt"
mode = "copy"
""",
        encoding="utf-8",
    )
    _git(root, "init", "-b", "main")
    _commit(root)


def _consumer(target: Path) -> None:
    _git(target, "init", "-b", "main")
    (target / ".qat.toml").write_text(
        """schema_version = 1
profile = "fixture"
native_configurations = ["native.toml"]
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
    (target / "native.toml").write_text("owned = 'consumer'\n", encoding="utf-8")
    _commit(target)


class DeploymentTests(unittest.TestCase):
    def test_enroll_status_and_unenroll_restore_local_git_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            exclude = target / ".git/info/exclude"
            exclude_before = exclude.read_bytes()

            enroll(target, root)
            report = status(target, root)

            self.assertTrue(report["current"])
            link = target / ".qat/config/link.txt"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.read_text(encoding="utf-8"), "linked\n")
            self.assertEqual(
                (target / ".qat/config/copy.txt").read_text(encoding="utf-8"),
                "alpha\nbase\ngamma\n",
            )
            self.assertIn(".qat/", exclude.read_text(encoding="utf-8").splitlines())

            unenroll(target)

            self.assertFalse((target / ".qat").exists())
            self.assertFalse((target / ".git/qat").exists())
            self.assertEqual(exclude.read_bytes(), exclude_before)
            self.assertTrue((target / ".qat.toml").is_file())
            self.assertTrue((target / "native.toml").is_file())

    def test_sync_merges_distinct_changes_and_leaves_conflicts_outside_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            enroll(target, root)
            copied = target / ".qat/config/copy.txt"
            copied.write_text("alpha-local\nbase\ngamma\n", encoding="utf-8")
            (root / "config/sample/copy.txt").write_text(
                "alpha\nbase\ngamma-new\n", encoding="utf-8"
            )
            self.assertFalse(status(target, root)["current"])

            sync(target, root)

            self.assertEqual(copied.read_text(encoding="utf-8"), "alpha-local\nbase\ngamma-new\n")
            copied.write_text("alpha-consumer\nbase\ngamma-new\n", encoding="utf-8")
            before = copied.read_bytes()
            (root / "config/sample/copy.txt").write_text(
                "alpha-upstream\nbase\ngamma-new\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(DeploymentError, "target unchanged"):
                sync(target, root)

            self.assertEqual(copied.read_bytes(), before)
            conflict = target / ".git/qat/conflicts/copied"
            self.assertTrue((conflict / "local").is_file())
            self.assertTrue((conflict / "incoming").is_file())

    def test_unenroll_requires_backup_for_modified_managed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "central"
            target = parent / "consumer"
            backup = parent / "backup"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            enroll(target, root)
            copied = target / ".qat/config/copy.txt"
            copied.write_text("modified\n", encoding="utf-8")

            with self.assertRaisesRegex(DeploymentError, "require --backup"):
                unenroll(target)

            unenroll(target, backup=backup)
            self.assertEqual(
                (backup / ".qat/config/copy.txt").read_text(encoding="utf-8"), "modified\n"
            )
            self.assertFalse((target / ".git/qat").exists())

    def test_sync_hard_reset_is_the_only_discarding_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            enroll(target, root)
            link = target / ".qat/config/link.txt"
            link.unlink()
            link.symlink_to(os.path.relpath(target / "native.toml", link.parent))

            with self.assertRaisesRegex(DeploymentError, "requires --hard-reset"):
                sync(target, root)

            sync(target, root, hard_reset=True)
            self.assertEqual(link.read_text(encoding="utf-8"), "linked\n")


if __name__ == "__main__":
    unittest.main()
