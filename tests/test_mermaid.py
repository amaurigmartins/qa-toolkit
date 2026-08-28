"""Tests for the optional containerized Mermaid PDF renderer."""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qa_toolkit import mermaid


class MermaidTests(unittest.TestCase):
    def test_container_arguments_are_bounded_for_podman_and_docker(self) -> None:
        source = Path("/source with spaces")
        target = Path("/target with spaces")
        for engine in ("podman", "docker"):
            with self.subTest(engine=engine):
                argv = mermaid._container_argv(
                    engine,
                    "example/mermaid:1.2.3",
                    source,
                    target,
                    Path("nested/diagram.mmd"),
                    Path("nested/diagram.pdf"),
                )
                self.assertEqual(argv[0:5], (engine, "run", "--rm", "--network", "none"))
                self.assertIn("example/mermaid:1.2.3", argv)
                self.assertIn("/data/source/nested/diagram.mmd", argv)
                self.assertIn("/data/target/nested/diagram.pdf", argv)
                self.assertNotIn("sh", argv)

    def test_default_target_incremental_render_and_force(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "config").mkdir()
            (root / "config/mermaid.toml").write_text(
                f'version = "1.2.3"\nimage = "example/mermaid:1.2.3@sha256:{"0" * 64}"\n',
                encoding="utf-8",
            )
            source = root / "diagrams"
            nested = source / "nested"
            nested.mkdir(parents=True)
            (source / "one.mmd").write_text("graph TD; A-->B\n", encoding="utf-8")
            (nested / "two.mmd").write_text("graph TD; B-->C\n", encoding="utf-8")

            def render(
                _engine: str,
                _configuration: mermaid.MermaidConfiguration,
                _source: Path,
                target: Path,
                _relative: Path,
                partial: Path,
                _timeout: int,
            ) -> None:
                output = target / partial
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"%PDF fixture")

            with (
                patch("qa_toolkit.mermaid._select_engine", return_value="podman"),
                patch("qa_toolkit.mermaid._run_container", side_effect=render) as invoke,
            ):
                first = mermaid.render_mermaid(source, root=root)
                second = mermaid.render_mermaid(source, root=root)
                third = mermaid.render_mermaid(source, root=root, force=True)

            self.assertEqual(first.target, source / "mermaid-pdf")
            self.assertEqual((first.sources, first.rendered, first.current), (2, 2, 0))
            self.assertEqual((second.sources, second.rendered, second.current), (2, 0, 2))
            self.assertEqual((third.sources, third.rendered, third.current), (2, 2, 0))
            self.assertEqual(invoke.call_count, 4)
            self.assertTrue((first.target / "one.pdf").is_file())
            self.assertTrue((first.target / "nested/two.pdf").is_file())

    def test_container_execution_never_uses_a_shell(self) -> None:
        configuration = mermaid.MermaidConfiguration("1.2.3", "example/mermaid:1.2.3")
        with patch(
            "qa_toolkit.mermaid.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as execute:
            mermaid._run_container(
                "docker",
                configuration,
                Path("/source"),
                Path("/target"),
                Path("diagram.mmd"),
                Path(".diagram.partial.pdf"),
                30,
            )
        self.assertFalse(execute.call_args.kwargs["shell"])
        self.assertEqual(execute.call_args.args[0][0:3], ["docker", "run", "--rm"])

    def test_source_validation_and_command_surface(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw)
            with self.assertRaisesRegex(mermaid.MermaidError, "no .mmd files"):
                mermaid._sources(source, source / "mermaid-pdf")
            with self.assertRaisesRegex(mermaid.MermaidError, "target must differ"):
                mermaid._paths(source, source)
            with self.assertRaisesRegex(mermaid.MermaidError, "must not contain"):
                mermaid._paths(source, source.parent)

            summary = mermaid.RenderSummary(1, 1, 0, source / "mermaid-pdf")
            stdout = io.StringIO()
            with (
                patch("qa_toolkit.mermaid.render_mermaid", return_value=summary) as render,
                contextlib.redirect_stdout(stdout),
            ):
                mermaid.main(["--source", str(source)])
            self.assertEqual(render.call_args.args, (source, None))
            self.assertIn("sources=1", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
