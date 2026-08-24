"""Acceptance tests for repository-local structured work packages."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_toolkit.agent_cli import thread_name
from qa_toolkit.deployment import enroll, unenroll
from qa_toolkit.deployment import status as deployment_status
from qa_toolkit.work import WorkError, WorkPackage, WorkState
from qa_toolkit.work_git import (
    bind,
    calculate_release,
    finish,
    initialize,
    reconcile,
    report,
    retire,
    stage,
)

ROOT = Path(__file__).parents[1]


def _git(target: Path, *arguments: str, hooks: bool = False) -> str:
    command = ["git", "-C", str(target)]
    if not hooks:
        command.extend(("-c", "core.hooksPath=/dev/null"))
    completed = subprocess.run(
        [*command, *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    return completed.stdout.strip()


def _fixture(parent: Path) -> tuple[Path, Path, str]:
    remote = parent / "remote.git"
    _git(parent, "init", "--bare", str(remote))
    target = parent / "consumer"
    target.mkdir()
    _git(parent, "init", "-b", "main", str(target))
    _git(target, "config", "user.name", "QA Toolkit")
    _git(target, "config", "user.email", "qat@example.invalid")
    (target / ".qat.toml").write_text(
        """schema_version = 1
profile = "disposable-hooks"
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
    (target / "app.txt").write_text("base\n", encoding="utf-8")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "test(repo): create work target")
    base = _git(target, "rev-parse", "HEAD")
    _git(target, "remote", "add", "origin", str(remote))
    _git(target, "push", "-u", "origin", "main")
    enroll(target, ROOT)
    return target, remote, base


def _inputs(parent: Path, task: str = "C01") -> tuple[Path, Path]:
    plan = parent / f"{task}-plan.md"
    current = parent / f"{task}-task.md"
    plan.write_text("# Accepted\n\nOne exact task.\n", encoding="utf-8")
    current.write_text(f"# {task}\n\nChange app.txt.\n", encoding="utf-8")
    return plan, current


def _initialize(
    target: Path,
    parent: Path,
    base: str,
    *,
    task: str = "C01",
    revision: int = 1,
    proof: str = "check",
    cleanup: bool = False,
) -> WorkPackage:
    plan, current = _inputs(parent, task)
    utility = ROOT / "bin" / f"qat-{proof}"
    return initialize(
        target,
        work_id="managed-change",
        repository="owner/repository",
        issue=42,
        pull_request=43 if revision > 1 else None,
        remote="origin",
        kind="refactor",
        branch="refactor/managed-change",
        base_branch="main",
        base_sha=base if revision == 1 else _git(target, "rev-parse", "main"),
        plan_revision=revision,
        task_id=task,
        task_title="change managed file",
        expected_parent=_git(target, "rev-parse", "HEAD"),
        final_subject=f"refactor(core): apply managed change {task.lower()}",
        allowed_paths=("app.txt",),
        validation_argv=((str(utility), "--target", "."),),
        quality_proof=proof,
        plan_source=plan,
        task_source=current,
        retire_after_finish=cleanup,
    )


class WorkLifecycleTests(unittest.TestCase):
    def test_exact_stage_finish_next_task_and_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            package = _initialize(target, parent, base)
            self.assertEqual(package.state.phase, "accepted")
            self.assertTrue(deployment_status(target, ROOT)["skills"][0]["current"])
            self.assertTrue((target / ".agents/skills/plan-work-package").is_symlink())

            staged = stage(target, "managed-change")
            self.assertEqual(staged.state.phase, "staged")
            bound = bind(target, "managed-change", 43)
            self.assertEqual(bound.state.pull_request, 43)
            (target / "app.txt").write_text("implemented\n", encoding="utf-8")
            complete = finish(target, "managed-change")
            self.assertEqual(complete.state.phase, "complete")
            self.assertEqual(complete.head, complete.remote_head)
            self.assertIn("1/1 passed", report(target, "managed-change"))
            self.assertEqual(complete.completed_items, ("C01",))

            _initialize(
                target,
                parent,
                base,
                task="C02",
                revision=2,
                proof="sentinel",
                cleanup=True,
            )
            stage(target, "managed-change")
            (target / "app.txt").write_text("cleaned\n", encoding="utf-8")
            cleanup = finish(target, "managed-change")
            self.assertTrue(cleanup.state.retire_after_finish)
            final = retire(target, "managed-change")
            self.assertEqual(final, cleanup.head)
            self.assertFalse(target.joinpath(".git/qat/work/managed-change").exists())

            unenroll(target)
            self.assertFalse((target / ".agents").exists())

    def test_interrupted_final_publication_reconciles_with_exact_lease(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            _initialize(target, parent, base)
            provisional = stage(target, "managed-change").head
            bind(target, "managed-change", 43)
            (target / "app.txt").write_text("implemented\n", encoding="utf-8")
            with (
                patch("qa_toolkit.work_git._lease_publish", side_effect=WorkError("offline")),
                self.assertRaisesRegex(WorkError, "offline"),
            ):
                finish(target, "managed-change")
            pending = WorkPackage.load(target, "managed-change").state
            self.assertEqual(pending.phase, "publishing")
            self.assertNotEqual(pending.final_sha, provisional)

            recovered = reconcile(target, "managed-change")
            self.assertEqual(recovered.state.phase, "complete")
            self.assertEqual(recovered.remote_head, pending.final_sha)

    def test_validation_failure_preserves_provisional_and_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            plan, current = _inputs(parent)
            package = initialize(
                target,
                work_id="managed-change",
                repository="owner/repository",
                issue=42,
                pull_request=None,
                remote="origin",
                kind="feature",
                branch="feature/managed-change",
                base_branch="main",
                base_sha=base,
                plan_revision=1,
                task_id="C01",
                task_title="change managed file",
                expected_parent=base,
                final_subject="feat(core): add managed output",
                allowed_paths=("app.txt",),
                validation_argv=(
                    (str(ROOT / "bin/qat-check"), "--target", "."),
                    (
                        str(ROOT / "toolkit/python/bin/python"),
                        str(ROOT / "tests/fixtures/fail_validation.py"),
                    ),
                ),
                quality_proof="check",
                plan_source=plan,
                task_source=current,
            )
            self.assertEqual(package.state.phase, "accepted")
            provisional = stage(target, "managed-change").head
            bind(target, "managed-change", 43)
            (target / "app.txt").write_text("failed\n", encoding="utf-8")
            with self.assertRaisesRegex(WorkError, "provisional commit preserved"):
                finish(target, "managed-change")
            retained = WorkPackage.load(target, "managed-change")
            self.assertEqual(retained.state.phase, "staged")
            self.assertEqual(_git(target, "rev-parse", "HEAD"), provisional)
            self.assertEqual(tuple(item.exit_code for item in retained.result.commands), (0, 1))
            for item in retained.result.commands:
                self.assertTrue((retained.root / item.stdout).is_file())
                self.assertTrue((retained.root / item.stderr).is_file())

    def test_closed_state_release_and_thread_helpers(self) -> None:
        raw = {
            "schema_version": 1,
            "repository": "owner/repository",
            "issue": 1,
            "pull_request": None,
            "remote": "origin",
            "work_id": "sample",
            "kind": "feature",
            "phase": "accepted",
            "branch": "feature/sample",
            "base_branch": "main",
            "base_sha": "a" * 40,
            "plan_revision": 1,
            "current_task": "C01",
            "task_title": "add sample",
            "expected_parent": "a" * 40,
            "final_subject": "feat(core): add sample output",
            "allowed_paths": ["src/"],
            "validation_argv": [["qat", "check"]],
            "quality_proof": "check",
            "retire_after_finish": False,
            "provisional_sha": None,
            "final_sha": None,
        }
        self.assertEqual(WorkState.parse(raw).work_id, "sample")
        with self.assertRaisesRegex(WorkError, "unknown extra"):
            WorkState.parse(raw | {"extra": True})
        self.assertEqual(
            calculate_release("1.2.3", ("feat(core): add output",)).next_version,
            "1.3.0",
        )
        self.assertEqual(
            thread_name("owner/repository", 42, "C01", "Add output"),
            "[repository#42 C01] Add output",
        )


if __name__ == "__main__":
    unittest.main()
