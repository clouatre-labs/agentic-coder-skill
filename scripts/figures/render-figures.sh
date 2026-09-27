#!/usr/bin/env sh
# Mermaid → Excalidraw figure pipeline.
#
#   figures/*.mmd  (source of truth, LLM-editable)
#     → figures/*.excalidraw  (scripts/figures/mmd2excalidraw.mjs, styled)
#     → figures/*.svg         (Kroki render + rounded white canvas padding)
#
# Usage: scripts/figures/render-figures.sh [--check] [file.mmd ...]
#   --check  regenerate in a temp dir and fail on any diff with the committed
#            artifacts (same drift-gate pattern as scripts/generate-coder-agents.sh)
# Without arguments: all .mmd files under figures/.
set -eu

cd "$(dirname "$0")/../.."

check=0
files=""
for arg in "$@"; do
  case $arg in
    --check) check=1 ;;
    *) files="$files $arg" ;;
  esac
done
if [ -z "$files" ]; then
  for f in figures/*.mmd; do
    [ -e "$f" ] && files="$files $f"
  done
fi
[ -n "$files" ] || { echo "no .mmd figures found" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

for mmd in $files; do
  name=$(basename "$mmd" .mmd)
  if [ "$check" = 1 ]; then
    outdir=$tmp
  else
    outdir=figures
  fi
  mkdir -p "$outdir"

  # 1. Convert + style: .mmd → .excalidraw
  node scripts/figures/mmd2excalidraw.mjs "$mmd" "$outdir/$name.excalidraw"

  # 2. Render: .excalidraw → .svg via Kroki, then pad the viewBox with a
  #    20px margin and add a rounded white background (shapeshift style,
  #    mirroring decisions-judge-mcp scripts/render-diagram.sh).
  curl -fsSL --data-binary @"$outdir/$name.excalidraw" -H "Content-Type: text/plain" \
    https://kroki.io/excalidraw/svg -o "$outdir/$name.svg"
  python3 - "$outdir/$name.svg" <<'EOF'
import re, sys

path = sys.argv[1]
s = open(path).read()
m = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"', s)
if not m:
    sys.exit(f"no viewBox found in {path}")
x, y, w, h = (float(g) for g in m.groups())
x, y, w, h = x - 20, y - 20, w + 40, h + 40
s = s[:m.start()] + f'viewBox="{x:g} {y:g} {w:g} {h:g}"' + s[m.end():]
s = re.sub(r'(<svg[^>]*?)width="[\d.]+" height="[\d.]+"',
           rf'\g<1>width="{w:g}" height="{h:g}"', s, count=1)
bg = f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="24" fill="#ffffff"></rect>'
if re.search(r'<rect [^>]*fill="#ffffff"', s):
    s = re.sub(r'<rect [^>]*fill="#ffffff"[^>]*>(</rect>)?', bg, s, count=1)
else:
    s = re.sub(r'(<metadata[^>]*></metadata>)', rf'\1{bg}', s, count=1)
open(path, "w").write(s)
EOF
  echo "rendered $mmd -> $outdir/$name.excalidraw, $outdir/$name.svg"
done

if [ "$check" = 1 ]; then
  drift=0
  for mmd in $files; do
    name=$(basename "$mmd" .mmd)
    if ! diff -u "figures/$name.excalidraw" "$tmp/$name.excalidraw"; then
      echo "DRIFT: figures/$name.excalidraw does not match regeneration from $mmd" >&2
      echo "       run: sh scripts/figures/render-figures.sh" >&2
      drift=1
    fi
    # Kroki SVG output carries float-precision noise between renders, so
    # compare a canonical form: every number rounded to 1 decimal.
    # (Normalized via temp files, not process substitution: /bin/sh is
    # bash-3.2 POSIX mode on macOS and lacks <(...).)
    norm() {
      python3 -c "
import re, sys
s = open(sys.argv[1]).read()
s = re.sub(r'base64,[A-Za-z0-9+/=]+', 'base64,X', s)
s = re.sub(r'-?\\d+\\.\\d+', lambda m: f'{float(m.group(0)):.1f}', s)
open(sys.argv[2], 'w').write(s)
" "$1" "$2"
    }
    norm "figures/$name.svg" "$tmp/$name.norm.svg"
    norm "$tmp/$name.svg" "$tmp/$name.norm.new.svg"
    if ! diff -u "$tmp/$name.norm.svg" "$tmp/$name.norm.new.svg"; then
      echo "DRIFT: figures/$name.svg does not match regeneration from $mmd" >&2
      echo "       run: sh scripts/figures/render-figures.sh" >&2
      drift=1
    fi
  done
  exit $drift
fi
