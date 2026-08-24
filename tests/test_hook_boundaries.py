"""Boundary tests for repository-scoped hooks and guardrail state."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from test_hooks import ROOT, _payload, _target

from qa_toolkit import (
    codex_hooks,
    guardrail_state,
    guardrails,
    hook_deployment,
    hook_dispatch,
    strict_json,
)
from qa_toolkit.deployment import DeploymentError, enroll
from qa_toolkit.guardrail_state import GuardrailStateError
from qa_toolkit.hook_deployment import HookDeploymentError
from qa_toolkit.models import Hook, Profile


class GuardrailPathTests(unittest.TestCase):
    def test_paths_patterns_programs_and_segments_are_bounded(self) -> None:
        self.assertEqual(guardrails._validated_path("src/file.py").as_posix(), "src/file.py")
        for value in ("", "../file", "/file", "bad\\file", "bad\nfile"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guardrails._validated_path(value)
        target = Path("/repo")
        self.assertEqual(guardrails._repository_path("src/file", target, target), "src/file")
        for value in ("-f", "$FILE", "../outside"):
            self.assertIsNone(guardrails._repository_path(value, target, target))
        self.assertTrue(guardrails._matches("config/value", ("config/**",)))
        self.assertTrue(guardrails._matches("config", ("config/**",)))
        self.assertFalse(guardrails._matches("source", ("config/**",)))
        self.assertEqual(
            guardrails._segments(("one", ";", "two", "&&", "three")),
            (("one",), ("two",), ("three",)),
        )
        self.assertEqual(
            guardrails._program(("A=1", "env", "-i", "B=2", "git", "status")), ("git", ("status",))
        )
        self.assertEqual(guardrails._program(("A=1",)), ("", ()))
        for program, arguments, expected in (
            ("rm", ("file",), True),
            ("sed", ("-i.bak", "file"), True),
            ("git", ("status",), False),
            ("git", ("reset", "--hard"), True),
            ("printf", (">", "file"), True),
            ("printf", ("value",), False),
        ):
            with self.subTest(program=program):
                self.assertEqual(guardrails._mutating(program, arguments), expected)
        for command in ("", "bad\0command"):
            with self.assertRaises(ValueError):
                guardrails._tokens(command)

    def test_apply_patch_extracts_add_move_update_and_rejects_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw).resolve()
            command = (
                "*** Begin Patch\n"
                "*** Add File: one.txt\n"
                "*** Update File: two.txt\n"
                "*** Move to: three.txt\n"
                "*** Delete File: one.txt\n"
                "*** End Patch"
            )
            self.assertEqual(
                guardrails.extract_apply_patch_paths(command, target, target),
                ("one.txt", "two.txt", "three.txt"),
            )
            for invalid in (
                "text",
                "*** Begin Patch\n*** End Patch",
                "*** Begin Patch\n*** Add File: ../bad\n*** End Patch",
            ):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    guardrails.extract_apply_patch_paths(invalid, target, target)
            (target / "linked").symlink_to(target.parent)
            with self.assertRaisesRegex(ValueError, "symlink"):
                guardrails.extract_apply_patch_paths(
                    "*** Begin Patch\n*** Add File: linked/file\n*** End Patch", target, target
                )

    def test_bash_and_patch_evaluation_identify_only_protected_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw).resolve()
            protected = ("protected.txt", ".git/**")
            allowed: tuple[tuple[str, dict[str, object]], ...] = (
                ("Read", {}),
                ("Bash", {"command": "git status"}),
                ("Bash", {"command": "rm ordinary.txt"}),
                (
                    "apply_patch",
                    {"command": "*** Begin Patch\n*** Update File: ordinary.txt\n*** End Patch"},
                ),
            )
            for tool, payload in allowed:
                with self.subTest(tool=tool):
                    self.assertFalse(
                        guardrails.evaluate(
                            tool, payload, cwd=target, target=target, protected=protected
                        ).denied
                    )
            denied: tuple[tuple[str, dict[str, object]], ...] = (
                ("Bash", {}),
                ("Bash", {"command": "rm protected.txt"}),
                ("Bash", {"command": "git reset --hard ."}),
                ("Bash", {"command": "printf value > protected.txt"}),
                (
                    "apply_patch",
                    {"command": "*** Begin Patch\n*** Update File: protected.txt\n*** End Patch"},
                ),
                ("apply_patch", {"command": "bad"}),
            )
            for tool, payload in denied:
                with self.subTest(tool=tool, payload=payload):
                    decision = guardrails.evaluate(
                        tool, payload, cwd=target, target=target, protected=protected
                    )
                    self.assertTrue(decision.denied)
                    self.assertTrue(decision.reason)


class GuardrailStateTests(unittest.TestCase):
    def test_state_files_reject_irregular_invalid_and_oversized_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "state.json"
            self.assertIsNone(guardrail_state._read(path))
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(GuardrailStateError):
                guardrail_state._read(path)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(GuardrailStateError):
                guardrail_state._read(path)
            path.write_text("x" * 65_537, encoding="utf-8")
            with self.assertRaisesRegex(GuardrailStateError, "irregular"):
                guardrail_state._read(path)

    def test_identity_and_proof_paths_fail_closed(self) -> None:
        with (
            patch("qa_toolkit.guardrail_state.git_bytes", side_effect=DeploymentError("bad")),
            self.assertRaisesRegex(GuardrailStateError, "cannot inspect"),
        ):
            guardrail_state._git(Path("."), "status")
        with (
            patch("qa_toolkit.guardrail_state._git", return_value=b"short\n"),
            self.assertRaisesRegex(GuardrailStateError, "exact Git"),
        ):
            guardrail_state.identity(Path("/target"), Path("/root"))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            (target / ".git/qat/evidence").mkdir(parents=True)
            with self.assertRaisesRegex(GuardrailStateError, "repository-local"):
                guardrail_state.record_proof(target, target, target)
            with self.assertRaisesRegex(GuardrailStateError, "must not be empty"):
                guardrail_state.open_breaker(target, target, " \n")

    def test_breaker_and_proof_status_distinguish_absent_stale_and_current(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = _target(Path(raw))
            enroll(target, ROOT)
            self.assertEqual(guardrail_state.breaker_status(target, ROOT)["open"], False)
            self.assertEqual(guardrail_state.proof_status(target, ROOT)["present"], False)
            guardrail_state.open_breaker(target, ROOT, "  observed   failure  ")
            self.assertTrue(guardrail_state.breaker_status(target, ROOT)["current"])
            evidence = target / ".git/qat/evidence/run"
            evidence.mkdir(parents=True)
            (evidence / "summary.json").write_text("{}", encoding="utf-8")
            guardrail_state.record_proof(target, ROOT, evidence)
            self.assertTrue(guardrail_state.proof_status(target, ROOT)["current"])
            self.assertFalse(guardrail_state.breaker_status(target, ROOT)["open"])
            (target / "ordinary.txt").write_text("dirty", encoding="utf-8")
            self.assertFalse(guardrail_state.proof_status(target, ROOT)["current"])


class CodexPayloadTests(unittest.TestCase):
    def test_payload_parser_accepts_all_six_events_and_rejects_malformed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw).resolve()
            for event in codex_hooks.EVENTS:
                extra: dict[str, object] = {}
                if event in {"PreToolUse", "PermissionRequest", "PostToolUse"}:
                    extra = {"tool_name": "Bash", "tool_input": {"command": "true"}}
                if event == "Stop":
                    extra = {"stop_hook_active": False}
                parsed = codex_hooks.parse_payload(_payload(target, event, **extra), event, target)
                self.assertEqual(parsed["hook_event_name"], event)
            invalid = (
                b"",
                b"{",
                b"[]",
                b'{"hook_event_name":"Stop","hook_event_name":"Stop"}',
                _payload(target, "Other"),
                json.dumps({"hook_event_name": "SessionStart", "cwd": "relative"}).encode(),
                _payload(target, "PreToolUse", tool_name="", tool_input={}),
                _payload(target, "PreToolUse", tool_name="Bash", tool_input=[]),
                _payload(target, "Stop", stop_hook_active="no"),
            )
            for content in invalid:
                with self.subTest(content=content), self.assertRaises(codex_hooks.CodexHookError):
                    codex_hooks.parse_payload(content, "Stop", target)

            temporary_escape = str(Path(tempfile.gettempdir()) / ".." / "outside")
            for cwd in ("", temporary_escape, "/outside", "/" + "x" * 4097):
                with self.subTest(cwd=cwd), self.assertRaises(codex_hooks.CodexHookError):
                    codex_hooks.parse_payload(
                        json.dumps({"hook_event_name": "SessionStart", "cwd": cwd}).encode(),
                        "SessionStart",
                        target,
                    )
            with self.assertRaisesRegex(codex_hooks.CodexHookError, "tool_name"):
                codex_hooks.parse_payload(
                    _payload(target, "PreToolUse", tool_name="x" * 257, tool_input={}),
                    "PreToolUse",
                    target,
                )

    def test_guardrail_events_and_fast_check_have_bounded_responses(self) -> None:
        target = Path("/target")
        root = Path("/root")
        with patch("qa_toolkit.codex_hooks.proof_status", return_value={"current": False}):
            response = codex_hooks.handle_guardrail(
                {"hook_event_name": "SessionStart"}, target, root
            )
        self.assertIn("not current", str(response))
        self.assertIsNone(
            codex_hooks.handle_guardrail({"hook_event_name": "SessionEnd"}, target, root)
        )
        with (
            patch(
                "qa_toolkit.codex_hooks.evaluate", return_value=guardrails.GuardrailDecision(False)
            ),
            patch("qa_toolkit.codex_hooks._protected", return_value=()),
        ):
            self.assertIsNone(
                codex_hooks.handle_guardrail(
                    {
                        "hook_event_name": "PermissionRequest",
                        "tool_name": "Bash",
                        "tool_input": {},
                        "cwd": target,
                    },
                    target,
                    root,
                )
            )
        with (
            patch(
                "qa_toolkit.codex_hooks.evaluate",
                return_value=guardrails.GuardrailDecision(True, "denied"),
            ),
            patch("qa_toolkit.codex_hooks._protected", return_value=()),
        ):
            response = codex_hooks.handle_guardrail(
                {
                    "hook_event_name": "PermissionRequest",
                    "tool_name": "Bash",
                    "tool_input": {},
                    "cwd": target,
                },
                target,
                root,
            )
        self.assertIn("deny", str(response))
        with (
            patch("qa_toolkit.codex_hooks._changed_paths", return_value=()),
            patch("qa_toolkit.codex_hooks._protected", return_value=()),
        ):
            self.assertIsNone(
                codex_hooks.handle_guardrail({"hook_event_name": "PostToolUse"}, target, root)
            )
        with (
            patch("qa_toolkit.codex_hooks.breaker_status", return_value={"open": False}),
            patch("qa_toolkit.codex_hooks.proof_status", return_value={"current": False}),
        ):
            response = codex_hooks.handle_guardrail(
                {"hook_event_name": "Stop", "stop_hook_active": True}, target, root
            )
            self.assertIsNotNone(response)
            assert response is not None
            self.assertIn("systemMessage", response)
        with self.assertRaises(codex_hooks.CodexHookError):
            codex_hooks.handle_guardrail({"hook_event_name": "Other"}, target, root)

        with (
            patch("qa_toolkit.codex_hooks._changed_paths", return_value=(".qat.toml",)),
            patch("qa_toolkit.codex_hooks._protected", return_value=(".qat.toml",)),
            patch("qa_toolkit.codex_hooks.open_breaker") as open_state,
        ):
            response = codex_hooks.handle_guardrail(
                {"hook_event_name": "PostToolUse"}, target, root
            )
        self.assertIn("opened", str(response))
        open_state.assert_called_once()
        with (
            patch(
                "qa_toolkit.codex_hooks.breaker_status",
                return_value={"open": True, "reason": "failed"},
            ),
            patch("qa_toolkit.codex_hooks.proof_status", return_value={"current": False}),
        ):
            response = codex_hooks.handle_guardrail(
                {"hook_event_name": "Stop", "stop_hook_active": False}, target, root
            )
            self.assertIsNotNone(response)
            assert response is not None
            self.assertIn("decision", response)
        with (
            patch("qa_toolkit.codex_hooks.breaker_status", return_value={"open": False}),
            patch("qa_toolkit.codex_hooks.proof_status", return_value={"current": True}),
        ):
            self.assertIsNone(
                codex_hooks.handle_guardrail(
                    {"hook_event_name": "Stop", "stop_hook_active": False}, target, root
                )
            )

        with patch("qa_toolkit.codex_hooks.guarded_execute", return_value=(0, None)):
            self.assertIsNone(codex_hooks.handle_fast_check(target, root))
        with (
            patch("qa_toolkit.codex_hooks.guarded_execute", return_value=(1, Path("evidence"))),
            patch("qa_toolkit.codex_hooks.open_breaker") as open_state,
        ):
            self.assertIn("evidence", str(codex_hooks.handle_fast_check(target, root)))
        open_state.assert_called_once()

        with (
            patch("qa_toolkit.codex_hooks.guarded_execute", return_value=(2, None)),
            patch("qa_toolkit.codex_hooks.open_breaker") as open_state,
        ):
            self.assertNotIn("evidence", str(codex_hooks.handle_fast_check(target, root)))
        open_state.assert_called_once()

    def test_changed_path_failures_and_command_responses_are_fail_closed(self) -> None:
        with (
            patch("qa_toolkit.codex_hooks.git_bytes", side_effect=DeploymentError("cannot read")),
            self.assertRaisesRegex(codex_hooks.CodexHookError, "observed mutations"),
        ):
            codex_hooks._changed_paths(Path("/target"))

        target = Path("/target")
        root = Path("/root")
        payload = _payload(target, "SessionEnd")
        environment = {"QAT_EVENT": "SessionEnd", "QAT_TARGET": str(target), "QAT_ROOT": str(root)}
        fake_stdin = type("Input", (), {"buffer": io.BytesIO(payload)})()
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("qa_toolkit.codex_hooks.sys.stdin", fake_stdin),
            patch("qa_toolkit.codex_hooks.handle_guardrail", return_value={"value": 1}),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            codex_hooks.main(["guardrail"])
        self.assertEqual(json.loads(output.getvalue()), {"value": 1})

        error_cases = (
            ("PreToolUse", "permissionDecision"),
            ("PermissionRequest", "behavior"),
            ("Stop", "decision"),
        )
        for event, marker in error_cases:
            extra: dict[str, object] = {}
            if event in {"PreToolUse", "PermissionRequest"}:
                extra = {"tool_name": "Bash", "tool_input": {"command": "true"}}
            if event == "Stop":
                extra = {"stop_hook_active": False}
            fake_stdin = type(
                "Input", (), {"buffer": io.BytesIO(_payload(target, event, **extra))}
            )()
            with (
                self.subTest(event=event),
                patch.dict(
                    os.environ,
                    {"QAT_EVENT": event, "QAT_TARGET": str(target), "QAT_ROOT": str(root)},
                    clear=True,
                ),
                patch("qa_toolkit.codex_hooks.sys.stdin", fake_stdin),
                patch(
                    "qa_toolkit.codex_hooks.handle_guardrail",
                    side_effect=codex_hooks.CodexHookError("failure"),
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                codex_hooks.main(["guardrail"])
            self.assertIn(marker, output.getvalue())

        with (
            patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as exited,
        ):
            codex_hooks.main(["fast-check"])
        self.assertEqual(exited.exception.code, 2)


class StrictJsonTests(unittest.TestCase):
    def test_typed_json_boundaries_and_strict_decoder(self) -> None:
        self.assertEqual(strict_json.require_json_object({"key": 1}, "value"), {"key": 1})
        self.assertEqual(strict_json.require_json_array([1], "value"), [1])
        self.assertEqual(strict_json.require_json_string("text", "value"), "text")
        self.assertTrue(strict_json.require_json_boolean(True, "value"))
        invalid: tuple[Callable[[], object], ...] = (
            lambda: strict_json.require_json_object([], "value"),
            lambda: strict_json.require_json_object({1: "value"}, "value"),
            lambda: strict_json.require_json_array({}, "value"),
            lambda: strict_json.require_json_string("", "value"),
            lambda: strict_json.require_json_boolean(1, "value"),
            lambda: strict_json.strict_json_loads('{"key": 1, "key": 2}'),
            lambda: strict_json.strict_json_loads("NaN"),
        )
        for operation in invalid:
            with self.subTest(operation=operation), self.assertRaises((RuntimeError, ValueError)):
                operation()


class HookDispatchTests(unittest.TestCase):
    def test_invocation_context_and_records_are_strict(self) -> None:
        target = Path(tempfile.gettempdir()) / "target"
        self.assertEqual(
            hook_dispatch.invocation_context(None, target, "git", "pre-commit"),
            (target.resolve(), "git", "pre-commit"),
        )
        for values in (
            (None, target, None, "event"),
            (None, None, None, None),
            ("bad", None, None, None),
        ):
            with self.subTest(values=values), self.assertRaises(HookDeploymentError):
                hook_dispatch.invocation_context(*values)
        self.assertEqual(
            hook_dispatch.invocation_context("/repo/.git/hooks/pre-commit", None, None, None)[1:],
            ("git", "pre-commit"),
        )
        self.assertEqual(
            hook_dispatch.invocation_context("/repo/.codex/hooks/Stop", None, None, None)[1:],
            ("codex", "Stop"),
        )
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            for document in (
                "not json",
                "{}",
                json.dumps({"target_root": str(target), "toolkit_root": "relative", "hooks": {}}),
            ):
                path = target / ".git/qat/deployment.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(document, encoding="utf-8")
                with self.subTest(document=document), self.assertRaises(HookDeploymentError):
                    hook_dispatch._record(target)

    def test_response_merging_preserves_decisions_context_and_messages(self) -> None:
        self.assertIsNone(hook_dispatch._merge_responses("Stop", []))
        decisive: dict[str, object] = {"decision": "block"}
        self.assertEqual(hook_dispatch._merge_responses("Stop", [{}, decisive]), decisive)
        contexts: list[dict[str, object]] = [
            {"hookSpecificOutput": {"additionalContext": "one"}},
            {"hookSpecificOutput": {"additionalContext": "two"}},
        ]
        merged = hook_dispatch._merge_responses("SessionStart", contexts)
        self.assertIsNotNone(merged)
        assert merged is not None
        specific = merged["hookSpecificOutput"]
        self.assertIsInstance(specific, dict)
        assert isinstance(specific, dict)
        self.assertEqual(specific["additionalContext"], "one\ntwo")
        self.assertEqual(
            hook_dispatch._merge_responses(
                "Stop", [{"systemMessage": "one"}, {"systemMessage": "two"}]
            ),
            {"systemMessage": "one\ntwo"},
        )
        self.assertEqual(hook_dispatch._merge_responses("Stop", [{"value": 1}]), {"value": 1})
        self.assertIsNone(hook_dispatch._merge_responses("Stop", [{"one": 1}, {"two": 2}]))
        self.assertTrue(
            hook_dispatch._decisive({"hookSpecificOutput": {"permissionDecision": "deny"}})
        )
        self.assertTrue(hook_dispatch._decisive({"hookSpecificOutput": {"decision": {}}}))

    def test_dispatch_classifies_git_and_codex_entry_results(self) -> None:
        target = Path("/target")
        root = Path("/root")
        record = {"dispatchers": [{"kind": "git", "event": "pre-commit"}]}
        entry = Path("/entry")
        with (
            patch("qa_toolkit.hook_dispatch._record", return_value=(root, record)),
            patch("qa_toolkit.hook_dispatch._selected_entries", return_value=(entry,)),
            patch(
                "qa_toolkit.hook_dispatch.subprocess.run",
                return_value=subprocess.CompletedProcess([], 7),
            ),
        ):
            self.assertEqual(hook_dispatch.dispatch(target, "git", "pre-commit", ()), 7)
        with (
            patch("qa_toolkit.hook_dispatch._record", return_value=(root, record)),
            self.assertRaisesRegex(HookDeploymentError, "not selected"),
        ):
            hook_dispatch.dispatch(target, "git", "pre-push", ())

        record = {"dispatchers": [{"kind": "codex", "event": "Stop"}]}
        results = (
            (subprocess.CompletedProcess([], 4, b"", b"error"), 4, None),
            (subprocess.CompletedProcess([], 0, b"not json", b""), None, "invalid JSON"),
            (subprocess.CompletedProcess([], 0, b"[]", b""), None, "non-object"),
            (subprocess.CompletedProcess([], 0, b'{"decision":"block"}', b""), 0, None),
        )
        for completed, expected, message in results:
            with (
                self.subTest(message=message),
                patch("qa_toolkit.hook_dispatch._record", return_value=(root, record)),
                patch("qa_toolkit.hook_dispatch._selected_entries", return_value=(entry,)),
                patch("qa_toolkit.hook_dispatch.subprocess.run", return_value=completed),
            ):
                if message:
                    with self.assertRaisesRegex(HookDeploymentError, message):
                        hook_dispatch.dispatch(target, "codex", "Stop", (), codex_input=b"{}")
                else:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(
                            hook_dispatch.dispatch(target, "codex", "Stop", (), codex_input=b"{}"),
                            expected,
                        )
        with (
            patch("qa_toolkit.hook_dispatch._record", return_value=(root, record)),
            patch("qa_toolkit.hook_dispatch._selected_entries", return_value=()),
            self.assertRaisesRegex(HookDeploymentError, "one MiB"),
        ):
            hook_dispatch.dispatch(
                target, "codex", "Stop", (), codex_input=b"x" * (hook_dispatch.MAX_CODEX_INPUT + 1)
            )


class HookDeploymentBoundaryTests(unittest.TestCase):
    def test_definition_snapshot_restore_and_missing_dispatcher(self) -> None:
        definition = json.loads(hook_deployment._definition(set(hook_deployment.CODEX_EVENTS)))
        self.assertEqual(tuple(definition["hooks"]), hook_deployment.CODEX_EVENTS)
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "repo"
            root = Path(raw) / "root"
            target.mkdir()
            root.mkdir()
            foreign = target / ".git/hooks/pre-commit"
            foreign.parent.mkdir(parents=True)
            foreign.symlink_to("foreign")
            snapshot = hook_deployment._snapshot_foreign(
                target, foreign, target / ".git/qat/backups"
            )
            foreign.unlink()
            hook_deployment._restore_foreign(target, snapshot)
            self.assertEqual(os.readlink(foreign), "foreign")
            profile = Profile(
                "fixture",
                (),
                (),
                (),
                (Hook("git", "pre-commit", Path("hook"), True),),
                (),
                root / "profile.toml",
            )
            with self.assertRaisesRegex(HookDeploymentError, "unavailable"):
                hook_deployment._expected_dispatchers(target, root, profile)

    def test_toggle_refuses_missing_malformed_and_modified_entries(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            item = {
                "kind": "git",
                "event": "pre-commit",
                "name": "quality",
                "enabled": "hooks/git/pre-commit/enabled/quality",
                "enabled_target": "../available/quality",
            }
            record = {"entries": [item]}
            with self.assertRaisesRegex(HookDeploymentError, "no selected"):
                hook_deployment.set_enabled(target, record, True, event="other")
            path = target / ".git/qat" / str(item["enabled"])
            path.parent.mkdir(parents=True)
            path.write_text("bad", encoding="utf-8")
            with self.assertRaisesRegex(HookDeploymentError, "malformed"):
                hook_deployment.set_enabled(target, record, True)
            path.unlink()
            path.symlink_to("wrong")
            with self.assertRaisesRegex(HookDeploymentError, "modified"):
                hook_deployment.set_enabled(target, record, False)

    def test_foreign_snapshot_and_previous_validation_reject_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            target.mkdir()
            directory = target / ".git/hooks/pre-commit"
            directory.mkdir(parents=True)
            with self.assertRaisesRegex(HookDeploymentError, "non-regular foreign"):
                hook_deployment._snapshot_foreign(
                    target,
                    directory,
                    target / ".git/qat/backups",
                )
            previous: dict[str, object] = {
                "dispatchers": [{"path": ".git/hooks/commit-msg", "target": "dispatcher"}]
            }
            with self.assertRaisesRegex(HookDeploymentError, "modified owned hook"):
                hook_deployment._validate_previous(target, previous, False)
            hook_deployment._validate_previous(target, previous, True)

            definition = target / ".codex/hooks.json"
            definition.parent.mkdir(parents=True)
            definition.write_text("changed", encoding="utf-8")
            previous = {
                "definition": {
                    "path": ".codex/hooks.json",
                    "digest": "0" * 64,
                }
            }
            with self.assertRaisesRegex(HookDeploymentError, "modified owned hook"):
                hook_deployment._validate_previous(target, previous, False)

    def test_definition_subset_enabled_state_and_malformed_status(self) -> None:
        definition = json.loads(hook_deployment._definition({"Stop"}))
        self.assertEqual(tuple(definition["hooks"]), ("Stop",))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            target.mkdir()
            source = root / "library/git-hooks/pre-commit/quality"
            source.parent.mkdir(parents=True)
            source.write_text("#!/bin/sh\n", encoding="utf-8")
            source.chmod(0o755)
            item = {
                "kind": "git",
                "event": "pre-commit",
                "name": "quality",
                "source": "library/git-hooks/pre-commit/quality",
                "source_digest": hook_deployment._digest(source),
                "available": "hooks/git/pre-commit/available/quality",
                "available_target": "source",
                "enabled": "hooks/git/pre-commit/enabled/quality",
                "enabled_target": "../available/quality",
            }
            enabled = target / ".git/qat" / item["enabled"]
            enabled.parent.mkdir(parents=True)
            enabled.symlink_to(item["enabled_target"])
            self.assertIn(
                ("git", "pre-commit", "quality"),
                hook_deployment._enabled_before(target, {"entries": [item]}),
            )
            available = target / ".git/qat" / item["available"]
            available.parent.mkdir(parents=True)
            available.symlink_to("source")
            enabled.unlink()
            enabled.write_text("malformed", encoding="utf-8")
            report = hook_deployment.hook_status(
                target,
                root,
                {"dispatchers": [], "entries": [item]},
            )
            self.assertFalse(report["current"])
            self.assertFalse(report["entries"][0]["current"])

    def test_reconcile_removes_obsolete_hooks_and_restores_adopted_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            root = Path(raw) / "root"
            target.mkdir()
            root.mkdir()
            dispatcher = target / ".git/hooks/pre-commit"
            dispatcher.parent.mkdir(parents=True)
            dispatcher.symlink_to("managed")
            definition = target / ".codex/hooks.json"
            definition.parent.mkdir(parents=True)
            definition.write_text("managed", encoding="utf-8")
            backup = target / ".git/qat/hook-backups/file"
            backup.parent.mkdir(parents=True)
            backup.write_text("foreign", encoding="utf-8")
            previous = {
                "dispatchers": [
                    {
                        "path": ".git/hooks/pre-commit",
                        "target": "managed",
                    }
                ],
                "definition": {
                    "path": ".codex/hooks.json",
                    "digest": hook_deployment._digest(definition),
                },
                "entries": [],
                "adopted": [
                    {
                        "path": ".git/hooks/pre-commit",
                        "kind": "file",
                        "backup": "hook-backups/file",
                        "mode": 0o755,
                    }
                ],
            }
            profile = Profile("none", (), (), (), (), (), root / "profile.toml")
            record = hook_deployment.reconcile_hooks(target, root, profile, previous=previous)
            self.assertEqual(dispatcher.read_text(encoding="utf-8"), "foreign")
            self.assertFalse(definition.exists())
            self.assertEqual(record["dispatchers"], [])

    def test_remove_hooks_backup_copies_files_links_and_skips_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            backup = Path(raw) / "backup"
            target.mkdir()
            link = target / ".git/hooks/pre-commit"
            link.parent.mkdir(parents=True)
            link.symlink_to("dispatcher")
            definition = target / ".codex/hooks.json"
            definition.parent.mkdir(parents=True)
            definition.write_text("definition", encoding="utf-8")
            record = {
                "dispatchers": [
                    {"path": ".git/hooks/pre-commit", "target": "dispatcher"},
                    {"path": ".git/hooks/missing", "target": "dispatcher"},
                ],
                "definition": {
                    "path": ".codex/hooks.json",
                    "digest": hook_deployment._digest(definition),
                },
                "adopted": [],
            }
            hook_deployment.remove_hooks(
                target,
                record,
                backup=backup,
                hard_reset=False,
            )
            self.assertEqual(os.readlink(backup / ".git/hooks/pre-commit"), "dispatcher")
            self.assertEqual(
                (backup / ".codex/hooks.json").read_text(encoding="utf-8"),
                "definition",
            )


if __name__ == "__main__":
    unittest.main()
