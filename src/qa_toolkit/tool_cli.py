"""Command-line surfaces for the central tool registry."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from qa_toolkit.registry import (
    RegistryError,
    fetch_tool,
    list_rows,
    load_registry,
    select_tools,
    tool_status,
    update_standalone,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qat-tool")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("tools", nargs="*")
    status_parser.add_argument("--json", action="store_true")
    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("tools", nargs="*")
    fetch_parser.add_argument("--all", action="store_true")
    fetch_parser.add_argument("--force", action="store_true")
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("tool")
    update_parser.add_argument("version")
    update_parser.add_argument("url")
    update_parser.add_argument("sha256")
    update_parser.add_argument(
        "--archive", choices=("raw", "tar.gz", "tar.xz", "zip"), required=True
    )
    update_parser.add_argument("--version-contains")
    return parser


def _list(as_json: bool) -> int:
    rows = list_rows()
    if as_json:
        print(
            json.dumps([{"id": row[0], "version": row[1], "environment": row[2]} for row in rows])
        )
    else:
        for identifier, version, environment in rows:
            print(f"{identifier}\t{version}\t{environment}")
    return 0


def _status(identifiers: Sequence[str], as_json: bool) -> int:
    tools = select_tools(identifiers) if identifiers else load_registry()
    rows = []
    current = True
    for tool in tools:
        valid, detail = tool_status(tool)
        rows.append(
            {"id": tool.tool_id, "version": tool.version, "current": valid, "detail": detail}
        )
        current = current and valid
    if as_json:
        print(json.dumps(rows))
    else:
        for row in rows:
            state = "current" if row["current"] else row["detail"]
            print(f"{row['id']}\t{row['version']}\t{state}")
    return 0 if current else 1


def _fetch(identifiers: Sequence[str], fetch_all: bool, force: bool) -> int:
    if fetch_all == bool(identifiers):
        raise RegistryError("fetch requires tool IDs or --all, but not both")
    tools = load_registry() if fetch_all else select_tools(identifiers)
    handled_environments: set[str] = set()
    for tool in tools:
        if tool.environment in handled_environments:
            continue
        fetch_tool(tool, force=force)
        print(f"{tool.tool_id}\t{tool.version}\tcurrent")
        if tool.environment != "standalone":
            handled_environments.add(tool.environment)
    return 0


def main(arguments: Sequence[str] | None = None) -> None:
    """Run one independent registry operation."""
    parser = _parser()
    options = parser.parse_args(arguments)
    try:
        if options.operation == "list":
            code = _list(options.json)
        elif options.operation == "status":
            code = _status(options.tools, options.json)
        elif options.operation == "fetch":
            code = _fetch(options.tools, options.all, options.force)
        else:
            update_standalone(
                options.tool,
                options.version,
                options.url,
                options.sha256,
                options.archive,
                options.version_contains,
            )
            print(f"{options.tool}\t{options.version}\tcurrent")
            code = 0
    except RegistryError as error:
        print(f"qat-tool-{options.operation}: {error}", file=sys.stderr)
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
