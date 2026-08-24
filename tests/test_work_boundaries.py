"""Boundary and recovery tests for structured work-package state."""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from test_work import _fixture, _git, _initialize

from qa_toolkit import work, work_git
from qa_toolkit.work import ValidationRecord, WorkError, WorkPackage, WorkResult, WorkState


def _state() -> dict[str, object]:
    return {
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


class WorkStateBoundaryTests(unittest.TestCase):
    def test_validation_and_result_records_are_closed(self) -> None:
        record = ValidationRecord.parse(
            {"argv": ["true"], "exit_code": 0, "stdout": "out", "stderr": "err"}
        )
        self.assertEqual(record.as_dict()["argv"], ["true"])
        result = WorkResult.parse(
            {
                "schema_version": 1,
                "work_id": "sample",
                "task_id": "C01",
                "commands": [record.as_dict()],
                "changed_paths": [],
                "evidence_references": ["evidence/run"],
            }
        )
        self.assertEqual(result.as_dict()["task_id"], "C01")
        invalid = (
            {"argv": ["true"], "exit_code": -1, "stdout": "out", "stderr": "err"},
            {"argv": ["true"], "exit_code": 0, "stdout": "../out", "stderr": "err"},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkError):
                ValidationRecord.parse(value)
        with self.assertRaisesRegex(WorkError, "commands must be an array"):
            WorkResult.parse(
                {
                    "schema_version": 1,
                    "work_id": "sample",
                    "task_id": "C01",
                    "commands": {},
                    "changed_paths": [],
                    "evidence_references": [],
                }
            )

    def test_state_phase_and_identity_invariants_fail_closed(self) -> None:
        raw = _state()
        self.assertEqual(WorkState.parse(raw).as_dict(), raw)
        mutations: tuple[tuple[str, object], ...] = (
            ("schema_version", 2),
            ("repository", "repository"),
            ("issue", 0),
            ("pull_request", 0),
            ("remote", "bad remote"),
            ("work_id", "Bad"),
            ("kind", "other"),
            ("phase", "other"),
            ("branch", ""),
            ("base_sha", "short"),
            ("plan_revision", True),
            ("current_task", "task"),
            ("task_title", ""),
            ("final_subject", "update"),
            ("allowed_paths", []),
            ("validation_argv", []),
            ("quality_proof", "other"),
            ("retire_after_finish", "no"),
            ("provisional_sha", "short"),
        )
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(WorkError):
                WorkState.parse(raw | {key: value})
        phase_cases = (
            {"phase": "staged", "provisional_sha": None},
            {
                "phase": "publishing",
                "provisional_sha": "b" * 40,
                "final_sha": None,
                "pull_request": 1,
            },
            {"phase": "executing", "provisional_sha": "b" * 40, "pull_request": None},
            {"retire_after_finish": True, "quality_proof": "check", "phase": "cleanup"},
        )
        for changes in phase_cases:
            with self.subTest(changes=changes), self.assertRaises(WorkError):
                WorkState.parse(raw | changes)

    def test_closed_helpers_reject_malformed_values(self) -> None:
        self.assertEqual(work._optional_positive(None, "value"), None)
        self.assertEqual(work._optional_sha(None, "sha"), None)
        invalid = (
            lambda: work._object([], "object"),
            lambda: work._exact({}, {"field"}, "object"),
            lambda: work._schema(True, "object"),
            lambda: work._choice("bad", "kind", frozenset({"good"})),
            lambda: work._positive(False, "number"),
            lambda: work._text("", "text", 10),
            lambda: work._boolean(1, "flag"),
            lambda: work._strings([""], "strings"),
            lambda: work._paths(["../file"]),
            lambda: work._commands([["true", ""]]),
            lambda: work._quality_command((("qat", "check"),), "sentinel"),
        )
        for operation in invalid:
            with self.subTest(operation=operation), self.assertRaises(WorkError):
                operation()


class WorkFileBoundaryTests(unittest.TestCase):
    def test_markdown_json_and_artifact_paths_reject_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            empty = root / "empty.md"
            empty.write_text(" \n", encoding="utf-8")
            with self.assertRaisesRegex(WorkError, "empty"):
                work.read_markdown(empty, "plan")
            invalid = root / "invalid.md"
            invalid.write_bytes(b"\xff")
            with self.assertRaises(WorkError):
                work.read_markdown(invalid, "plan")
            link = root / "link.md"
            link.symlink_to(empty)
            with self.assertRaisesRegex(WorkError, "symlinked"):
                work.read_markdown(link, "plan")
            directory = root / "package"
            directory.mkdir()
            with self.assertRaisesRegex(WorkError, "unexpected"):
                work._artifact_directory(directory)
            outside = root.parent / "outside"
            with self.assertRaisesRegex(WorkError, "escapes"):
                work._no_symlink_components(root, outside)

    def test_package_write_refuses_replaced_state_files(self) -> None:
        state = WorkState.parse(_state())
        result = WorkResult("sample", "C01", (), (), ())
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "package"
            work.write_package(root, "plan", "task", state, result)
            self.assertEqual(work.immutable_changes(state, state), ())
            linked = root / "state.json"
            linked.unlink()
            linked.symlink_to(root / "PLAN.md")
            with self.assertRaisesRegex(WorkError, "symlinked work state"):
                work.write_state(root, state)
            linked.unlink()
            linked.write_text("{}", encoding="utf-8")
            result_path = root / "result.json"
            result_path.unlink()
            result_path.symlink_to(root / "PLAN.md")
            with self.assertRaisesRegex(WorkError, "symlinked work result"):
                work.write_result(root, result)


class WorkGitHelperTests(unittest.TestCase):
    def test_release_and_validation_parsers_cover_every_increment(self) -> None:
        cases = (
            ("0.1.0", ("fix(core): repair",), "0.1.1", "patch"),
            ("0.1.0", ("feat(core)!: replace API",), "0.2.0", "minor"),
            ("1.2.3", ("feat(core): add API",), "1.3.0", "minor"),
            ("1.2.3", ("fix(core): repair\n\nBREAKING CHANGE: new API",), "2.0.0", "major"),
        )
        for base, messages, expected, bump in cases:
            result = work_git.calculate_release(base, messages)
            self.assertEqual((result.next_version, result.bump), (expected, bump))
            self.assertEqual(result.as_dict()["schema_version"], 1)
        self.assertEqual(work_git.parse_validation(('["qat", "check"]',)), (("qat", "check"),))
        invalid_releases = (("latest", ("fix(core): repair",)), ("1.2.3", ()), ("1.2.3", ("",)))
        for base, invalid_messages in invalid_releases:
            with self.assertRaises(WorkError):
                work_git.calculate_release(base, invalid_messages)
        for value in ("{", '"qat check"', '["qat", 1]'):
            with self.assertRaises(WorkError):
                work_git.parse_validation((value,))

    def test_git_process_identity_and_remote_parsers_fail_closed(self) -> None:
        target = Path("/target")
        with (
            patch("qa_toolkit.work_git.subprocess.run", side_effect=OSError("unavailable")),
            self.assertRaisesRegex(WorkError, "unavailable"),
        ):
            work_git._git(target, ("status",))
        for completed, message in (
            (
                subprocess.CompletedProcess((), 0, b"x" * (work_git._MAX_GIT_OUTPUT + 1), b""),
                "excessive",
            ),
            (subprocess.CompletedProcess((), 2, b"", b"bad revision"), "bad revision"),
        ):
            with (
                patch("qa_toolkit.work_git.subprocess.run", return_value=completed),
                self.assertRaisesRegex(WorkError, message),
            ):
                work_git._git(target, ("status",))
        with (
            patch(
                "qa_toolkit.work_git._git",
                return_value=subprocess.CompletedProcess((), 0, b"\xff", b""),
            ),
            self.assertRaisesRegex(WorkError, "non-UTF-8"),
        ):
            work_git._git_text(target, ("status",))
        with (
            patch("qa_toolkit.work_git._git_text", return_value="invalid"),
            self.assertRaisesRegex(WorkError, "invalid HEAD"),
        ):
            work_git._head(target)
        with (
            patch("qa_toolkit.work_git._git_text", return_value=""),
            self.assertRaisesRegex(WorkError, "attached branch"),
        ):
            work_git._branch(target)
        with (
            patch("qa_toolkit.work_git._git", return_value=subprocess.CompletedProcess((), 2)),
            self.assertRaisesRegex(WorkError, "cannot inspect local"),
        ):
            work_git._local_branch(target, "branch")
        ref = "refs/heads/branch"
        for output in (
            f"{'a' * 40}\t{ref}\n{'b' * 40}\t{ref}\n",
            f"{'a' * 40}\trefs/heads/other\n",
            f"{'g' * 40}\t{ref}\n",
        ):
            with (
                patch("qa_toolkit.work_git._git_text", return_value=output),
                self.assertRaises(WorkError),
            ):
                work_git._remote_head(target, "origin", "branch")
        with patch("qa_toolkit.work_git._git_text", return_value=""):
            self.assertIsNone(work_git._remote_head(target, "origin", "branch"))

    def test_worktree_paths_allowances_and_validation_results_are_closed(self) -> None:
        for raw in (b"\xff", b"/absolute", b"../parent"):
            with self.subTest(raw=raw), self.assertRaises(WorkError):
                work_git._git_path(raw)
        malformed = subprocess.CompletedProcess((), 0, b"??\0", b"")
        with (
            patch("qa_toolkit.work_git._git", return_value=malformed),
            self.assertRaisesRegex(WorkError, "malformed"),
        ):
            work_git._changes(Path("/target"))
        rename = subprocess.CompletedProcess((), 0, b"R  destination\0", b"")
        with (
            patch("qa_toolkit.work_git._git", return_value=rename),
            self.assertRaisesRegex(WorkError, "incomplete rename"),
        ):
            work_git._changes(Path("/target"))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "src").mkdir()
            with self.assertRaisesRegex(WorkError, "outside"):
                work_git._validate_paths(target, ("other",), ("src/",))
            link = target / "src/link"
            link.symlink_to(target)
            with self.assertRaisesRegex(WorkError, "symlink"):
                work_git._validate_paths(target, ("src/link/file",), ("src/",))

    def test_validation_execution_retains_output_errors_and_evidence(self) -> None:
        state = WorkState.parse(_state())
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            package = WorkPackage(
                target / "work", "plan", "task", state, WorkResult("sample", "C01", (), (), ())
            )
            evidence = target / ".git/qat/evidence/run"
            evidence.mkdir(parents=True)
            (evidence / "summary.json").write_text("{}", encoding="utf-8")
            calls = (
                subprocess.CompletedProcess((), 0, b"output", b""),
                subprocess.CompletedProcess((), 1, b"", b"finding"),
            )
            with (
                patch("qa_toolkit.work_git._evidence_runs", side_effect=(set(), {evidence})),
                patch("qa_toolkit.work_git.subprocess.run", side_effect=calls),
            ):
                records, references = work_git._validations(target, package, (("one",), ("two",)))
            self.assertEqual(tuple(item.exit_code for item in records), (0, 1))
            self.assertEqual(references, ("evidence/run",))
            with (
                patch("qa_toolkit.work_git._evidence_runs", return_value=set()),
                patch("qa_toolkit.work_git.subprocess.run", side_effect=OSError("missing")),
            ):
                records, _references = work_git._validations(target, package, (("missing",),))
            self.assertEqual(records[0].exit_code, 2)

    def test_status_rename_index_evidence_and_output_limits(self) -> None:
        state = WorkState.parse(_state())
        status = work_git.WorkStatus(
            Path("/target"),
            "a" * 40,
            "feature/sample",
            None,
            ("C01",),
            state,
        )
        self.assertEqual(status.as_dict()["completed_items"], ["C01"])
        rename = subprocess.CompletedProcess((), 0, b"R  new.txt\0old.txt\0", b"")
        with patch("qa_toolkit.work_git._git", return_value=rename):
            self.assertEqual(work_git._changes(Path("/target")), ("new.txt", "old.txt"))
        indexed = subprocess.CompletedProcess((), 0, b"two\0one\0", b"")
        with patch("qa_toolkit.work_git._git", return_value=indexed):
            self.assertEqual(work_git._index_changes(Path("/target")), ("one", "two"))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self.assertEqual(work_git._evidence_runs(target), set())
            root = target / ".git/qat/evidence"
            (root / "valid").mkdir(parents=True)
            (root / "valid/summary.json").write_text("{}", encoding="utf-8")
            (root / "ignored").mkdir()
            self.assertEqual(work_git._evidence_runs(target), {root / "valid"})

            package = WorkPackage(
                target / "work",
                "plan",
                "task",
                state,
                WorkResult("sample", "C01", (), (), ()),
            )
            completed = subprocess.CompletedProcess(
                (),
                0,
                b"x" * (work_git._MAX_VALIDATION_OUTPUT + 1),
                b"",
            )
            with (
                patch("qa_toolkit.work_git._evidence_runs", return_value=set()),
                patch("qa_toolkit.work_git.subprocess.run", return_value=completed),
                self.assertRaisesRegex(WorkError, "excessive output"),
            ):
                work_git._validations(target, package, (("command",),))

    def test_provisional_publication_and_completed_trailers_are_exact(self) -> None:
        state = WorkState.parse(_state())
        with self.assertRaisesRegex(WorkError, "exact provisional"):
            work_git._require_provisional(Path("/target"), state)
        with self.assertRaisesRegex(WorkError, "observed provisional"):
            work_git._lease_publish(Path("/target"), state, None)
        with patch("qa_toolkit.work_git._git") as git:
            work_git._publish_provisional(Path("/target"), state, None)
            work_git._publish_provisional(Path("/target"), state, "a" * 40)
        self.assertEqual(git.call_count, 2)
        with (
            patch(
                "qa_toolkit.work_git._git_text",
                side_effect=(
                    "revision\n",
                    "subject\n\nWork-Package: owner/repository#1\nWork-Item: bad\n",
                ),
            ),
            self.assertRaisesRegex(WorkError, "malformed work trailers"),
        ):
            work_git._completed_items(Path("/target"), state)


class WorkLifecycleBoundaryTests(unittest.TestCase):
    def _package(self, phase: str) -> WorkPackage:
        changes: dict[str, object] = {"phase": phase}
        if phase in {"staged", "executing", "publishing", "complete"}:
            changes["provisional_sha"] = "b" * 40
        if phase in {"executing", "publishing", "complete"}:
            changes["pull_request"] = 1
        if phase in {"publishing", "complete"}:
            changes["final_sha"] = "c" * 40
        state = WorkState.parse(_state() | changes)
        return WorkPackage(
            Path("/work"),
            "plan",
            "task",
            state,
            WorkResult("sample", "C01", (), (), ()),
        )

    def test_stage_bind_finish_and_retire_preconditions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            package = _initialize(target, parent, base)
            with (
                patch("qa_toolkit.work_git._head", return_value="b" * 40),
                self.assertRaisesRegex(WorkError, "expected parent"),
            ):
                work_git.stage(target, "managed-change")
            work_git.stage(target, "managed-change")
            with self.assertRaisesRegex(WorkError, "cannot stage"):
                work_git.stage(target, "managed-change")
            work_git.bind(target, "managed-change", 43)
            with self.assertRaisesRegex(WorkError, "identity mismatch"):
                work_git.bind(target, "managed-change", 44)
            with self.assertRaisesRegex(WorkError, "no implementation"):
                work_git.finish(target, "managed-change")
            with self.assertRaisesRegex(WorkError, "completed cleanup"):
                work_git.retire(target, "managed-change")
            wrong = replace(
                package.state, phase="executing", provisional_sha="b" * 40, pull_request=1
            )
            with (
                patch(
                    "qa_toolkit.work_git.WorkPackage.load",
                    return_value=replace(package, state=wrong),
                ),
                patch("qa_toolkit.work_git.enrolled_target", return_value=target),
                self.assertRaisesRegex(WorkError, "cannot reconcile"),
            ):
                work_git.reconcile(target, "managed-change")

    def test_initialization_branch_binding_and_index_preconditions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            (target / "app.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(WorkError, "clean worktree"):
                _initialize(target, parent, base)
            (target / "app.txt").write_text("base\n", encoding="utf-8")
            _initialize(target, parent, base)
            with self.assertRaisesRegex(WorkError, "active task"):
                _initialize(target, parent, base)
            with self.assertRaisesRegex(WorkError, "requires a staged task"):
                work_git.bind(target, "managed-change", 43)
            _git(target, "branch", "refactor/managed-change")
            with self.assertRaisesRegex(WorkError, "already exists locally"):
                work_git.stage(target, "managed-change")

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            _initialize(target, parent, base)
            work_git.stage(target, "managed-change")
            work_git.bind(target, "managed-change", 43)
            (target / "app.txt").write_text("implemented\n", encoding="utf-8")
            _git(target, "add", "app.txt")
            with self.assertRaisesRegex(WorkError, "empty index"):
                work_git.finish(target, "managed-change")

    def test_validation_mutation_restores_staged_phase(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            target, _remote, base = _fixture(parent)
            _initialize(target, parent, base)
            work_git.stage(target, "managed-change")
            work_git.bind(target, "managed-change", 43)
            (target / "app.txt").write_text("implementation\n", encoding="utf-8")

            def mutate(
                _target: Path,
                _package: WorkPackage,
                _commands: object,
            ) -> tuple[tuple[ValidationRecord, ...], tuple[str, ...]]:
                (target / "app.txt").write_text("validation mutation\n", encoding="utf-8")
                return (ValidationRecord(("true",), 0, "out", "err"),), ()

            with (
                patch("qa_toolkit.work_git._validations", side_effect=mutate),
                self.assertRaisesRegex(WorkError, "validation modified"),
            ):
                work_git.finish(target, "managed-change")
            self.assertEqual(WorkPackage.load(target, "managed-change").state.phase, "staged")

    def test_stage_bind_and_reconcile_remote_divergence_is_explicit(self) -> None:
        accepted = self._package("accepted")
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=Path("/target")),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=accepted),
            patch("qa_toolkit.work_git._head", return_value="a" * 40),
            patch("qa_toolkit.work_git._changes", return_value=()),
            patch("qa_toolkit.work_git._branch", return_value="feature/sample"),
            patch("qa_toolkit.work_git._remote_head", return_value="d" * 40),
            self.assertRaisesRegex(WorkError, "remote workflow branch moved"),
        ):
            work_git.stage(Path("/target"), "sample")

        staged = self._package("staged")
        bound_staged = replace(staged, state=replace(staged.state, pull_request=1))
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=Path("/target")),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=bound_staged),
            patch("qa_toolkit.work_git._require_provisional"),
            patch("qa_toolkit.work_git._remote_head", return_value="d" * 40),
            self.assertRaisesRegex(WorkError, "remote branch is not the exact provisional"),
        ):
            work_git.bind(Path("/target"), "sample", 1)
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=Path("/target")),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=bound_staged),
            self.assertRaisesRegex(WorkError, "pull-request identity mismatch"),
        ):
            work_git.reconcile(Path("/target"), "sample", pull_request=2)

    def test_reconcile_recovers_final_local_commit_and_rejects_each_divergence(self) -> None:
        staged = self._package("staged")
        staged = replace(staged, state=replace(staged.state, pull_request=1))
        target = Path("/target")
        common = (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=staged),
            patch("qa_toolkit.work_git.write_state"),
        )
        with contextlib.ExitStack() as stack:
            for manager in common:
                stack.enter_context(manager)
            stack.enter_context(patch("qa_toolkit.work_git._head", return_value="c" * 40))
            stack.enter_context(patch("qa_toolkit.work_git._remote_head", return_value="b" * 40))
            stack.enter_context(patch("qa_toolkit.work_git._commit_subject", return_value="wrong"))
            stack.enter_context(patch("qa_toolkit.work_git._parents", return_value=("a" * 40,)))
            with self.assertRaisesRegex(WorkError, "local branch diverged"):
                work_git.reconcile(target, "sample")

        with contextlib.ExitStack() as stack:
            for manager in common:
                stack.enter_context(manager)
            stack.enter_context(patch("qa_toolkit.work_git._head", return_value="c" * 40))
            stack.enter_context(patch("qa_toolkit.work_git._remote_head", return_value="b" * 40))
            stack.enter_context(
                patch(
                    "qa_toolkit.work_git._commit_subject",
                    return_value=staged.state.final_subject,
                )
            )
            stack.enter_context(patch("qa_toolkit.work_git._parents", return_value=("a" * 40,)))
            lease = stack.enter_context(patch("qa_toolkit.work_git._lease_publish"))
            stack.enter_context(patch("qa_toolkit.work_git.status", return_value="recovered"))
            self.assertEqual(work_git.reconcile(target, "sample"), "recovered")
            lease.assert_called_once()

        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=staged),
            patch("qa_toolkit.work_git._head", return_value="b" * 40),
            patch("qa_toolkit.work_git._remote_head", return_value="d" * 40),
            patch("qa_toolkit.work_git._require_provisional"),
            self.assertRaisesRegex(WorkError, "remote branch diverged from the provisional"),
        ):
            work_git.reconcile(target, "sample")

        publishing = self._package("publishing")
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=publishing),
            patch("qa_toolkit.work_git._head", return_value="c" * 40),
            patch("qa_toolkit.work_git._remote_head", return_value="d" * 40),
            patch(
                "qa_toolkit.work_git._commit_subject",
                return_value=publishing.state.final_subject,
            ),
            self.assertRaisesRegex(WorkError, "diverged during final publication"),
        ):
            work_git.reconcile(target, "sample")

        complete = self._package("complete")
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=complete),
            patch("qa_toolkit.work_git._head", return_value="d" * 40),
            patch("qa_toolkit.work_git._remote_head", return_value="c" * 40),
            self.assertRaisesRegex(WorkError, "completed work does not match"),
        ):
            work_git.reconcile(target, "sample")

    def test_finish_restores_index_after_amend_failure(self) -> None:
        staged = self._package("staged")
        staged = replace(staged, state=replace(staged.state, pull_request=1))
        success = ValidationRecord(("true",), 0, "out", "err")
        git_result = subprocess.CompletedProcess((), 0, b"", b"")
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=Path("/target")),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=staged),
            patch("qa_toolkit.work_git._require_provisional"),
            patch("qa_toolkit.work_git._remote_head", return_value="b" * 40),
            patch("qa_toolkit.work_git._index_changes", return_value=()),
            patch("qa_toolkit.work_git._changes", return_value=("src/file.py",)),
            patch("qa_toolkit.work_git._validate_paths"),
            patch("qa_toolkit.work_git._worktree_fingerprint", return_value="same"),
            patch("qa_toolkit.work_git._validations", return_value=((success,), ())),
            patch("qa_toolkit.work_git.write_state"),
            patch("qa_toolkit.work_git.write_result"),
            patch(
                "qa_toolkit.work_git._git",
                side_effect=(git_result, WorkError("amend failed"), git_result),
            ) as git,
            self.assertRaisesRegex(WorkError, "amend failed"),
        ):
            work_git.finish(Path("/target"), "sample")
        self.assertEqual(git.call_args_list[-1].args[1][:2], ("restore", "--staged"))

    def test_retirement_requires_sentinel_exact_state_and_unsubstituted_root(self) -> None:
        target = Path("/target")
        complete = self._package("complete")
        cleanup = replace(
            complete,
            state=replace(complete.state, retire_after_finish=True, quality_proof="sentinel"),
        )
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=cleanup),
            patch("qa_toolkit.work_git._changes", return_value=("dirty",)),
            self.assertRaisesRegex(WorkError, "Sentinel proof"),
        ):
            work_git.retire(target, "sample")
        with (
            patch("qa_toolkit.work_git.enrolled_target", return_value=target),
            patch("qa_toolkit.work_git.WorkPackage.load", return_value=cleanup),
            patch("qa_toolkit.work_git._changes", return_value=()),
            patch("qa_toolkit.work_git._head", return_value="d" * 40),
            patch("qa_toolkit.work_git._remote_head", return_value="c" * 40),
            self.assertRaisesRegex(WorkError, "exact published final state"),
        ):
            work_git.retire(target, "sample")


if __name__ == "__main__":
    unittest.main()
