from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_toolkit.github import (
    GitHubCheck,
    GitHubClient,
    GitHubIssue,
    GitHubPullRequest,
)


def _completed(
    stdout: str = "", *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess((), returncode, stdout, stderr)


def _repository() -> str:
    return json.dumps({"nameWithOwner": "owner/repository"})


def _issue(number: int = 42, *, title: str = "Managed work") -> str:
    return json.dumps(
        {
            "number": number,
            "state": "OPEN",
            "title": title,
            "url": f"https://github.com/owner/repository/issues/{number}",
        }
    )


def _pull_request(
    number: int = 43,
    *,
    draft: bool = True,
    closing: tuple[int, ...] = (),
) -> str:
    return json.dumps(
        {
            "number": number,
            "state": "OPEN",
            "isDraft": draft,
            "headRefName": "feature/cables",
            "baseRefName": "main",
            "title": "Managed work",
            "url": f"https://github.com/owner/repository/pull/{number}",
            "closingIssuesReferences": [{"number": item} for item in closing],
        }
    )


class GitHubClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GitHubClient(Path("/usr/bin/gh"), {"PATH": "/bin"})

    def test_discovery_keeps_only_required_auth_environment_and_disables_prompts(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PATH": "/bin",
                    "GH_TOKEN": "token",
                    "GITHUB_TOKEN": "fallback",
                    "UNRELATED_SECRET": "drop",
                },
                clear=True,
            ),
            patch("qa_toolkit.github.payload_root", return_value=Path("/central")),
            patch("qa_toolkit.github.Path.is_file", return_value=True),
            patch("qa_toolkit.github.os.access", return_value=True),
        ):
            client = GitHubClient.discover()
        self.assertEqual(client.executable, Path("/central/gh/bin/gh"))
        self.assertEqual(client.environment["GH_TOKEN"], "token")
        self.assertEqual(client.environment["GH_PROMPT_DISABLED"], "1")
        self.assertNotIn("UNRELATED_SECRET", client.environment)

    def test_issue_view_requires_auth_and_exact_repository_identity(self) -> None:
        responses = (_completed(), _completed(_repository()), _completed(_issue()))
        with patch("qa_toolkit.github.subprocess.run", side_effect=responses) as run:
            issue = self.client.issue("owner/repository", 42)
        self.assertEqual(
            issue,
            GitHubIssue(
                "owner/repository",
                42,
                "OPEN",
                "Managed work",
                "https://github.com/owner/repository/issues/42",
            ),
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list[:2]],
            [
                ("/usr/bin/gh", "auth", "status", "--hostname", "github.com"),
                (
                    "/usr/bin/gh",
                    "repo",
                    "view",
                    "owner/repository",
                    "--json",
                    "nameWithOwner",
                ),
            ],
        )
        for call in run.call_args_list:
            self.assertFalse(call.kwargs["shell"])
            self.assertEqual(call.kwargs["env"], {"PATH": "/bin"})

    def test_issue_creation_rejects_duplicates_and_verifies_created_url(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            body = Path(raw) / "body.md"
            body.write_text("# Managed work\n", encoding="utf-8")
            duplicate = (_completed(), _completed(_repository()), _completed(f"[{_issue()}]"))
            with (
                patch("qa_toolkit.github.subprocess.run", side_effect=duplicate),
                self.assertRaisesRegex(RuntimeError, "duplicate"),
            ):
                self.client.create_issue("owner/repository", title="Managed work", body_file=body)

            created = (
                _completed(),
                _completed(_repository()),
                _completed("[]"),
                _completed("https://github.com/owner/repository/issues/42\n"),
                _completed(_issue()),
            )
            with patch("qa_toolkit.github.subprocess.run", side_effect=created) as run:
                issue = self.client.create_issue(
                    "owner/repository", title="Managed work", body_file=body
                )
            self.assertEqual(issue.number, 42)
            self.assertIn("--body-file", run.call_args_list[3].args[0])

            outside = Path(raw) / "outside.md"
            outside.write_text("keep\n", encoding="utf-8")
            link = Path(raw) / "link.md"
            link.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "non-symlink"):
                self.client.create_issue("owner/repository", title="Managed work", body_file=link)

    def test_draft_pull_request_creation_rejects_duplicate_heads(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            body = Path(raw) / "body.md"
            body.write_text("References #42 without closing it.\n", encoding="utf-8")
            duplicate = (
                _completed(),
                _completed(_repository()),
                _completed(f"[{_pull_request()}]"),
            )
            with (
                patch("qa_toolkit.github.subprocess.run", side_effect=duplicate),
                self.assertRaisesRegex(RuntimeError, "duplicate"),
            ):
                self.client.create_pull_request(
                    "owner/repository",
                    head="feature/cables",
                    base="main",
                    title="Managed work",
                    body_file=body,
                )

            created = (
                _completed(),
                _completed(_repository()),
                _completed("[]"),
                _completed("https://github.com/owner/repository/pull/43\n"),
                _completed(_pull_request()),
            )
            with patch("qa_toolkit.github.subprocess.run", side_effect=created) as run:
                pull_request = self.client.create_pull_request(
                    "owner/repository",
                    head="feature/cables",
                    base="main",
                    title="Managed work",
                    body_file=body,
                )
            self.assertEqual(
                pull_request,
                GitHubPullRequest(
                    "owner/repository",
                    43,
                    "OPEN",
                    True,
                    "feature/cables",
                    "main",
                    "Managed work",
                    "https://github.com/owner/repository/pull/43",
                    (),
                ),
            )
            self.assertIn("--draft", run.call_args_list[3].args[0])

    def test_checks_comments_and_ready_state_are_strict_and_never_merge(self) -> None:
        checks = json.dumps(
            [
                {
                    "name": "test",
                    "state": "SUCCESS",
                    "bucket": "pass",
                    "workflow": "CI",
                    "link": "https://github.com/owner/repository/actions/runs/1",
                }
            ]
        )
        check_responses = (
            _completed(),
            _completed(_repository()),
            _completed(_pull_request()),
            _completed(checks, returncode=8),
        )
        with patch("qa_toolkit.github.subprocess.run", side_effect=check_responses) as run:
            result = self.client.checks("owner/repository", 43)
        self.assertEqual(
            result,
            (
                GitHubCheck(
                    "test",
                    "SUCCESS",
                    "pass",
                    "CI",
                    "https://github.com/owner/repository/actions/runs/1",
                ),
            ),
        )
        self.assertEqual(run.call_args_list[-1].args[0][1:3], ("pr", "checks"))

        ready_responses = (
            _completed(),
            _completed(_repository()),
            _completed(_pull_request()),
            _completed("ready\n"),
            _completed(_pull_request(draft=False)),
        )
        with patch("qa_toolkit.github.subprocess.run", side_effect=ready_responses) as run:
            ready = self.client.ready("owner/repository", 43)
        self.assertFalse(ready.draft)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command[1:3] == ("pr", "ready") for command in commands))
        self.assertFalse(any("merge" in command for command in commands))

        with tempfile.TemporaryDirectory() as raw:
            body = Path(raw) / "report.md"
            body.write_text("Validation passed.\n", encoding="utf-8")
            comment_responses = (
                _completed(),
                _completed(_repository()),
                _completed(_pull_request()),
                _completed("https://github.com/owner/repository/pull/43#issuecomment-1\n"),
                _completed(_pull_request()),
            )
            with patch("qa_toolkit.github.subprocess.run", side_effect=comment_responses) as run:
                reported = self.client.comment("owner/repository", 43, body_file=body)
        self.assertEqual(reported.number, 43)
        self.assertEqual(run.call_args_list[3].args[0][1:3], ("pr", "comment"))

    def test_issue_and_pull_request_updates_preserve_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            body = Path(raw) / "body.md"
            body.write_text("Updated contract.\n", encoding="utf-8")
            issue_responses = (
                _completed(),
                _completed(_repository()),
                _completed(_issue(title="Old title")),
                _completed("https://github.com/owner/repository/issues/42\n"),
                _completed(_issue(title="Managed work")),
            )
            with patch("qa_toolkit.github.subprocess.run", side_effect=issue_responses) as run:
                issue = self.client.update_issue(
                    "owner/repository",
                    42,
                    title="Managed work",
                    body_file=body,
                )
            self.assertEqual(issue.title, "Managed work")
            self.assertEqual(run.call_args_list[3].args[0][1:3], ("issue", "edit"))

            pull_responses = (
                _completed(),
                _completed(_repository()),
                _completed(_pull_request()),
                _completed("https://github.com/owner/repository/pull/43\n"),
                _completed(_pull_request(closing=(42,))),
            )
            with patch("qa_toolkit.github.subprocess.run", side_effect=pull_responses) as run:
                pull_request = self.client.update_pull_request(
                    "owner/repository",
                    43,
                    title="Managed work",
                    body_file=body,
                )
            self.assertEqual(pull_request.closing_issues, (42,))
            self.assertEqual(run.call_args_list[3].args[0][1:3], ("pr", "edit"))

    def test_identity_json_auth_and_output_failures_are_closed(self) -> None:
        for repository in ("", "owner", "owner/repo/extra", "../repo"):
            with self.subTest(repository=repository), self.assertRaises(RuntimeError):
                self.client.repository(repository)
        with (
            patch(
                "qa_toolkit.github.subprocess.run",
                return_value=_completed(returncode=1, stderr="not authenticated"),
            ),
            self.assertRaisesRegex(RuntimeError, "not authenticated"),
        ):
            self.client.repository("owner/repository")
        malformed = (_completed(), _completed('{"nameWithOwner":"a","nameWithOwner":"b"}'))
        with (
            patch("qa_toolkit.github.subprocess.run", side_effect=malformed),
            self.assertRaisesRegex(RuntimeError, "duplicate JSON key"),
        ):
            self.client.repository("owner/repository")
        mismatched = (_completed(), _completed(json.dumps({"nameWithOwner": "other/repo"})))
        with (
            patch("qa_toolkit.github.subprocess.run", side_effect=mismatched),
            self.assertRaisesRegex(RuntimeError, "identity mismatch"),
        ):
            self.client.repository("owner/repository")


if __name__ == "__main__":
    unittest.main()
