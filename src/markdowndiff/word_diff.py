"""Inline word-level diff for similar single-line replacements."""

from __future__ import annotations

import difflib

from .wrap import (
    is_table_row,
    is_table_separator_row,
    split_block_prefix,
    tokenize_line,
    wrap_del,
    wrap_ins,
)

WORD_DIFF_RATIO_THRESHOLD = 0.6
WORD_DIFF_MAX_FRAGMENTS = 8


def _count_word_diff_fragments(old_line: str, new_line: str) -> int:
    """Count the number of `<del>`/`<ins>` tags an `inline_word_diff` would emit.

    Mirrors `inline_word_diff`'s tokenization and prefix-peeling so the
    count reflects what the user would actually see. A `replace` opcode
    contributes 2 (one `<del>` and one `<ins>`); pure `insert` and
    `delete` opcodes contribute 1 each.
    """
    old_prefix, old_content = split_block_prefix(old_line)
    new_prefix, new_content = split_block_prefix(new_line)
    if old_prefix and old_prefix == new_prefix:
        old_line, new_line = old_content, new_content
    old_toks = tokenize_line(old_line)
    new_toks = tokenize_line(new_line)
    matcher = difflib.SequenceMatcher(a=old_toks, b=new_toks, autojunk=False)
    count = 0
    for tag, *_ in matcher.get_opcodes():
        if tag == "replace":
            count += 2
        elif tag == "insert" or tag == "delete":
            count += 1
    return count


def should_word_diff(old_line: str, new_line: str) -> bool:
    """True if a single-line replace should be highlighted at word level.

    Three rules: refuse if either line contains a backtick (HTML inside a
    code span wouldn't render); refuse if a token-level diff would emit
    more than `WORD_DIFF_MAX_FRAGMENTS` `<del>`/`<ins>` tags (heavily
    rewritten paragraphs become unreadable as a chain of small fragments
    — whole-line ins/del shows the before and after cleanly); otherwise
    require similarity ≥ `WORD_DIFF_RATIO_THRESHOLD` so unrelated
    rewrites fall back to whole-line ins/del rather than producing a
    noisy diff. For two table rows the similarity ratio is computed over
    the *cell list* — a long appended cell would otherwise drag a
    character-level ratio below the threshold even when most cells are
    unchanged. Table rows skip the fragmentation gate because cell-level
    diffing keeps fragment counts naturally low (one per changed cell).
    """
    if "`" in old_line or "`" in new_line:
        return False
    is_tbl = is_table_row(old_line) and is_table_row(new_line)
    if not is_tbl:
        if _count_word_diff_fragments(old_line, new_line) > WORD_DIFF_MAX_FRAGMENTS:
            return False
    char_ratio = difflib.SequenceMatcher(
        a=old_line, b=new_line, autojunk=False
    ).ratio()
    if char_ratio >= WORD_DIFF_RATIO_THRESHOLD:
        return True
    if is_tbl:
        # Char-level similarity drags below threshold when one row gains a
        # long cell — most cells are unchanged but the added content swells
        # the denominator. Cell-list similarity captures "most cells match"
        # directly, so use it as a second chance.
        old_cells = [c.strip() for c in old_line.rstrip("\n").split("|")[1:-1]]
        new_cells = [c.strip() for c in new_line.rstrip("\n").split("|")[1:-1]]
        cell_ratio = difflib.SequenceMatcher(
            a=old_cells, b=new_cells, autojunk=False
        ).ratio()
        return cell_ratio >= WORD_DIFF_RATIO_THRESHOLD
    return False


def cell_diff_table_row(old_line: str, new_line: str) -> str:
    """Cell-level diff for two table rows with different column counts.

    Splits both rows into cells and runs `SequenceMatcher` on the stripped
    cell contents. Equal cells pass through unchanged; inserted and deleted
    cells get their content wrapped in `<ins>`/`<del>` (with leading and
    trailing whitespace kept outside the tag so column alignment survives);
    replaced cells get a word-level diff. The column-boundary `|`
    characters are emitted as plain text between cells, never inside a
    diff tag — that's the property that makes this safe across renderers.
    """
    old_parts = old_line.rstrip("\n").split("|")
    new_parts = new_line.rstrip("\n").split("|")
    old_cells = old_parts[1:-1]
    new_cells = new_parts[1:-1]

    def wrap_cell(cell: str, wrapper) -> str:
        content = cell.strip()
        if not content:
            return cell
        leading = cell[: len(cell) - len(cell.lstrip())]
        trailing = cell[len(cell.rstrip()):]
        return f"{leading}{wrapper(content)}{trailing}"

    matcher = difflib.SequenceMatcher(
        a=[c.strip() for c in old_cells],
        b=[c.strip() for c in new_cells],
        autojunk=False,
    )
    cells_out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            cells_out.extend(new_cells[j1:j2])
        elif tag == "insert":
            cells_out.extend(wrap_cell(c, wrap_ins) for c in new_cells[j1:j2])
        elif tag == "delete":
            cells_out.extend(wrap_cell(c, wrap_del) for c in old_cells[i1:i2])
        elif tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                old_cell = old_cells[i1 + k]
                new_cell = new_cells[j1 + k]
                content = new_cell.strip()
                old_content = old_cell.strip()
                if not content and not old_content:
                    cells_out.append(new_cell)
                    continue
                leading = new_cell[: len(new_cell) - len(new_cell.lstrip())]
                trailing = new_cell[len(new_cell.rstrip()):]
                if should_word_diff(old_content, content):
                    cells_out.append(
                        f"{leading}{inline_word_diff(old_content, content)}{trailing}"
                    )
                else:
                    cells_out.append(
                        f"{leading}{wrap_del(old_content)}{wrap_ins(content)}{trailing}"
                    )
            for k in range(paired, j2 - j1):
                cells_out.append(wrap_cell(new_cells[j1 + k], wrap_ins))
            for k in range(paired, i2 - i1):
                cells_out.append(wrap_cell(old_cells[i1 + k], wrap_del))
    return "|".join([old_parts[0]] + cells_out + [new_parts[-1]])


def inline_word_diff(old_line: str, new_line: str) -> str:
    """Word-level diff for two similar lines, with shared prefix preserved.

    Three branches: when both lines are table rows, delegate to
    `cell_diff_table_row` so column-boundary pipes never end up inside a
    diff tag (which is what would let renderers collapse cells together).
    Otherwise: peel any matching block prefix (heading, list marker,
    blockquote) off both lines via `split_block_prefix` and recurse on
    the content, so the prefix stays outside any `<ins>`/`<del>` tag and
    block recognition survives. Then run a token-level `SequenceMatcher`
    on the remaining content, emitting `wrap_ins` / `wrap_del` for the
    differing token runs.
    """
    if is_table_row(old_line) and is_table_row(new_line):
        # Separator rows control table column count — they have no
        # content to diff and any wrapping turns the row into invalid
        # separator syntax, which makes GFM stop recognizing the table.
        # Emit the new separator unchanged so the renderer reads the
        # current column structure.
        if is_table_separator_row(old_line) or is_table_separator_row(new_line):
            return new_line
        return cell_diff_table_row(old_line, new_line)
    old_prefix, old_content = split_block_prefix(old_line)
    new_prefix, new_content = split_block_prefix(new_line)
    if old_prefix and old_prefix == new_prefix:
        return new_prefix + inline_word_diff(old_content, new_content)
    old_toks = tokenize_line(old_line)
    new_toks = tokenize_line(new_line)
    matcher = difflib.SequenceMatcher(a=old_toks, b=new_toks, autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.append("".join(new_toks[j1:j2]))
        elif tag == "delete":
            out.append(wrap_del("".join(old_toks[i1:i2])))
        elif tag == "insert":
            out.append(wrap_ins("".join(new_toks[j1:j2])))
        elif tag == "replace":
            out.append(wrap_del("".join(old_toks[i1:i2])))
            out.append(wrap_ins("".join(new_toks[j1:j2])))
    return "".join(out)
