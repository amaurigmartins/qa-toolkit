"""Handle six repository-local Codex events without transcript or global state."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.config import load_consumer
from qa_toolkit.deployment import DeploymentError, git_bytes
from qa_toolkit.guardrail_state import (
    GuardrailStateError,
    breaker_status,
    open_breaker,
    proof_status,
)
from qa_toolkit.guardrails import evaluate
from qa_toolkit.runner import guarded_execute

EVENTS = frozenset(
    {"SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop", "SessionEnd"}
)
MAX_INPUT = 1_048_576
_AUTOMATIC_PROTECTED = (
    ".qat.toml",
    ".qat/**",
    ".git/**",
    ".codex/hooks.json",
    ".codex/hooks/**",
    ".agents/skills/**",
)


class CodexHookError(RuntimeError):
    """Report malformed repository-local Codex hook input."""


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in values:
        if key in result:
            raise CodexHookError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_payload(content: bytes, expected_event: str, target: Path) -> dict[str, object]:
    """Parse bounded JSON and retain only documented fields used by local checks."""
    if not content or len(content) > MAX_INPUT:
        raise CodexHookError("hook input must be a non-empty JSON object below one MiB")
    try:
        value = json.loads(content, object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CodexHookError("hook input is not valid JSON") from error
    if not isinstance(value, dict):
        raise CodexHookError("hook input must be a JSON object")
    event = value.get("hook_event_name")
    if event != expected_event or event not in EVENTS:
        raise CodexHookError("hook event does not match the installed dispatcher")
    cwd_value = value.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value or len(cwd_value) > 4096:
        raise CodexHookError("hook cwd must be a bounded absolute path")
    cwd = Path(cwd_value)
    if not cwd.is_absolute() or ".." in cwd.parts or os.path.normpath(cwd_value) != cwd_value:
        raise CodexHookError("hook cwd must be a normalized absolute path")
    resolved_cwd = cwd.resolve()
    try:
        resolved_cwd.relative_to(target)
    except ValueError as error:
        raise CodexHookError("hook cwd is outside the enrolled repository") from error
    result: dict[str, object] = {"hook_event_name": event, "cwd": resolved_cwd}
    if event in {"PreToolUse", "PermissionRequest", "PostToolUse"}:
        tool_name = value.get("tool_name")
        tool_input = value.get("tool_input")
        if not isinstance(tool_name, str) or not tool_name or len(tool_name) > 256:
            raise CodexHookError("hook tool_name must be a bounded string")
        if not isinstance(tool_input, dict) or any(not isinstance(key, str) for key in tool_input):
            raise CodexHookError("hook tool_input must be a JSON object")
        result.update({"tool_name": tool_name, "tool_input": tool_input})
    if event == "Stop":
        active = value.get("stop_hook_active")
        if not isinstance(active, bool):
            raise CodexHookError("Stop requires a boolean stop_hook_active")
        result["stop_hook_active"] = active
    return result


def _protected(target: Path) -> tuple[str, ...]:
    consumer = load_consumer(target)
    return tuple(
        dict.fromkeys(
            (*_AUTOMATIC_PROTECTED, *(path.as_posix() for path in consumer.protected_paths))
        )
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        path == pattern.rstrip("/")
        or fnmatch.fnmatchcase(path, pattern)
        or (pattern.endswith("/**") and (path == pattern[:-3] or path.startswith(pattern[:-2])))
        for pattern in patterns
    )


def _changed_paths(target: Path) -> tuple[str, ...]:
    commands = (
        ["git", "-C", str(target), "diff", "--name-only", "-z", "HEAD", "--"],
        ["git", "-C", str(target), "ls-files", "--others", "--exclude-standard", "-z"],
    )
    values: list[str] = []
    for argv in commands:
        try:
            output = git_bytes(target, *argv[3:])
        except DeploymentError as error:
            raise CodexHookError(f"cannot inspect observed mutations: {error}") from error
        values.extend(item.decode("utf-8") for item in output.split(b"\0") if item)
    return tuple(sorted(set(values)))


def _pre_denial(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason[:1000],
        }
    }


def _permission_denial(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": reason[:1000]},
        }
    }


def _context(event: str, message: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": " ".join(message.split())[:1500],
        }
    }


def _stop(active: bool, reason: str) -> dict[str, object]:
    message = " ".join(reason.split())[:2000]
    return {"systemMessage": message} if active else {"decision": "block", "reason": message}


def handle_guardrail(
    payload: dict[str, object], target: Path, root: Path
) -> dict[str, object] | None:
    """Evaluate one event using only the enrolled repository and current state."""
    event = str(payload["hook_event_name"])
    if event == "SessionStart":
        proof = proof_status(target, root)
        state = "current" if proof["current"] else "not current"
        return _context(
            event,
            f"qa-toolkit is enrolled for this repository; Sentinel proof is {state}. "
            "Review this exact repository hook definition through /hooks.",
        )
    if event == "SessionEnd":
        return None
    if event in {"PreToolUse", "PermissionRequest"}:
        decision = evaluate(
            str(payload["tool_name"]),
            payload["tool_input"],  # type: ignore[arg-type]
            cwd=payload["cwd"],  # type: ignore[arg-type]
            target=target,
            protected=_protected(target),
        )
        if not decision.denied:
            return None
        reason = decision.reason or "protected repository mutation"
        return _pre_denial(reason) if event == "PreToolUse" else _permission_denial(reason)
    if event == "PostToolUse":
        changed = tuple(
            path for path in _changed_paths(target) if _matches(path, _protected(target))
        )
        if not changed:
            return None
        reason = "observed protected-path changes: " + ", ".join(changed)
        open_breaker(target, root, reason)
        return _context(event, f"qa-toolkit opened the local breaker: {reason}")
    if event == "Stop":
        active = bool(payload["stop_hook_active"])
        breaker = breaker_status(target, root)
        if breaker["open"]:
            return _stop(
                active, f"qa-toolkit breaker is open: {breaker.get('reason', 'unknown failure')}"
            )
        proof = proof_status(target, root)
        if proof["current"]:
            return None
        return _stop(active, "qa-toolkit requires a current successful `qat sentinel` proof")
    raise CodexHookError("unsupported event")


def handle_fast_check(target: Path, root: Path) -> dict[str, object] | None:
    """Optionally run the fast plan after a mutation and open the local breaker on failure."""
    code, evidence = guarded_execute(target, "check", root=root)
    if code == 0:
        return None
    reason = f"post-mutation fast check exited {code}"
    if evidence is not None:
        reason += f"; evidence: {evidence}"
    open_breaker(target, root, reason)
    return _context("PostToolUse", reason)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-codex-hook")
    parser.add_argument("role", choices=("guardrail", "fast-check"))
    return parser


def main(arguments: Sequence[str] | None = None) -> None:
    """Read one bounded event and emit at most one compact JSON response."""
    options = _parser().parse_args(arguments)
    event = os.environ.get("QAT_EVENT", "")
    target = Path(os.environ.get("QAT_TARGET", ""))
    root = Path(os.environ.get("QAT_ROOT", ""))
    try:
        if event not in EVENTS or not target.is_absolute() or not root.is_absolute():
            raise CodexHookError("dispatcher environment is incomplete")
        content = sys.stdin.buffer.read(MAX_INPUT + 1)
        payload = parse_payload(content, event, target)
        response = (
            handle_guardrail(payload, target, root)
            if options.role == "guardrail"
            else handle_fast_check(target, root)
        )
        if response is not None:
            print(json.dumps(response, separators=(",", ":")))
    except (CodexHookError, GuardrailStateError, OSError, ValueError) as error:
        detail = (" ".join(str(error).split()) or error.__class__.__name__)[:800]
        if event == "PreToolUse":
            print(
                json.dumps(_pre_denial(f"qa-toolkit hook failure: {detail}"), separators=(",", ":"))
            )
            return
        if event == "PermissionRequest":
            print(
                json.dumps(
                    _permission_denial(f"qa-toolkit hook failure: {detail}"),
                    separators=(",", ":"),
                )
            )
            return
        if event == "Stop":
            print(
                json.dumps(
                    _stop(False, f"qa-toolkit hook failure: {detail}"), separators=(",", ":")
                )
            )
            return
        print(f"qat-codex-hook: {detail}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
