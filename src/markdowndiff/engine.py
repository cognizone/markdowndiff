"""Core diff engine: turn old + new markdown into rendered-diff markdown.

Public API surface for `diff_to_markdown` is documented in README.
"""

from __future__ import annotations

import difflib

from .fence import (
    FenceMap,
    find_modified_fence_regions,
    find_uniform_fence_regions,
    map_old_to_new_index,
)
from .styles import (
    BLOCK_ADDED_STYLE,
    BLOCK_MODIFIED_STYLE,
    BLOCK_REMOVED_STYLE,
)
from .word_diff import inline_word_diff, should_word_diff
from .wrap import (
    is_fence_line,
    is_table_row,
    table_column_count,
    wrap_del,
    wrap_ins,
    wrap_line,
)


def diff_to_markdown(old: str, new: str) -> str:
    """Generate rendered-diff markdown from old + new file contents.

    Pipeline:

    1. Compute line-level opcodes via `difflib.SequenceMatcher` on the
       two line lists.
    2. Tag each old/new line with its diff status (`insert`, `delete`,
       `replace-old`, `replace-new`, or `equal`).
    3. Detect fenced-code regions: uniformly added or removed (wrapped in
       a coloured `<div>` block-border because HTML inside a code fence
       wouldn't render), and modified-in-place (amber border).
    4. Walk the opcodes again and emit each region, with two fallbacks
       for `replace`: word-level inline diff for similar single lines,
       and per-row pairing for table edits.

    Returns the merged markdown with `<ins>` / `<del>` tags and block
    borders. The trailing newline is preserved if either input had one.
    """
    # Phase 1: line-level diff opcodes.
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    opcodes = difflib.SequenceMatcher(
        a=old_lines, b=new_lines, autojunk=False
    ).get_opcodes()

    # Phase 2: tag each old/new line with its diff status.
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

    # Phase 3: detect fenced-code regions (uniformly added/removed, or
    # modified-in-place) so the engine can wrap them in colored block
    # borders rather than try to mark up individual fenced lines.
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

    # Phase 4: walk opcodes and emit each region, with word-diff and
    # table-row fallbacks for `replace` opcodes.
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
                    if old_row_idxs and new_row_idxs:
                        old_cols = {
                            table_column_count(old_lines[i])
                            for i in old_row_idxs
                        }
                        new_cols = {
                            table_column_count(new_lines[j])
                            for j in new_row_idxs
                        }
                        if old_cols != new_cols or len(old_cols) > 1:
                            # Column-count changed: separate the deleted and
                            # inserted row groups with a blank line, otherwise
                            # GFM merges them into a single table and the
                            # mismatched rows render with trailing/merged cells.
                            # When columns match, leave them joined so the
                            # surrounding table (rows above and below this
                            # replace block) keeps rendering as one table.
                            out.append("")
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
