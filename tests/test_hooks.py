"""Acceptance tests for repository-scoped Git and Codex hooks."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.codex_hooks import handle_guardrail, parse_payload
from qa_toolkit.commit_policy import is_lifecycle_message, structural_findings
from qa_toolkit.deployment import enroll, status, unenroll
from qa_toolkit.guardrail_state import breaker_status, proof_status
from qa_toolkit.hook_deployment import HookDeploymentError, set_enabled
from qa_toolkit.hook_dispatch import dispatch
from qa_toolkit.runner import execute

ROOT = Path(__file__).parents[1]


def _git(target: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(target), "-c", "core.hooksPath=/dev/null", *arguments],
        check=True,
        capture_output=True,
        timeout=30,
        shell=False,
    )


def _target(parent: Path) -> Path:
    target = parent / "consumer"
    target.mkdir()
    (target / ".qat.toml").write_text(
        """schema_version = 1
profile = "disposable-hooks"
native_configurations = []
protected_paths = ["protected.txt"]

[vocabulary]
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
""",
        encoding="utf-8",
    )
    (target / "protected.txt").write_text("protected\n", encoding="utf-8")
    (target / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    _git(parent, "init", "-b", "main", str(target))
    _git(target, "config", "user.name", "QA Toolkit")
    _git(target, "config", "user.email", "qat@example.invalid")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "test(repo): create disposable hook target")
    return target


def _payload(target: Path, event: str, **extra: object) -> bytes:
    return json.dumps({"hook_event_name": event, "cwd": str(target), **extra}).encode()


class HookDeploymentTests(unittest.TestCase):
    def test_enroll_toggle_dispatch_and_unenroll_restore_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = _target(Path(raw))
            before_status = _git(target, "status", "--porcelain=v1", "-z").stdout
            central_mode = stat.S_IMODE(
                (ROOT / "library/codex-hooks/PreToolUse/guardrail").stat().st_mode
            )
            record = enroll(target, ROOT)
            self.assertTrue((target / ".git/hooks/pre-commit").is_symlink())
            self.assertTrue((target / ".git/hooks/commit-msg").is_symlink())
            self.assertEqual(
                (target / ".git/hooks/pre-commit").readlink(),
                Path("../qat/git-hook-dispatcher"),
            )
            self.assertTrue((target / ".git/qat/git-hook-dispatcher").is_file())
            self.assertTrue((target / ".codex/hooks/PreToolUse").is_symlink())
            definition = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(
                tuple(definition["hooks"]),
                (
                    "SessionStart",
                    "PreToolUse",
                    "PermissionRequest",
                    "PostToolUse",
                    "Stop",
                    "SessionEnd",
                ),
            )
            self.assertTrue(status(target, ROOT)["hooks"]["current"])

            protected = _payload(
                target,
                "PreToolUse",
                tool_name="apply_patch",
                tool_input={
                    "command": (
                        "*** Begin Patch\n"
                        "*** Update File: protected.txt\n"
                        "@@\n-old\n+new\n"
                        "*** End Patch"
                    )
                },
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    dispatch(target, "codex", "PreToolUse", (), codex_input=protected), 0
                )
            self.assertEqual(
                json.loads(output.getvalue())["hookSpecificOutput"]["permissionDecision"],
                "deny",
            )

            changed = set_enabled(
                target,
                record["hooks"],
                False,
                kind="codex",
                event="PreToolUse",
            )
            self.assertEqual(changed, ("codex:PreToolUse:guardrail",))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    dispatch(target, "codex", "PreToolUse", (), codex_input=protected), 0
                )
            self.assertEqual(output.getvalue(), "")
            set_enabled(target, record["hooks"], True, kind="codex", event="PreToolUse")
            self.assertEqual(
                stat.S_IMODE((ROOT / "library/codex-hooks/PreToolUse/guardrail").stat().st_mode),
                central_mode,
            )

            unenroll(target)
            self.assertFalse((target / ".codex/hooks.json").exists())
            self.assertFalse((target / ".codex").exists())
            self.assertFalse((target / ".git/hooks/pre-commit").exists())
            self.assertEqual(_git(target, "status", "--porcelain=v1", "-z").stdout, before_status)

    def test_foreign_git_hook_requires_adoption_and_is_restored_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = _target(Path(raw))
            foreign = target / ".git/hooks/pre-commit"
            foreign.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            foreign.chmod(0o751)
            exclude = (target / ".git/info/exclude").read_bytes()
            with self.assertRaisesRegex(HookDeploymentError, "foreign hook"):
                enroll(target, ROOT)
            self.assertEqual(foreign.read_bytes(), b"#!/bin/sh\nexit 7\n")
            self.assertEqual(stat.S_IMODE(foreign.stat().st_mode), 0o751)
            self.assertEqual((target / ".git/info/exclude").read_bytes(), exclude)
            self.assertFalse((target / ".git/qat").exists())

            enroll(target, ROOT, adopt_hooks=True)
            self.assertTrue(foreign.is_symlink())
            unenroll(target)
            self.assertEqual(foreign.read_bytes(), b"#!/bin/sh\nexit 7\n")
            self.assertEqual(stat.S_IMODE(foreign.stat().st_mode), 0o751)


class HookBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = _target(Path(self.temporary.name))
        self.record = enroll(self.target, ROOT)

    def test_commit_hook_and_lifecycle_messages_use_one_managed_check(self) -> None:
        self.assertFalse(structural_findings("feat(hooks): add repository dispatcher\n"))
        self.assertTrue(structural_findings("update\n"))
        self.assertTrue(is_lifecycle_message("Merge pull request #7 from example/topic\n"))
        message = self.target / ".git/COMMIT_EDITMSG"
        message.write_text("feat(hooks): add repository dispatcher\n", encoding="utf-8")
        environment = os.environ.copy()
        environment["QAT_HOOK_TEST_ACCEPT_DIRTY_TOOLKIT"] = "1"
        accepted = subprocess.run(
            [str(self.target / ".git/hooks/commit-msg"), str(message)],
            cwd=self.target,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        message.write_text("update\n", encoding="utf-8")
        rejected = subprocess.run(
            [str(self.target / ".git/hooks/commit-msg"), str(message)],
            cwd=self.target,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn(b"QCM001", rejected.stderr)

    def test_toolkit_drift_and_runtime_errors_do_not_block_commits(self) -> None:
        message = self.target / ".git/COMMIT_EDITMSG"
        message.write_text("update\n", encoding="utf-8")
        revision = self.target / ".git/qat/git-hook-toolkit-revision"
        revision.write_text(f"{'0' * 40}\n", encoding="ascii")

        stale = subprocess.run(
            [str(self.target / ".git/hooks/commit-msg"), str(message)],
            cwd=self.target,
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )

        self.assertEqual(stale.returncode, 0, stale.stderr)
        self.assertIn(b"allowing Git operation", stale.stderr)
        dirty_root = Path(self.temporary.name) / "dirty-toolkit"
        dirty_root.mkdir()
        _git(dirty_root, "init", "-b", "main")
        _git(dirty_root, "config", "user.name", "QA Toolkit")
        _git(dirty_root, "config", "user.email", "qat@example.invalid")
        (dirty_root / "tracked").write_text("accepted\n", encoding="utf-8")
        _git(dirty_root, "add", "tracked")
        _git(dirty_root, "commit", "-m", "test(repo): create dirty toolkit fixture")
        dirty_revision = _git(dirty_root, "rev-parse", "HEAD").stdout.decode().strip()
        (self.target / ".git/qat/git-hook-toolkit-root").write_text(
            f"{dirty_root}\n", encoding="utf-8"
        )
        revision.write_text(f"{dirty_revision}\n", encoding="ascii")
        (dirty_root / "untracked").write_text("changed\n", encoding="utf-8")
        dirty = subprocess.run(
            [str(self.target / ".git/hooks/commit-msg"), str(message)],
            cwd=self.target,
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(dirty.returncode, 0, dirty.stderr)
        self.assertIn(b"allowing Git operation", dirty.stderr)
        (self.target / ".git/qat/git-hook-toolkit-root").write_text(f"{ROOT}\n", encoding="utf-8")
        revision.write_text(f"{self.record['toolkit_revision']}\n", encoding="ascii")
        environment = os.environ.copy()
        environment["QAT_HOOK_TEST_ACCEPT_DIRTY_TOOLKIT"] = "1"
        environment["QAT_PYTHON"] = "/bin/false"
        failed_runtime = subprocess.run(
            [str(self.target / ".git/hooks/commit-msg"), str(message)],
            cwd=self.target,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
            shell=False,
        )
        self.assertEqual(failed_runtime.returncode, 0, failed_runtime.stderr)
        self.assertIn(b"allowing Git operation", failed_runtime.stderr)

    def test_protected_mutation_opens_breaker_and_sentinel_replaces_it_with_proof(self) -> None:
        pre = parse_payload(
            _payload(
                self.target,
                "PreToolUse",
                tool_name="Bash",
                tool_input={"command": "rm protected.txt"},
            ),
            "PreToolUse",
            self.target,
        )
        self.assertEqual(
            handle_guardrail(pre, self.target, ROOT)["hookSpecificOutput"]["permissionDecision"],  # type: ignore[index]
            "deny",
        )
        allowed = parse_payload(
            _payload(
                self.target,
                "PreToolUse",
                tool_name="Bash",
                tool_input={"command": "sed -n 1p protected.txt"},
            ),
            "PreToolUse",
            self.target,
        )
        self.assertIsNone(handle_guardrail(allowed, self.target, ROOT))

        (self.target / "protected.txt").write_text("changed\n", encoding="utf-8")
        post = parse_payload(
            _payload(
                self.target,
                "PostToolUse",
                tool_name="apply_patch",
                tool_input={"command": "*** Begin Patch\n*** End Patch"},
            ),
            "PostToolUse",
            self.target,
        )
        self.assertIsNotNone(handle_guardrail(post, self.target, ROOT))
        self.assertTrue(breaker_status(self.target, ROOT)["open"])
        stop = parse_payload(
            _payload(self.target, "Stop", stop_hook_active=False),
            "Stop",
            self.target,
        )
        self.assertEqual(handle_guardrail(stop, self.target, ROOT)["decision"], "block")  # type: ignore[index]

        code, evidence = execute(self.target, "sentinel", root=ROOT)
        self.assertEqual(code, 0, evidence)
        self.assertFalse(breaker_status(self.target, ROOT)["open"])
        self.assertTrue(proof_status(self.target, ROOT)["current"])
        self.assertIsNone(handle_guardrail(stop, self.target, ROOT))


if __name__ == "__main__":
    unittest.main()
