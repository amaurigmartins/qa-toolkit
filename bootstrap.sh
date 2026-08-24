#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PAYLOAD="$ROOT/toolkit"
STAGING="$PAYLOAD/.staging"
UV_VERSION=0.11.21
UV_SHA256=8c88519b0ef0af9801fcdee419bbb12116bd9e6b18e162ae093c932d8b264050
UV_URL=https://github.com/astral-sh/uv/releases/download/0.11.21/uv-x86_64-unknown-linux-gnu.tar.gz
LINK_LAUNCHER=0

usage() {
  printf 'usage: %s [--link-launcher]\n' "$0" >&2
  exit 2
}

if [ "$#" -gt 1 ]; then
  usage
fi
if [ "$#" -eq 1 ]; then
  [ "$1" = "--link-launcher" ] || usage
  LINK_LAUNCHER=1
fi

[ "$(uname -s)" = Linux ] || { echo 'qa-toolkit: Linux is required' >&2; exit 2; }
[ "$(uname -m)" = x86_64 ] || { echo 'qa-toolkit: x86_64 is required' >&2; exit 2; }
command -v git >/dev/null 2>&1 || { echo 'qa-toolkit: Git is required' >&2; exit 2; }
command -v tar >/dev/null 2>&1 || { echo 'qa-toolkit: tar is required' >&2; exit 2; }

mkdir -p "$STAGING" "$PAYLOAD/.cache/uv" "$PAYLOAD/python-runtimes"
WORK=$(mktemp -d "$STAGING/bootstrap.XXXXXX")
cleanup() {
  rm -rf -- "$WORK"
}
trap cleanup EXIT HUP INT TERM

download() {
  source_url=$1
  destination=$2
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$source_url" -o "$destination"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$destination" "$source_url"
  else
    echo 'qa-toolkit: curl or wget is required' >&2
    exit 2
  fi
}

verify_sha256() {
  expected=$1
  file=$2
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$file" | awk '{print $1}')
  elif command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$file" | awk '{print $1}')
  else
    echo 'qa-toolkit: sha256sum or shasum is required' >&2
    exit 2
  fi
  [ "$actual" = "$expected" ] || {
    echo "qa-toolkit: checksum mismatch for $file" >&2
    exit 2
  }
}

replace_directory() {
  staged=$1
  target=$2
  previous="$STAGING/previous.$$.${target##*/}"
  if [ -e "$target" ]; then
    mv "$target" "$previous"
  fi
  if ! mv "$staged" "$target"; then
    [ ! -e "$previous" ] || mv "$previous" "$target"
    return 1
  fi
  [ ! -e "$previous" ] || rm -rf -- "$previous"
}

UV="$PAYLOAD/uv/bin/uv"
if [ ! -x "$UV" ] || ! "$UV" --version 2>/dev/null | grep -F "$UV_VERSION" >/dev/null; then
  archive="$WORK/uv.tar.gz"
  expanded="$WORK/uv-expanded"
  staged_uv="$WORK/uv"
  download "$UV_URL" "$archive"
  verify_sha256 "$UV_SHA256" "$archive"
  mkdir -p "$expanded" "$staged_uv/bin"
  tar -xzf "$archive" -C "$expanded"
  uv_binary=$(find "$expanded" -type f -name uv -print | head -n 1)
  uvx_binary=$(find "$expanded" -type f -name uvx -print | head -n 1)
  if [ -z "$uv_binary" ] || [ -z "$uvx_binary" ]; then
    echo 'qa-toolkit: uv archive is incomplete' >&2
    exit 2
  fi
  cp "$uv_binary" "$staged_uv/bin/uv"
  cp "$uvx_binary" "$staged_uv/bin/uvx"
  chmod +x "$staged_uv/bin/uv" "$staged_uv/bin/uvx"
  "$staged_uv/bin/uv" --version | grep -F "$UV_VERSION" >/dev/null || {
    echo 'qa-toolkit: uv version verification failed' >&2
    exit 2
  }
  replace_directory "$staged_uv" "$PAYLOAD/uv"
fi

python_stage="$WORK/python"
env \
  UV_CACHE_DIR="$PAYLOAD/.cache/uv" \
  UV_LINK_MODE=copy \
  UV_NO_PROGRESS=1 \
  UV_PYTHON_INSTALL_DIR="$PAYLOAD/python-runtimes" \
  "$UV" python install 3.11.15
env \
  UV_CACHE_DIR="$PAYLOAD/.cache/uv" \
  UV_LINK_MODE=copy \
  UV_NO_PROGRESS=1 \
  UV_PYTHON_INSTALL_DIR="$PAYLOAD/python-runtimes" \
  "$UV" venv --python 3.11.15 --relocatable "$python_stage"
env \
  UV_CACHE_DIR="$PAYLOAD/.cache/uv" \
  UV_LINK_MODE=copy \
  UV_NO_PROGRESS=1 \
  UV_PROJECT_ENVIRONMENT="$python_stage" \
  UV_PYTHON_INSTALL_DIR="$PAYLOAD/python-runtimes" \
  "$UV" sync --frozen --all-groups --project "$ROOT"
"$python_stage/bin/python" --version 2>&1 | grep -F 3.11.15 >/dev/null || {
  echo 'qa-toolkit: Python version verification failed' >&2
  exit 2
}
replace_directory "$python_stage" "$PAYLOAD/python"

PYTHONPATH="$ROOT/src" "$PAYLOAD/python/bin/python" -m qa_toolkit.tool_cli fetch --all

if [ "$LINK_LAUNCHER" -eq 1 ]; then
  [ -n "${HOME:-}" ] || { echo 'qa-toolkit: HOME is unavailable' >&2; exit 2; }
  launcher="$HOME/.local/bin/qat"
  mkdir -p "$HOME/.local/bin"
  if [ -e "$launcher" ] || [ -L "$launcher" ]; then
    if [ ! -L "$launcher" ] || [ "$(readlink "$launcher")" != "$ROOT/bin/qat" ]; then
      echo "qa-toolkit: refusing to replace foreign path $launcher" >&2
      exit 2
    fi
  else
    ln -s "$ROOT/bin/qat" "$launcher"
  fi
fi

echo 'qa-toolkit: central tool bundle is current'
