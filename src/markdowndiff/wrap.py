"""Tokenization, ins/del wrapping, and block-prefix-aware line wrappers.

These helpers preserve markdown block structure (headings, lists, tables,
blockquotes, fenced code) when surrounding line content with `<ins>`/`<del>`
tags, so the rendered preview keeps recognizing the original blocks.
"""

from __future__ import annotations

import re

from .styles import DEL_STYLE, INS_STYLE

TOKEN_RE = re.compile(r'(\s+|[*_`\[\]()#~|>!-])')
FENCE_RE = re.compile(r'^\s{0,3}(```|~~~)')
BLOCK_PREFIX_RE = re.compile(
    r'^(\s{0,3}(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s?))(.*)$'
)


def is_fence_line(line: str) -> bool:
    return bool(FENCE_RE.match(line))


def split_block_prefix(line: str) -> tuple[str, str]:
    m = BLOCK_PREFIX_RE.match(line)
    if m:
        return m.group(1), m.group(2)
    return "", line


def tokenize_line(line: str) -> list[str]:
    return [t for t in TOKEN_RE.split(line) if t != ""]


def wrap_ins(text: str) -> str:
    return f"<ins {INS_STYLE}>{text}</ins>" if text else ""


def wrap_del(text: str) -> str:
    return f"<del {DEL_STYLE}>{text}</del>" if text else ""


def is_table_row(line: str) -> bool:
    s = line.strip()
    return len(s) >= 2 and s.startswith("|") and s.endswith("|")


def is_table_separator_row(line: str) -> bool:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    inner = s[1:-1]
    return inner != "" and all(c in "-: |" for c in inner) and "-" in inner


def wrap_table_row(line: str, wrapper) -> str:
    stripped = line.rstrip("\n")
    parts = stripped.split("|")
    out = [parts[0]]
    for cell in parts[1:-1]:
        content = cell.strip()
        if not content:
            out.append(cell)
            continue
        leading = cell[: len(cell) - len(cell.lstrip())]
        trailing = cell[len(cell.rstrip()):]
        out.append(f"{leading}{wrapper(content)}{trailing}")
    out.append(parts[-1])
    return "|".join(out)


def wrap_line(line: str, wrapper) -> str:
    if is_table_separator_row(line):
        return line
    if is_table_row(line):
        return wrap_table_row(line, wrapper)
    prefix, content = split_block_prefix(line)
    if prefix:
        return f"{prefix}{wrapper(content)}"
    # Keep leading whitespace outside the wrapper so list-continuation
    # paragraphs (indented under their parent list item) keep their indent on
    # the actual line. If the indent is swallowed inside <ins>/<del>, the
    # line starts with an HTML tag at column 0, which CommonMark treats as
    # ending the list — and a following "2." can't restart the ordered list
    # because it can't interrupt a paragraph.
    stripped = line.lstrip()
    if stripped and stripped != line:
        leading = line[: len(line) - len(stripped)]
        return f"{leading}{wrapper(stripped)}"
    return wrapper(line)
