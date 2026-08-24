"""Small command surfaces for structured work-package transitions."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from qa_toolkit.filesystem import atomic_bytes
from qa_toolkit.paths import toolkit_root
from qa_toolkit.work import TEMPLATE_NAMES, WorkError
from qa_toolkit.work_git import (
    bind,
    calculate_release,
    finish,
    initialize,
    parse_validation,
    reconcile,
    report,
    retire,
    stage,
    status,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-work")
    operations = parser.add_subparsers(dest="operation", required=True)
    initialize_parser = operations.add_parser("init")
    initialize_parser.add_argument("work_id")
    initialize_parser.add_argument("--target", type=Path, default=Path.cwd())
    initialize_parser.add_argument("--repository", required=True)
    initialize_parser.add_argument("--issue", type=int, required=True)
    initialize_parser.add_argument("--pull-request", type=int)
    initialize_parser.add_argument("--remote", default="origin")
    initialize_parser.add_argument(
        "--kind", choices=("feature", "refactor", "release"), required=True
    )
    initialize_parser.add_argument("--branch", required=True)
    initialize_parser.add_argument("--base-branch", required=True)
    initialize_parser.add_argument("--base-sha", required=True)
    initialize_parser.add_argument("--plan-revision", type=int, required=True)
    initialize_parser.add_argument("--task", required=True)
    initialize_parser.add_argument("--title", required=True)
    initialize_parser.add_argument("--expected-parent", required=True)
    initialize_parser.add_argument("--subject", required=True)
    initialize_parser.add_argument(
        "--allow-path", action="append", dest="allowed_paths", required=True
    )
    initialize_parser.add_argument(
        "--validation-json", action="append", dest="validation_json", required=True
    )
    initialize_parser.add_argument("--proof", choices=("check", "sentinel"), required=True)
    initialize_parser.add_argument("--plan-file", type=Path, required=True)
    initialize_parser.add_argument("--task-file", type=Path, required=True)
    initialize_parser.add_argument("--retire-after-finish", action="store_true")

    for operation in ("stage", "finish", "retire", "status", "report"):
        command = operations.add_parser(operation)
        command.add_argument("work_id")
        command.add_argument("--target", type=Path, default=Path.cwd())
        if operation == "report":
            command.add_argument("--output", type=Path)
    bind_parser = operations.add_parser("bind")
    bind_parser.add_argument("work_id")
    bind_parser.add_argument("--target", type=Path, default=Path.cwd())
    bind_parser.add_argument("--pull-request", type=int, required=True)
    reconcile_parser = operations.add_parser("reconcile")
    reconcile_parser.add_argument("work_id")
    reconcile_parser.add_argument("--target", type=Path, default=Path.cwd())
    reconcile_parser.add_argument("--pull-request", type=int)
    template = operations.add_parser("template")
    template.add_argument("name", choices=tuple(sorted(TEMPLATE_NAMES)))
    release = operations.add_parser("release")
    release.add_argument("--base-version", required=True)
    release.add_argument("--message", action="append", dest="messages", required=True)
    return parser


def _initialize(options: argparse.Namespace) -> dict[str, object]:
    package = initialize(
        options.target,
        work_id=options.work_id,
        repository=options.repository,
        issue=options.issue,
        pull_request=options.pull_request,
        remote=options.remote,
        kind=options.kind,
        branch=options.branch,
        base_branch=options.base_branch,
        base_sha=options.base_sha,
        plan_revision=options.plan_revision,
        task_id=options.task,
        task_title=options.title,
        expected_parent=options.expected_parent,
        final_subject=options.subject,
        allowed_paths=tuple(options.allowed_paths),
        validation_argv=parse_validation(tuple(options.validation_json)),
        quality_proof=options.proof,
        plan_source=options.plan_file,
        task_source=options.task_file,
        retire_after_finish=options.retire_after_finish,
    )
    return package.state.as_dict()


def _template(name: str) -> str:
    path = toolkit_root() / "library" / "work-packages" / "templates" / f"{name}.md"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 262_144:
        raise WorkError(f"work template is unavailable: {name}")
    value = path.read_text(encoding="utf-8", errors="strict")
    if not value.strip():
        raise WorkError(f"work template is empty: {name}")
    return value


def main(arguments: Sequence[str] | None = None) -> None:
    """Execute exactly one work-package operation."""
    options = _parser().parse_args(arguments)
    try:
        if options.operation == "init":
            result: object = _initialize(options)
        elif options.operation == "stage":
            result = stage(options.target, options.work_id).as_dict()
        elif options.operation == "bind":
            result = bind(options.target, options.work_id, options.pull_request).as_dict()
        elif options.operation == "reconcile":
            result = reconcile(
                options.target, options.work_id, pull_request=options.pull_request
            ).as_dict()
        elif options.operation == "finish":
            result = finish(options.target, options.work_id).as_dict()
        elif options.operation == "retire":
            result = {
                "schema_version": 1,
                "status": "retired",
                "head": retire(options.target, options.work_id),
            }
        elif options.operation == "status":
            result = status(options.target, options.work_id).as_dict()
        elif options.operation == "report":
            rendered = report(options.target, options.work_id)
            if options.output is None:
                print(rendered, end="")
            else:
                atomic_bytes(options.output.resolve(), rendered.encode())
                print(options.output.resolve())
            return
        elif options.operation == "template":
            print(_template(options.name), end="")
            return
        else:
            result = calculate_release(options.base_version, tuple(options.messages)).as_dict()
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, UnicodeError, ValueError, WorkError) as error:
        print(f"qat-work-{options.operation}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
