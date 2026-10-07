"""Cut pinned three.js source into the chunks the code-context suites use.

r150's ``three.module.js`` averages ~22 bytes a line, so the spec's "500 lines"
(protorikis's 115 KB / 191 KB prompts) is met by sizing a chunk in bytes rather
than literally counting 500 lines. ``CHUNK_BYTES`` of 64 KiB gives three chunks
of ~191 KB by turn 3 of ``multi_turn_2``, which is what pushes the fourth turn
past a 65,536-token window.
"""

from __future__ import annotations

import re

from bench import data

CHUNK_BYTES = 64 * 1024
GAP_LINES = 50  # keep cold windows on genuinely different source

_DECLARATION = re.compile(r"^(?:export\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)")
_FUNCTION = re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")


def require_lines(ctx) -> list[str]:
    lines = getattr(ctx, "three_js_lines", None)
    if not lines:
        raise data.DataMissing(data.DATA_DIR / data.THREE_JS_FILE)
    return lines


def find_functions(
    lines: list[str], min_body: int = 8, max_body: int = 80
) -> list[dict]:
    """Functions whose body is between ``min_body`` and ``max_body`` lines."""
    found: list[dict] = []
    for i, line in enumerate(lines):
        match = _FUNCTION.match(line)
        if not match:
            continue
        brace = _brace_index(lines, i)
        if brace is None:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        body = _body_lines(lines, brace, indent)
        if min_body <= len(body) <= max_body:
            found.append(
                {
                    "name": match.group(1),
                    "decl_index": i,
                    "brace_index": brace,
                    "body": body,
                }
            )
    return found


def _brace_index(lines: list[str], start: int) -> int | None:
    for i in range(start, min(start + 5, len(lines))):
        if "{" in lines[i] or lines[i].rstrip().endswith(")"):
            return i
    return start


def _body_lines(lines: list[str], brace_index: int, indent: str = "") -> list[str]:
    """The lines up to the function's own closing brace: the ``}`` at the declaration's
    indentation, not the first nested block's (fixed 7 Oct 2026: that cut WebGLBackground
    to 20 lines when the function runs well past 100)."""
    body: list[str] = []
    for line in lines[brace_index + 1 :]:
        if line.rstrip() in (indent + "}", indent + "};"):
            break
        body.append(line)
        if len(body) >= 200:
            break
    while body and not body[-1].strip():
        body.pop()
    return body


def context_window(lines: list[str], brace_index: int, preceding: int) -> str:
    start = max(0, brace_index - preceding)
    return "\n".join(lines[start : brace_index + 1])


def windows(
    lines: list[str],
    count: int,
    bytes_each: int = CHUNK_BYTES,
    gap: int = GAP_LINES,
) -> list[str]:
    """Return ``count`` byte-sized, non-overlapping windows of source."""
    chunks: list[str] = []
    pos = 0
    for _ in range(count):
        buf: list[str] = []
        size = 0
        while pos < len(lines) and size < bytes_each:
            line = lines[pos]
            buf.append(line)
            size += len(line) + 1
            pos += 1
        if not buf:
            break
        chunks.append("\n".join(buf))
        pos += gap
    return chunks


def find_declaration(lines: list[str], start: int = 0) -> tuple[str, str] | None:
    """First line that declares a function or class, with its name."""
    for line in lines[start:]:
        match = _DECLARATION.match(line.strip())
        if match:
            return line.strip(), match.group(1)
    return None
