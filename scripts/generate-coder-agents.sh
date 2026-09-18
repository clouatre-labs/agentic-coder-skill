#!/usr/bin/env bash
# generate-coder-agents.sh -- regenerate coder-* agent files for pi and Claude Code
# from per-role frontmatter fragments (tools/agents/{pi,claude}-coder-<role>.yaml)
# and the shared body (config/agents-shared/coder-<role>.md).
#
# Usage:
#   scripts/generate-coder-agents.sh --check   # exit 1 on drift
#   scripts/generate-coder-agents.sh --write   # regenerate files in place

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRAGMENTS="$ROOT/tools/agents"
BODIES="$ROOT/agents-shared"
PI_DIR="$ROOT/agents/pi"
CLAUDE_DIR="$ROOT/agents/claude"
MODE="${1:---check}"

usage() { echo "usage: $0 (--check|--write)" >&2; exit 2; }
[ "$MODE" = "--check" ] || [ "$MODE" = "--write" ] || usage

drift=0
for role in scout guard build check; do
  body="$BODIES/coder-$role.md"
  [ -f "$body" ] || { echo "ERROR: missing body $body" >&2; exit 2; }
  for target in pi claude; do
    frag="$FRAGMENTS/$target-coder-$role.yaml"
    out="$PI_DIR/coder-$role.md"
    [ "$target" = "claude" ] && out="$CLAUDE_DIR/coder-$role.md"
    [ -f "$frag" ] || { echo "ERROR: missing fragment $frag" >&2; exit 2; }
    tmp="$(mktemp)"
    {
      printf -- '---\n'
      cat "$frag"
      printf -- '---\n\n'
      cat "$body"
    } > "$tmp"
    if [ "$MODE" = "--write" ]; then
      mkdir -p "$(dirname "$out")"
      cp "$tmp" "$out"
    elif ! diff -u "$out" "$tmp" >/dev/null 2>&1; then
      echo "DRIFT: $out differs from fragments + shared body" >&2
      diff -u "$out" "$tmp" >&2 || true
      drift=1
    fi
    rm -f "$tmp"
  done
done

if [ "$MODE" = "--check" ]; then
  if [ "$drift" -ne 0 ]; then
    echo "Run: scripts/generate-coder-agents.sh --write" >&2
    exit 1
  fi
  echo "OK: generated coder agents match fragments + shared bodies"
fi
