#!/usr/bin/env python3
"""Generate rendered-markdown diff files under .markdowndiff/.

For each changed .md file between a git base ref and the working tree, emits a
sibling file containing the same markdown with inline <ins>/<del> HTML tags
highlighting additions and deletions. Open the result in IntelliJ's markdown
preview to see the rendered diff with green/red backgrounds.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import NamedTuple

from .git_ops import (  # noqa: F401  -- re-export for tests/process_file
    find_changed_md_files,
    get_new_content,
    get_old_content,
    repo_root,
    run_git,
    verify_ref,
)
from .styles import (  # noqa: F401  -- re-export; engine + processing use these
    BLOCK_ADDED_STYLE,
    BLOCK_MODIFIED_STYLE,
    BLOCK_REMOVED_STYLE,
    DEL_STYLE,
    GENERATED_HEADER,
    INS_STYLE,
)
from .wrap import (  # noqa: F401  -- re-export for tests + engine
    BLOCK_PREFIX_RE,
    FENCE_RE,
    TOKEN_RE,
    is_fence_line,
    is_table_row,
    is_table_separator_row,
    split_block_prefix,
    tokenize_line,
    wrap_del,
    wrap_ins,
    wrap_line,
    wrap_table_row,
)

from .word_diff import (  # noqa: F401  -- re-export for tests + engine
    WORD_DIFF_RATIO_THRESHOLD,
    inline_word_diff,
    should_word_diff,
)

__version__ = "0.3.0"

# Public API. Other names exported from this module are internal — they are
# reachable for backwards-compat and tests, but may move or change without
# notice. See README "Public API" for the stability contract.
__all__ = ["__version__", "diff_to_markdown", "main"]


def find_uniform_fence_regions(
    lines: list[str], status: list[str], target_statuses: set[str]
) -> dict[int, int]:
    regions: dict[int, int] = {}
    i = 0
    while i < len(lines):
        if is_fence_line(lines[i]):
            j = i + 1
            while j < len(lines) and not is_fence_line(lines[j]):
                j += 1
            if j < len(lines) and all(
                status[k] in target_statuses for k in range(i, j + 1)
            ):
                regions[i] = j
            i = j + 1 if j < len(lines) else i + 1
        else:
            i += 1
    return regions


class FenceMap(NamedTuple):
    """Bundles a fence-region mapping plus its derived lookup sets."""

    starts: dict[int, int]
    indices: frozenset[int]
    ends: frozenset[int]

    @classmethod
    def build(cls, starts: dict[int, int]) -> "FenceMap":
        return cls(
            starts=dict(starts),
            indices=frozenset(
                k for s, e in starts.items() for k in range(s, e + 1)
            ),
            ends=frozenset(starts.values()),
        )


def map_old_to_new_index(old_i: int, opcodes) -> int | None:
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal" and i1 <= old_i < i2:
            return j1 + (old_i - i1)
    return None


def find_modified_fence_regions(
    lines: list[str], status: list[str]
) -> dict[int, int]:
    regions: dict[int, int] = {}
    i = 0
    while i < len(lines):
        if is_fence_line(lines[i]):
            j = i + 1
            while j < len(lines) and not is_fence_line(lines[j]):
                j += 1
            if (
                j < len(lines)
                and status[i] == "equal"
                and status[j] == "equal"
                and any(status[k] != "equal" for k in range(i + 1, j))
            ):
                regions[i] = j
            i = j + 1 if j < len(lines) else i + 1
        else:
            i += 1
    return regions


def diff_to_markdown(old: str, new: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    opcodes = difflib.SequenceMatcher(
        a=old_lines, b=new_lines, autojunk=False
    ).get_opcodes()

    new_status = ["equal"] * len(new_lines)
    old_status = ["equal"] * len(old_lines)
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "insert":
            for j in range(j1, j2):
                new_status[j] = "insert"
        elif tag == "delete":
            for i in range(i1, i2):
                old_status[i] = "delete"
        elif tag == "replace":
            for j in range(j1, j2):
                new_status[j] = "replace-new"
            for i in range(i1, i2):
                old_status[i] = "replace-old"

    added = FenceMap.build(
        find_uniform_fence_regions(
            new_lines, new_status, {"insert", "replace-new"}
        )
    )
    removed = FenceMap.build(
        find_uniform_fence_regions(
            old_lines, old_status, {"delete", "replace-old"}
        )
    )
    modified_starts = dict(
        find_modified_fence_regions(new_lines, new_status)
    )
    for old_start, old_end in find_modified_fence_regions(
        old_lines, old_status
    ).items():
        new_start = map_old_to_new_index(old_start, opcodes)
        new_end = map_old_to_new_index(old_end, opcodes)
        if (
            new_start is not None
            and new_end is not None
            and new_start not in added.starts
            and new_start not in modified_starts
        ):
            modified_starts[new_start] = new_end
    modified = FenceMap.build(modified_starts)

    out: list[str] = []
    # in_fence tracks the OUTPUT stream's fence state (toggled as we emit
    # fence markers) — not the source file's. Inside a fence we suppress
    # del/ins wrapping because HTML tags don't render in code blocks.
    in_fence = False

    def emit_new(j: int, line: str, wrapper=None) -> None:
        nonlocal in_fence
        if j in added.starts:
            out.append(f"<div {BLOCK_ADDED_STYLE}>")
            out.append("")
        elif j in modified.starts:
            out.append(f"<div {BLOCK_MODIFIED_STYLE}>")
            out.append("")
        if j in added.indices:
            out.append(line)
            if is_fence_line(line):
                in_fence = not in_fence
        elif is_fence_line(line):
            out.append(line)
            in_fence = not in_fence
        elif in_fence:
            out.append(line)
        elif wrapper is None:
            out.append(line)
        else:
            out.append(wrap_line(line, wrapper))
        if j in added.ends or j in modified.ends:
            out.append("")
            out.append("</div>")

    def emit_old_delete(i: int, line: str) -> None:
        nonlocal in_fence
        if i in removed.starts:
            out.append(f"<div {BLOCK_REMOVED_STYLE}>")
            out.append("")
        if i in removed.indices:
            out.append(line)
            if is_fence_line(line):
                in_fence = not in_fence
        elif in_fence:
            pass
        else:
            out.append(wrap_line(line, wrap_del))
        if i in removed.ends:
            out.append("")
            out.append("</div>")

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for j in range(j1, j2):
                emit_new(j, new_lines[j])
        elif tag == "insert":
            for j in range(j1, j2):
                emit_new(j, new_lines[j], wrap_ins)
        elif tag == "delete":
            for i in range(i1, i2):
                emit_old_delete(i, old_lines[i])
        elif tag == "replace":
            if (
                (i2 - i1) == 1
                and (j2 - j1) == 1
                and not in_fence
                and not is_fence_line(old_lines[i1])
                and not is_fence_line(new_lines[j1])
                and should_word_diff(old_lines[i1], new_lines[j1])
            ):
                out.append(inline_word_diff(old_lines[i1], new_lines[j1]))
            else:
                old_row_idxs = [
                    i for i in range(i1, i2) if is_table_row(old_lines[i])
                ]
                old_other_idxs = [
                    i for i in range(i1, i2) if not is_table_row(old_lines[i])
                ]
                new_row_idxs = [
                    j for j in range(j1, j2) if is_table_row(new_lines[j])
                ]
                new_other_idxs = [
                    j for j in range(j1, j2) if not is_table_row(new_lines[j])
                ]
                if (
                    old_row_idxs
                    and len(old_row_idxs) == len(new_row_idxs)
                    and all(
                        should_word_diff(old_lines[i], new_lines[j])
                        for i, j in zip(old_row_idxs, new_row_idxs)
                    )
                ):
                    for i, j in zip(old_row_idxs, new_row_idxs):
                        out.append(inline_word_diff(old_lines[i], new_lines[j]))
                else:
                    for i in old_row_idxs:
                        emit_old_delete(i, old_lines[i])
                    for j in new_row_idxs:
                        emit_new(j, new_lines[j], wrap_ins)
                had_rows = bool(old_row_idxs or new_row_idxs)
                had_other = bool(old_other_idxs or new_other_idxs)
                if had_rows and had_other and out and out[-1] != "":
                    out.append("")
                for i in old_other_idxs:
                    if not old_lines[i].strip():
                        continue
                    emit_old_delete(i, old_lines[i])
                for j in new_other_idxs:
                    emit_new(j, new_lines[j], wrap_ins)
    trailing = "\n" if (new.endswith("\n") or old.endswith("\n")) else ""
    return "\n".join(out) + trailing


from .processing import cleanup_stale, process_file  # noqa: F401, E402
from .cli import main  # noqa: F401, E402  -- keeps `markdowndiff:main` script entry working
