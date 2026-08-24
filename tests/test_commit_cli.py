"""Acceptance tests for self-contained commit validation."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from test_hooks import _target

from qa_toolkit.commit_cli import check_messages
from qa_toolkit.deployment import enroll

ROOT = Path(__file__).parents[1]


class CommitCliTests(unittest.TestCase):
    def test_cocogitto_does_not_require_consumer_or_global_git_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = _target(Path(directory))
            enroll(target, ROOT)
            for name in ("user.name", "user.email"):
                subprocess.run(
                    ["git", "-C", str(target), "config", "--local", "--unset-all", name],
                    check=True,
                    capture_output=True,
                    timeout=30,
                    shell=False,
                )

            code = check_messages(
                target,
                ROOT,
                (("fixture", "test(commits): validate isolated identity\n"),),
            )

            self.assertEqual(code, 0)
            for name in ("user.name", "user.email"):
                observed = subprocess.run(
                    ["git", "-C", str(target), "config", "--local", "--get", name],
                    check=False,
                    capture_output=True,
                    timeout=30,
                    shell=False,
                )
                self.assertEqual(observed.returncode, 1)


if __name__ == "__main__":
    unittest.main()
