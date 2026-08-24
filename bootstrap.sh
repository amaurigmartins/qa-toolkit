#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REGISTRY="$ROOT/registry/tools.json"

if [ ! -f "$REGISTRY" ]; then
    echo "qa-toolkit: missing registry/tools.json" >&2
    exit 2
fi

echo "qa-toolkit bootstrap is not available until C01 is complete" >&2
exit 2

