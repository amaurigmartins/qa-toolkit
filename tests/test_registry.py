"""Tests for the tracked tool registry and atomic standalone installation."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from qa_toolkit.registry import (
    RegistryError,
    fetch_tool,
    load_registry,
    select_tools,
    tool_status,
    update_standalone,
)


def _record(url: str, checksum: str) -> dict[str, object]:
    return {
        "id": "sample",
        "provider": "fixture",
        "version": "1.2.3",
        "source": "https://example.invalid/sample",
        "environment": "standalone",
        "checksum": {"algorithm": "sha256", "value": checksum},
        "asset": {
            "kind": "raw",
            "url": url,
            "archive": "raw",
            "executables": ["sample"],
        },
        "version_argv": ["{executable}", "--version"],
        "version_contains": "1.2.3",
    }


def _write_registry(root: Path, record: dict[str, object]) -> None:
    registry = root / "registry"
    registry.mkdir(exist_ok=True)
    document = {"schema_version": 1, "host": "linux-x86_64", "tools": [record]}
    (registry / "tools.json").write_text(json.dumps(document), encoding="utf-8")


class TrackedRegistryTests(unittest.TestCase):
    def test_seeded_registry_contains_every_accepted_environment(self) -> None:
        tools = load_registry()
        identifiers = {tool.tool_id for tool in tools}
        self.assertGreaterEqual(len(tools), 35)
        self.assertTrue(
            {
                "uv",
                "gitleaks",
                "cocogitto",
                "cspell",
                "python",
                "ruff",
                "julia-1.10.11",
                "julia-1.12.6",
                "juliaformatter",
            }.issubset(identifiers)
        )

    def test_registry_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "sample"
            executable.write_text("#!/bin/sh\necho 1.2.3\n", encoding="utf-8")
            checksum = hashlib.sha256(executable.read_bytes()).hexdigest()
            record = _record(executable.as_uri(), checksum)
            record["mystery"] = True
            _write_registry(root, record)
            with self.assertRaisesRegex(RegistryError, "unknown fields"):
                load_registry(root)

    def test_verified_raw_install_reports_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-sample"
            source.write_text("#!/bin/sh\necho sample 1.2.3\n", encoding="utf-8")
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            _write_registry(root, _record(source.as_uri(), checksum))
            tool = select_tools(["sample"], root)[0]

            fetch_tool(tool, root)

            current, detail = tool_status(tool, root)
            self.assertTrue(current, detail)
            self.assertEqual(
                (root / "toolkit/sample/bin/sample").resolve().read_bytes(), source.read_bytes()
            )

    def test_module_only_python_package_reports_current_without_an_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "toolkit/python/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\necho 7.1.0\n", encoding="utf-8")
            python.chmod(0o755)
            record = _record("https://example.invalid/module", "0" * 64)
            record.update(
                {
                    "id": "pytest-cov",
                    "environment": "python",
                    "asset": {
                        "kind": "uv-lock",
                        "url": None,
                        "archive": None,
                        "executables": [],
                    },
                    "version_argv": ["{python}", "-m", "ignored", "pytest-cov"],
                    "version_contains": "7.1.0",
                }
            )
            _write_registry(root, record)

            current, detail = tool_status(select_tools(["pytest-cov"], root)[0], root)

            self.assertTrue(current, detail)

    def test_checksum_failure_leaves_active_installation_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-sample"
            source.write_text("#!/bin/sh\necho sample 1.2.3\n", encoding="utf-8")
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            _write_registry(root, _record(source.as_uri(), checksum))
            tool = select_tools(["sample"], root)[0]
            fetch_tool(tool, root)
            active = root / "toolkit/sample/bin/sample"
            before = active.resolve().read_bytes()

            bad_record = _record(source.as_uri(), "0" * 64)
            _write_registry(root, bad_record)
            bad_tool = select_tools(["sample"], root)[0]
            with self.assertRaisesRegex(RegistryError, "checksum mismatch"):
                fetch_tool(bad_tool, root, force=True)

            self.assertEqual(active.resolve().read_bytes(), before)
            current, detail = tool_status(tool, root)
            self.assertTrue(current, detail)

    def test_update_accepts_only_a_verified_active_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "sample-one"
            first.write_text("#!/bin/sh\necho sample 1.2.3\n", encoding="utf-8")
            first_checksum = hashlib.sha256(first.read_bytes()).hexdigest()
            _write_registry(root, _record(first.as_uri(), first_checksum))
            fetch_tool(select_tools(["sample"], root)[0], root)

            second = root / "sample-two"
            second.write_text("#!/bin/sh\necho sample 2.0.0\n", encoding="utf-8")
            second_checksum = hashlib.sha256(second.read_bytes()).hexdigest()
            update_standalone(
                "sample",
                "2.0.0",
                second.as_uri(),
                second_checksum,
                "raw",
                root=root,
            )

            updated = select_tools(["sample"], root)[0]
            current, detail = tool_status(updated, root)
            self.assertTrue(current, detail)
            self.assertEqual(updated.version, "2.0.0")
            self.assertEqual(
                (root / "toolkit/sample/bin/sample").resolve().read_bytes(), second.read_bytes()
            )

    def test_failed_update_preserves_registry_and_active_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample-one"
            source.write_text("#!/bin/sh\necho sample 1.2.3\n", encoding="utf-8")
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            _write_registry(root, _record(source.as_uri(), checksum))
            tool = select_tools(["sample"], root)[0]
            fetch_tool(tool, root)
            registry_before = (root / "registry/tools.json").read_bytes()
            active_before = (root / "toolkit/sample/bin/sample").resolve().read_bytes()

            with self.assertRaisesRegex(RegistryError, "checksum mismatch"):
                update_standalone(
                    "sample",
                    "2.0.0",
                    source.as_uri(),
                    "0" * 64,
                    "raw",
                    root=root,
                )

            self.assertEqual((root / "registry/tools.json").read_bytes(), registry_before)
            self.assertEqual(
                (root / "toolkit/sample/bin/sample").resolve().read_bytes(), active_before
            )


if __name__ == "__main__":
    unittest.main()
