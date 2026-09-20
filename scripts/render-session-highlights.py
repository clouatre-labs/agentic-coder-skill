#!/usr/bin/env python3
"""Render an animated terminal GIF replaying highlights of a real coding-agent session.

Reads a curated, hardcoded set of line ranges from a session transcript JSONL,
extracts the actual text at render time, writes an asciicast v2 .cast file, and
runs `agg` to produce docs/examples/session-highlights.gif.

Deterministic and re-runnable. Requires: python3 (stdlib only) and `agg`
(https://github.com/asciinema/agg). If `agg` is missing, fall back to a
pure-PIL GIF writer (no repo dependencies added).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT = Path(
    "/Users/hugues.clouatre/.pi/agent/sessions/"
    "--Users-hugues.clouatre-git-clouatre-labs-aptu-coder--/"
    "2026-09-19T15-12-50-506Z_01a0ba3a-2f49-7289-99b0-e18f504933c9.jsonl"
)
CAST_PATH = REPO_ROOT / "docs" / "examples" / "session-highlights.cast"
GIF_PATH = REPO_ROOT / "docs" / "examples" / "session-highlights.gif"

COLS = 100
ROWS = 16
SECONDS_PER_FRAME = 2.2

# Curated highlight frames: (label, line numbers into the JSONL, content kind).
# Deterministic: each render reads exactly these lines and pulls text.
FRAMES = [
    ("user request", [4], "text"),
    ("orchestrator answers: five parallel sessions", [8], "text"),
    ("plan approved", [9, 88], "text"),
    ("SCOUT x5 spawned in parallel", [29], "text"),
    ("tier classification", [29], "classification"),
    ("scout progress", [50], "text"),
    ("GUARD verifies issue 1582", [76], "text"),
    ("GUARD catch: scout overstated", [77], "result"),
    ("BUILD 1582 spawned", [88], "text"),
    ("first session through BUILD", [98], "text"),
    ("PR #1584 ready", [105], "text"),
    ("CHECK FAIL gate", [145], "text"),
    ("semver fix via 0.35.0 bump", [254], "text"),
    ("all five PRs ready", [291], "table"),
    ("merge: #1584 through #1587", [323], "text"),
    ("rebase 1588 onto new main", [321], "text"),
    ("all five merged", [332], "text"),
    ("final summary: all 5 PRs merged, CI green", [336], "table"),
]


def read_line(path: Path, n: int) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        for i, raw in enumerate(fh, start=1):
            if i == n:
                return json.loads(raw)
    raise ValueError(f"transcript has only {i} lines; wanted line {n}")


def message_parts(event: dict) -> list[dict]:
    return event.get("message", {}).get("content", [])


def first_text(event: dict) -> str:
    for part in message_parts(event):
        if part.get("type") == "text":
            return part["text"]
    raise ValueError(f"line has no text block: {event.get('id')}")


def extract(event: dict, kind: str) -> str:
    if kind == "text":
        return first_text(event)
    if kind == "result":
        return str(event["data"]["result"])
    if kind == "classification":
        text = first_text(event)
        for line in text.splitlines():
            if "Classification" in line:
                return line.strip()
        raise ValueError("classification line not found")
    if kind == "table":
        text = first_text(event)
        lines = text.splitlines()
        # keep heading plus table rows, cap row count
        kept: list[str] = []
        for ln in lines:
            if "|" in ln or not kept:
                kept.append(ln)
            if len(kept) >= 12:
                break
        return "\n".join(kept)
    raise ValueError(f"unknown kind: {kind}")


def clip(text: str, width: int = COLS - 2, max_lines: int = ROWS - 3) -> str:
    out_lines: list[str] = []
    for raw in text.splitlines():
        raw = raw.rstrip()
        if not raw:
            continue
        s = raw.encode("ascii", "replace").decode("ascii")
        while len(s) > width:
            out_lines.append(s[:width])
            s = "  " + s[width:]
        out_lines.append(s)
        if len(out_lines) >= max_lines:
            break
    if len(out_lines) == max_lines and len(text.splitlines()) > max_lines:
        out_lines[-1] = "  [...]"
    return "\n".join(out_lines)


def render_frame(label: str, body: str) -> str:
    banner = "-- {} --".format(label.upper())
    width = COLS - 2
    banner = banner[:width]
    pad = max(0, (width - len(banner)) // 2)
    rule = "-" * width
    return f"\n{rule}\n{' ' * pad}{banner}\n{rule}\n{body}\n"


def build_cast(frames_text: list[str], path: Path) -> None:
    header = {
        "version": 2,
        "width": COLS,
        "height": ROWS,
        "timestamp": 0,
        "env": {"SHELL": "/bin/sh", "TERM": "xterm-256color"},
    }
    lines = [json.dumps(header)]
    t = 0.0
    for text in frames_text:
        lines.append(json.dumps([round(t, 3), "o", text]))
        t += SECONDS_PER_FRAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_agg(cast: Path, gif: Path) -> bool:
    if shutil.which("agg") is None:
        return False
    gif.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "agg",
            "--cols",
            str(COLS),
            "--rows",
            str(ROWS),
            "--font-size",
            "14",
            "--speed",
            "1",
            str(cast),
            str(gif),
        ],
        check=True,
    )
    return True


def run_pil_fallback(frames_text: list[str], gif: Path) -> None:
    """Pure-PIL fallback: render each frame as a simple terminal-style image."""
    from PIL import Image, ImageDraw, ImageFont

    scale_x, scale_y, pad = 8, 16, 12
    img_w = COLS * scale_x + pad * 2
    img_h = ROWS * scale_y + pad * 2
    font = None
    for name in ("Menlo.ttc", "Monaco.dfont", "Courier New.ttf"):
        try:
            font = ImageFont.truetype(name, 13)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    images = []
    for text in frames_text:
        img = Image.new("RGB", (img_w, img_h), (24, 24, 28))
        draw = ImageDraw.Draw(img)
        y = pad
        for ln in text.splitlines():
            draw.text((pad, y), ln, fill=(220, 220, 220), font=font)
            y += scale_y
        images.append(img)
    durations_ms = [int(SECONDS_PER_FRAME * 1000)] * len(images)
    images[0].save(
        gif, save_all=True, append_images=images[1:], duration=durations_ms, loop=0
    )


def main() -> int:
    frames_text: list[str] = []
    for label, line_nums, kind in FRAMES:
        try:
            body = clip("\n".join(extract(read_line(TRANSCRIPT, n), kind) for n in line_nums))
            frames_text.append(render_frame(label, body))
        except (KeyError, ValueError) as exc:
            print(f"warn: skipping frame '{label}': {exc}", file=sys.stderr)

    build_cast(frames_text, CAST_PATH)
    print(f"cast written: {CAST_PATH} ({len(frames_text)} frames)")

    if run_agg(CAST_PATH, GIF_PATH):
        print(f"gif written by agg: {GIF_PATH}")
    else:
        print("agg not found; using PIL fallback", file=sys.stderr)
        run_pil_fallback(frames_text, GIF_PATH)
        print(f"gif written by PIL fallback: {GIF_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
