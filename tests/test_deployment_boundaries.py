"""Failure and cleanup boundaries for repository deployment."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from test_deployment import _central, _consumer

from qa_toolkit import deployment
from qa_toolkit.config import load_profile
from qa_toolkit.deployment import DeploymentError
from qa_toolkit.hook_deployment import HookDeploymentError
from qa_toolkit.models import ConfigurationError, Consumer, Profile


class GitInspectionBoundaryTests(unittest.TestCase):
    def test_git_commands_and_target_resolution_fail_closed(self) -> None:
        for effect in (OSError("missing"), subprocess.TimeoutExpired(("git",), 1)):
            with patch("qa_toolkit.deployment.subprocess.run", side_effect=effect):
                with self.assertRaisesRegex(DeploymentError, "Git command failed"):
                    deployment._git(Path("."), ["status"])
                with self.assertRaisesRegex(DeploymentError, "Git inspection failed"):
                    deployment.git_bytes(Path("."), "status")
        completed = subprocess.CompletedProcess([], 1, "", "failed")
        with patch("qa_toolkit.deployment.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(DeploymentError, "failed"):
                deployment._git(Path("."), ["status"])
            self.assertEqual(deployment._git(Path("."), ["status"], check=False), completed)
        with (
            patch(
                "qa_toolkit.deployment._git",
                return_value=subprocess.CompletedProcess(
                    [],
                    0,
                    f"{Path(tempfile.gettempdir()) / 'not-a-repository'}\n",
                    "",
                ),
            ),
            self.assertRaisesRegex(DeploymentError, "ordinary Git worktree"),
        ):
            deployment.resolve_target(Path("."))

    def test_tracked_entries_regular_files_and_fallback_tracking(self) -> None:
        output = b"100644 a 0\tfile.txt\0"
        with patch("qa_toolkit.deployment.git_bytes", return_value=output):
            self.assertEqual(deployment.tracked_entries(Path(".")), (("100644", "file.txt"),))
        with (
            patch("qa_toolkit.deployment.git_bytes", side_effect=DeploymentError("bad")),
            self.assertRaisesRegex(DeploymentError, "cannot list tracked"),
        ):
            deployment.tracked_entries(Path("."))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            (target / "file.txt").write_text("text", encoding="utf-8")
            (target / "link.txt").symlink_to(target / "file.txt")
            entries = (("100644", "file.txt"), ("100644", "link.txt"), ("160000", "submodule"))
            with patch("qa_toolkit.deployment.tracked_entries", return_value=entries):
                self.assertEqual(deployment.tracked_regular_files(target), ("file.txt",))
        first = subprocess.CompletedProcess([], 1, "", "")
        second = subprocess.CompletedProcess([], 0, "path\n", "")
        with patch("qa_toolkit.deployment._git", side_effect=(first, second)):
            self.assertTrue(deployment._tracked(Path("."), Path("directory")))

    def test_declared_consumer_paths_and_gate_executables_must_be_tracked(self) -> None:
        consumer = SimpleNamespace(
            native_configurations=(Path("missing.toml"),),
            vocabulary_file=None,
            ast_grep_config=None,
            ast_grep_tests=None,
            python=SimpleNamespace(project=None),
            gates=(),
        )
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            (target / ".qat.toml").write_text("", encoding="utf-8")
            with (
                patch("qa_toolkit.deployment._tracked", return_value=True),
                self.assertRaisesRegex(DeploymentError, "does not exist"),
            ):
                deployment._validate_consumer_paths(target, cast(Consumer, consumer))
            (target / "missing.toml").write_text("", encoding="utf-8")
            with (
                patch("qa_toolkit.deployment._tracked", return_value=False),
                self.assertRaisesRegex(DeploymentError, "is not tracked"),
            ):
                deployment._validate_consumer_paths(target, cast(Consumer, consumer))
            gate = SimpleNamespace(argv=("scripts/live.sh",))
            consumer.gates = (gate,)
            with (
                patch(
                    "qa_toolkit.deployment._tracked",
                    side_effect=lambda _target, path: path != Path("scripts/live.sh"),
                ),
                self.assertRaisesRegex(DeploymentError, "executable is not tracked"),
            ):
                deployment._validate_consumer_paths(target, cast(Consumer, consumer))


class OwnershipBoundaryTests(unittest.TestCase):
    def test_revision_records_and_owned_paths_reject_substitution(self) -> None:
        with (
            patch(
                "qa_toolkit.deployment._git",
                return_value=subprocess.CompletedProcess([], 0, "short\n", ""),
            ),
            self.assertRaisesRegex(DeploymentError, "exact revision"),
        ):
            deployment._revision(Path("."))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw).resolve()
            record = target / ".git/qat/deployment.json"
            record.parent.mkdir(parents=True)
            for value, message in (
                ("not json", "not enrolled"),
                (json.dumps({"schema_version": 2}), "unsupported"),
                (
                    json.dumps({"schema_version": 1, "target_root": "/other"}),
                    "another repository",
                ),
            ):
                record.write_text(value, encoding="utf-8")
                with (
                    self.subTest(message=message),
                    self.assertRaisesRegex(DeploymentError, message),
                ):
                    deployment._load_record(target)
            missing = {"path": "missing", "kind": "symlink", "target": "source"}
            self.assertEqual(deployment._owned_current(target, missing)[1], "missing-or-replaced")
            path = target / "copy"
            path.write_text("changed", encoding="utf-8")
            copy = {"path": "copy", "kind": "copy", "digest": "0" * 64}
            self.assertEqual(deployment._owned_current(target, copy), (False, "modified"))

    def test_exclude_reconciliation_supports_legacy_records(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            exclude = target / ".git/info/exclude"
            exclude.parent.mkdir(parents=True)
            exclude.write_text("existing\n.qat/\n", encoding="utf-8")
            record = deployment._reconcile_exclude(
                target,
                {"owned": True, "line": ".qat/", "before": "existing\n"},
                (".agents/skills/",),
            )
            self.assertNotIn(".qat/", exclude.read_text(encoding="utf-8"))
            self.assertEqual(record["owned"], [".agents/skills/"])

    def test_skill_reconciliation_refuses_foreign_or_modified_links(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            target.mkdir()
            skill = root / "library/skills/sample"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("sample", encoding="utf-8")
            profile = Profile(
                "fixture",
                (),
                (),
                (),
                (),
                (Path("library/skills/sample"),),
                root / "profile.toml",
            )
            foreign = target / ".agents/skills/sample"
            foreign.mkdir(parents=True)
            with self.assertRaisesRegex(DeploymentError, "foreign skill"):
                deployment._reconcile_skills(target, root, profile)
            foreign.rmdir()
            records = deployment._reconcile_skills(target, root, profile)
            foreign = target / records[0]["path"]
            foreign.unlink()
            foreign.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(DeploymentError, "modified managed skill"):
                deployment._reconcile_skills(target, root, profile, records)
            with self.assertRaisesRegex(DeploymentError, "modified managed skills"):
                deployment._remove_skills(
                    target,
                    root,
                    records,
                    backup=None,
                    hard_reset=False,
                )

    def test_merge_and_backup_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw) / "merge"
            completed = subprocess.CompletedProcess([], 2, b"", b"failure")
            with (
                patch("qa_toolkit.deployment.subprocess.run", return_value=completed),
                self.assertRaisesRegex(DeploymentError, "merge-file failed"),
            ):
                deployment._merge_copy(b"local", b"base", b"incoming", directory)
            target = Path(raw) / "target"
            backup = Path(raw) / "backup"
            target.mkdir()
            (target / "source").symlink_to("destination")
            deployment._backup_path(target, Path("source"), backup)
            self.assertEqual(os.readlink(backup / "source"), "destination")


class DeploymentTransactionTests(unittest.TestCase):
    def test_enrollment_failure_removes_partial_paths_and_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            before = (target / ".git/info/exclude").read_bytes()
            with (
                patch(
                    "qa_toolkit.deployment.reconcile_hooks",
                    side_effect=RuntimeError("forced hook failure"),
                ),
                self.assertRaisesRegex(RuntimeError, "forced hook failure"),
            ):
                deployment.enroll(target, root)
            self.assertFalse((target / ".qat").exists())
            self.assertFalse((target / ".git/qat").exists())
            self.assertEqual((target / ".git/info/exclude").read_bytes(), before)

    def test_enrollment_and_unenrollment_reject_unsafe_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            (target / ".qat/config").mkdir(parents=True)
            (target / ".qat/config/link.txt").write_text("foreign", encoding="utf-8")
            with self.assertRaisesRegex(DeploymentError, "foreign path"):
                deployment.enroll(target, root)
            (target / ".qat/config/link.txt").unlink()
            (target / ".qat/config").rmdir()
            (target / ".qat").rmdir()
            deployment.enroll(target, root)
            with self.assertRaisesRegex(DeploymentError, "intentionally unsupported"):
                deployment.unenroll(target, purge_config=True)
            with self.assertRaisesRegex(DeploymentError, "outside the target"):
                deployment.unenroll(target, backup=target / "backup")
            with (
                patch(
                    "qa_toolkit.deployment.remove_hooks",
                    side_effect=HookDeploymentError("modified hook"),
                ),
                self.assertRaisesRegex(DeploymentError, "modified hook"),
            ):
                deployment.unenroll(target, hard_reset=True)

    def test_late_enrollment_failure_removes_hooks_skills_and_owned_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            with (
                patch("qa_toolkit.deployment._toolkit_revision", return_value="a" * 40),
                patch(
                    "qa_toolkit.deployment._revision",
                    side_effect=DeploymentError("target revision failed"),
                ),
                self.assertRaisesRegex(DeploymentError, "target revision failed"),
            ):
                deployment.enroll(target, root)
            self.assertFalse((target / ".qat").exists())
            self.assertFalse((target / ".agents").exists())
            self.assertFalse((target / ".git/qat").exists())

    def test_sync_retains_local_copy_and_rejects_missing_or_modified_removal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            deployment.enroll(target, root)
            copied = target / ".qat/config/copy.txt"
            copied.write_text("local only\n", encoding="utf-8")
            deployment.sync(target, root)
            self.assertEqual(copied.read_text(encoding="utf-8"), "local only\n")
            copied.unlink()
            with self.assertRaisesRegex(DeploymentError, "requires --hard-reset"):
                deployment.sync(target, root)
            deployment.sync(target, root, hard_reset=True)
            copied.write_text("modified removal\n", encoding="utf-8")
            profile = load_profile("fixture", root)
            without_copy = replace(
                profile,
                configurations=tuple(
                    item for item in profile.configurations if item.identifier != "copied"
                ),
            )
            with (
                patch("qa_toolkit.deployment.load_profile", return_value=without_copy),
                self.assertRaisesRegex(DeploymentError, "modified removed path"),
            ):
                deployment.sync(target, root)

    def test_existing_record_and_profile_validation_errors_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "central"
            target = parent / "consumer"
            root.mkdir()
            target.mkdir()
            _central(root)
            _consumer(target)
            deployment.enroll(target, root)
            with self.assertRaisesRegex(DeploymentError, "already enrolled"):
                deployment.enroll(target, root)
            with (
                patch(
                    "qa_toolkit.deployment.load_profile",
                    side_effect=ConfigurationError("invalid profile"),
                ),
                self.assertRaisesRegex(DeploymentError, "invalid profile"),
            ):
                deployment.validate_profile("fixture", root)


if __name__ == "__main__":
    unittest.main()
