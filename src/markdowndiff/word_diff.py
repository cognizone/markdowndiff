"""Inline word-level diff for similar single-line replacements."""

from __future__ import annotations

import difflib

from .wrap import (
    is_table_row,
    split_block_prefix,
    table_column_count,
    tokenize_line,
    wrap_del,
    wrap_ins,
)

WORD_DIFF_RATIO_THRESHOLD = 0.6


def should_word_diff(old_line: str, new_line: str) -> bool:
    """True if a single-line replace should be highlighted at word level.

    Three rules: refuse if either line contains a backtick (HTML inside a
    code span wouldn't render); refuse if both lines are table rows with
    different column counts (a per-cell tokenizer would wrap a column-
    boundary `|` inside a `<del>` tag, which markdown renderers then
    collapse into the previous cell); otherwise require difflib similarity
    ≥ `WORD_DIFF_RATIO_THRESHOLD` so unrelated rewrites fall back to
    whole-line ins/del rather than producing a noisy character-level diff.
    """
    if "`" in old_line or "`" in new_line:
        return False
    if (
        is_table_row(old_line)
        and is_table_row(new_line)
        and table_column_count(old_line) != table_column_count(new_line)
    ):
        return False
    return difflib.SequenceMatcher(
        a=old_line, b=new_line, autojunk=False
    ).ratio() >= WORD_DIFF_RATIO_THRESHOLD


def inline_word_diff(old_line: str, new_line: str) -> str:
    """Word-level diff for two similar lines, with shared prefix preserved.

    Two-step shape: first peel any matching block prefix (heading, list
    marker, blockquote) off both lines via `split_block_prefix` and recurse
    on the content, so the prefix stays outside any `<ins>`/`<del>` tag and
    block recognition survives. Then run a token-level `SequenceMatcher`
    on the remaining content, emitting `wrap_ins` / `wrap_del` for the
    differing token runs.
    """
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
