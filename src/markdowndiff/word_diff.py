"""Inline word-level diff for similar single-line replacements."""

from __future__ import annotations

import difflib

from .wrap import split_block_prefix, tokenize_line, wrap_del, wrap_ins

WORD_DIFF_RATIO_THRESHOLD = 0.6


def should_word_diff(old_line: str, new_line: str) -> bool:
    if "`" in old_line or "`" in new_line:
        return False
    return difflib.SequenceMatcher(
        a=old_line, b=new_line, autojunk=False
    ).ratio() >= WORD_DIFF_RATIO_THRESHOLD


def inline_word_diff(old_line: str, new_line: str) -> str:
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
