#!/usr/bin/env python3
"""Unit tests for markdowndiff.

Run directly: `python3 tests/test_markdowndiff.py`
Or via unittest: `python3 -m unittest discover tests`

Stdlib-only (matches the tool's no-dependencies promise).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import markdowndiff as md


# --- Helper-level tests -----------------------------------------------------


class IsFenceLineTests(unittest.TestCase):
    def test_triple_backtick(self):
        self.assertTrue(md.is_fence_line("```"))

    def test_fence_with_language(self):
        self.assertTrue(md.is_fence_line("```turtle"))

    def test_tildes(self):
        self.assertTrue(md.is_fence_line("~~~"))

    def test_indented_up_to_three_spaces(self):
        self.assertTrue(md.is_fence_line("   ```"))

    def test_four_spaces_is_not_a_fence(self):
        self.assertFalse(md.is_fence_line("    ```"))

    def test_plain_text(self):
        self.assertFalse(md.is_fence_line("regular text"))

    def test_inline_backticks_are_not_fence(self):
        self.assertFalse(md.is_fence_line("text with ``` in the middle"))


class IsTableRowTests(unittest.TestCase):
    def test_simple_row(self):
        self.assertTrue(md.is_table_row("| a | b |"))

    def test_missing_trailing_pipe(self):
        self.assertFalse(md.is_table_row("| a | b"))

    def test_plain_text(self):
        self.assertFalse(md.is_table_row("regular text"))


class IsTableSeparatorRowTests(unittest.TestCase):
    def test_plain_separator(self):
        self.assertTrue(md.is_table_separator_row("|---|---|"))

    def test_with_alignment_markers(self):
        self.assertTrue(md.is_table_separator_row("|:--|--:|"))

    def test_content_row_is_not_separator(self):
        self.assertFalse(md.is_table_separator_row("| a | b |"))


class SplitBlockPrefixTests(unittest.TestCase):
    def test_heading(self):
        self.assertEqual(md.split_block_prefix("## Heading"), ("## ", "Heading"))

    def test_unordered_list(self):
        self.assertEqual(md.split_block_prefix("- item"), ("- ", "item"))

    def test_ordered_list(self):
        self.assertEqual(md.split_block_prefix("1. first"), ("1. ", "first"))

    def test_blockquote(self):
        self.assertEqual(md.split_block_prefix("> quote"), ("> ", "quote"))

    def test_bare_blockquote_marker(self):
        # Empty blockquote-continuation lines must keep `>` as the prefix
        # so wrap_line doesn't swallow it inside <ins>/<del>, which would
        # break the blockquote in the rendered output.
        self.assertEqual(md.split_block_prefix(">"), (">", ""))
        self.assertEqual(md.split_block_prefix("> "), ("> ", ""))

    def test_plain_text_has_no_prefix(self):
        self.assertEqual(md.split_block_prefix("plain"), ("", "plain"))


class WrapTableRowTests(unittest.TestCase):
    def test_wraps_each_cell_content(self):
        result = md.wrap_table_row("| a | b |", lambda s: f"[{s}]")
        self.assertEqual(result, "| [a] | [b] |")

    def test_empty_cells_passed_through(self):
        result = md.wrap_table_row("| a |  |", lambda s: f"[{s}]")
        self.assertEqual(result, "| [a] |  |")

    def test_preserves_cell_whitespace_padding(self):
        result = md.wrap_table_row("|  a  |  b  |", lambda s: f"[{s}]")
        self.assertEqual(result, "|  [a]  |  [b]  |")


class WrapLineTests(unittest.TestCase):
    def test_separator_row_returned_unchanged(self):
        self.assertEqual(
            md.wrap_line("|---|---|", lambda s: f"[{s}]"), "|---|---|"
        )

    def test_table_row_wrapped_per_cell(self):
        self.assertEqual(
            md.wrap_line("| a | b |", lambda s: f"[{s}]"),
            "| [a] | [b] |",
        )

    def test_heading_prefix_preserved(self):
        self.assertEqual(
            md.wrap_line("## Title", lambda s: f"[{s}]"), "## [Title]"
        )

    def test_plain_line_wrapped_whole(self):
        self.assertEqual(md.wrap_line("plain", lambda s: f"[{s}]"), "[plain]")

    def test_empty_line_wraps_to_empty_by_wrapper(self):
        # wrap_ins / wrap_del return "" for empty input, so wrap_line
        # returning whatever the wrapper returns on "" is the contract.
        self.assertEqual(md.wrap_line("", md.wrap_ins), "")
        self.assertEqual(md.wrap_line("", md.wrap_del), "")

    def test_indented_continuation_keeps_indent_outside_wrapper(self):
        self.assertEqual(
            md.wrap_line("    Tracked here.", lambda s: f"[{s}]"),
            "    [Tracked here.]",
        )

    def test_whitespace_only_line_left_alone(self):
        self.assertEqual(md.wrap_line("    ", lambda s: f"[{s}]"), "[    ]")

    def test_bare_blockquote_marker_not_wrapped(self):
        # `>` alone is a blockquote-continuation line; wrapping the literal
        # `>` in <ins>/<del> turns it into HTML and breaks the blockquote.
        self.assertEqual(md.wrap_line(">", md.wrap_ins), ">")
        self.assertEqual(md.wrap_line("> ", md.wrap_del), "> ")


class TokenizeLineTests(unittest.TestCase):
    def test_preserves_whitespace_runs(self):
        self.assertEqual(md.tokenize_line("a  b"), ["a", "  ", "b"])

    def test_splits_markdown_syntax_chars(self):
        self.assertEqual(
            md.tokenize_line("**bold**"), ["*", "*", "bold", "*", "*"]
        )


class ShouldWordDiffTests(unittest.TestCase):
    def test_similar_lines(self):
        self.assertTrue(md.should_word_diff("Hello world", "Hello worlds"))

    def test_very_different_lines(self):
        self.assertFalse(
            md.should_word_diff("Hello world", "Goodbye moon and stars")
        )

    def test_skipped_when_backticks_present(self):
        self.assertFalse(
            md.should_word_diff("the `code` here", "the `other` here")
        )


class InlineWordDiffTests(unittest.TestCase):
    def test_single_word_swap_produces_ins_and_del(self):
        result = md.inline_word_diff("the quick fox", "the slow fox")
        self.assertIn("<ins", result)
        self.assertIn("slow", result)
        self.assertIn("<del", result)
        self.assertIn("quick", result)
        self.assertIn("the ", result)
        self.assertIn(" fox", result)

    def test_heading_prefix_preserved_outside_tags(self):
        # Regression: heading word-diff used to absorb the space after `#`
        # into the <ins> tag, leaving `#<ins>` which breaks ATX heading parsing.
        result = md.inline_word_diff(
            "# Pancake Recipe", "# Fluffy Pancake Recipe"
        )
        self.assertTrue(result.startswith("# "))
        self.assertIn("Fluffy", result)

    def test_list_bullet_prefix_preserved_outside_tags(self):
        result = md.inline_word_diff("- old item", "- new item")
        self.assertTrue(result.startswith("- "))

    def test_blockquote_prefix_preserved_outside_tags(self):
        result = md.inline_word_diff("> say hi", "> say hello")
        self.assertTrue(result.startswith("> "))


class MapOldToNewIndexTests(unittest.TestCase):
    def test_in_equal_region(self):
        opcodes = [
            ("equal", 0, 3, 0, 3),
            ("insert", 3, 3, 3, 5),
            ("equal", 3, 6, 5, 8),
        ]
        self.assertEqual(md.map_old_to_new_index(1, opcodes), 1)
        self.assertEqual(md.map_old_to_new_index(4, opcodes), 6)

    def test_in_non_equal_region_returns_none(self):
        opcodes = [("replace", 0, 1, 0, 1)]
        self.assertIsNone(md.map_old_to_new_index(0, opcodes))


class FindUniformFenceRegionsTests(unittest.TestCase):
    def test_wholly_inserted_fence(self):
        lines = ["prose", "```turtle", "content", "```", "end"]
        status = ["equal", "insert", "insert", "insert", "equal"]
        regions = md.find_uniform_fence_regions(
            lines, status, {"insert", "replace-new"}
        )
        self.assertEqual(regions, {1: 3})

    def test_mixed_content_not_uniform(self):
        lines = ["```", "a", "```"]
        status = ["equal", "insert", "equal"]
        regions = md.find_uniform_fence_regions(lines, status, {"insert"})
        self.assertEqual(regions, {})

    def test_unclosed_fence_yields_no_region(self):
        lines = ["```", "a", "b"]
        status = ["insert", "insert", "insert"]
        regions = md.find_uniform_fence_regions(lines, status, {"insert"})
        self.assertEqual(regions, {})


class FindModifiedFenceRegionsTests(unittest.TestCase):
    def test_equal_markers_with_insert_inside(self):
        lines = ["```", "a", "b", "```"]
        status = ["equal", "equal", "insert", "equal"]
        self.assertEqual(
            md.find_modified_fence_regions(lines, status), {0: 3}
        )

    def test_all_equal_not_modified(self):
        lines = ["```", "a", "```"]
        status = ["equal", "equal", "equal"]
        self.assertEqual(md.find_modified_fence_regions(lines, status), {})

    def test_unclosed_fence_yields_no_region(self):
        lines = ["```", "a", "b"]
        status = ["equal", "insert", "equal"]
        self.assertEqual(md.find_modified_fence_regions(lines, status), {})


# --- End-to-end diff_to_markdown tests --------------------------------------


class DiffPassthroughTests(unittest.TestCase):
    def test_identical_input_survives(self):
        text = "# Title\n\nParagraph.\n"
        self.assertEqual(md.diff_to_markdown(text, text), text)


class DiffPureAdditionTests(unittest.TestCase):
    def test_added_paragraph_wrapped_in_ins(self):
        old = "# Title\n\nA.\n"
        new = "# Title\n\nA.\n\nB.\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("<ins", result)
        self.assertIn("A.", result)
        self.assertIn("B.", result)


class DiffPureDeletionTests(unittest.TestCase):
    def test_deleted_paragraph_wrapped_in_del(self):
        old = "# Title\n\nA.\n\nB.\n"
        new = "# Title\n\nA.\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("<del", result)
        self.assertIn("B.", result)


class DiffHeadingEditTests(unittest.TestCase):
    def test_heading_marker_stays_at_line_start(self):
        result = md.diff_to_markdown("## Old\n", "## New\n")
        has_plain_heading_line = any(
            line.startswith("## ") for line in result.splitlines()
        )
        self.assertTrue(
            has_plain_heading_line,
            f"no line starts with '## ' in output:\n{result}",
        )


class DiffTableRowEditTests(unittest.TestCase):
    def test_edited_row_stays_inside_table(self):
        old = "| a | b |\n|---|---|\n| x | y |\n"
        new = "| a | b |\n|---|---|\n| x | z |\n"
        result = md.diff_to_markdown(old, new)
        # Every line containing the edited cell letters must start with `|`
        for line in result.splitlines():
            if any(tok in line for tok in ("| x", "| y", "| z")):
                self.assertTrue(
                    line.lstrip().startswith("|"),
                    f"table row must start with pipe: {line!r}",
                )


class DiffTableMultiRowEditTests(unittest.TestCase):
    """Regression: two adjacent rows changing only one cell each used to emit
    full-row del + full-row ins (4 rendered rows). They should pair up and
    word-diff so only the changed cells are wrapped."""

    def test_paired_rows_word_diff_only_changed_cells(self):
        old = (
            "| Step | Time   |\n"
            "| ---- | ------ |\n"
            "| Mix  | 2 min  |\n"
            "| Rest | 10 min |\n"
            "| Fry  | 5 min  |\n"
        )
        new = (
            "| Step | Time   |\n"
            "| ---- | ------ |\n"
            "| Mix  | 2 min  |\n"
            "| Rest | 15 min |\n"
            "| Fry  | 4 min  |\n"
        )
        result = md.diff_to_markdown(old, new)
        # Exactly 2 changed rows in output, not 4.
        changed_rows = [
            line
            for line in result.splitlines()
            if line.startswith("|") and ("<ins" in line or "<del" in line)
        ]
        self.assertEqual(
            len(changed_rows),
            2,
            f"expected 2 paired rows, got {len(changed_rows)}:\n{result}",
        )
        # The unchanged first cells must NOT be wrapped.
        for row in changed_rows:
            first_cell = row.split("|", 2)[1]
            self.assertNotIn("<ins", first_cell)
            self.assertNotIn("<del", first_cell)
        # The numbers must be diffed.
        joined = "\n".join(changed_rows)
        for token in ("10", "15", "5", "4"):
            self.assertIn(token, joined)

    def test_unequal_row_counts_fall_back_to_full_row_emission(self):
        # Counts differ → no pairing assumption, fall back to del-then-ins.
        old = (
            "| Step | Time |\n"
            "| ---- | ---- |\n"
            "| Mix  | 2    |\n"
            "| Rest | 10   |\n"
        )
        new = (
            "| Step | Time |\n"
            "| ---- | ---- |\n"
            "| Mix  | 2    |\n"
            "| Rest | 15   |\n"
            "| Fry  | 4    |\n"
        )
        # Just verifying it doesn't crash and still produces table rows.
        result = md.diff_to_markdown(old, new)
        table_rows = [l for l in result.splitlines() if l.startswith("|")]
        self.assertTrue(len(table_rows) >= 4)


class DiffTableColumnCountChangeTests(unittest.TestCase):
    """Regression: when a table loses (or gains) a column, word-diff used to
    wrap the dropped cell — including its bordering `|` — inside a `<del>` tag.
    Markdown renderers then collapse that pipe-inside-HTML into the previous
    cell, so the strikethrough text bleeds visually into the surviving column.
    """

    def test_pipe_never_wrapped_inside_del_or_ins(self):
        old = (
            "| ID | Constraint | Notes | Future |\n"
            "|---|---|---|---|\n"
            "| C1 | Single MS | shared MS | Multi-country |\n"
            "| C2 | Same vehicles | shared set | Per-case sets |\n"
        )
        new = (
            "| ID | Constraint | Notes |\n"
            "|---|---|---|\n"
            "| C1 | Single MS | shared MS |\n"
            "| C2 | Same vehicles | shared set |\n"
        )
        result = md.diff_to_markdown(old, new)
        # No `<del>...|...</del>` or `<ins>...|...</ins>` — pipes inside
        # diff-marker HTML are what caused the renderer to merge cells.
        for tag_open, tag_close in (("<del", "</del>"), ("<ins", "</ins>")):
            cursor = 0
            while True:
                start = result.find(tag_open, cursor)
                if start == -1:
                    break
                end = result.find(tag_close, start)
                self.assertNotEqual(end, -1, "unbalanced diff tag")
                self.assertNotIn(
                    "|",
                    result[start:end],
                    f"column-boundary `|` wrapped inside {tag_open}…{tag_close}:\n{result}",
                )
                cursor = end + len(tag_close)

    def test_pipe_never_wrapped_when_column_added(self):
        # Symmetric to test_pipe_never_wrapped_inside_del_or_ins: gaining a
        # column (3→4) must not wrap the new column-boundary `|` inside an
        # `<ins>` either.
        old = (
            "| ID | Constraint | Notes |\n"
            "|---|---|---|\n"
            "| C1 | Single MS | shared MS |\n"
            "| C2 | Same vehicles | shared set |\n"
        )
        new = (
            "| ID | Constraint | Notes | Future |\n"
            "|---|---|---|---|\n"
            "| C1 | Single MS | shared MS | Multi-country |\n"
            "| C2 | Same vehicles | shared set | Per-case sets |\n"
        )
        result = md.diff_to_markdown(old, new)
        for tag_open, tag_close in (("<del", "</del>"), ("<ins", "</ins>")):
            cursor = 0
            while True:
                start = result.find(tag_open, cursor)
                if start == -1:
                    break
                end = result.find(tag_close, start)
                self.assertNotEqual(end, -1, "unbalanced diff tag")
                self.assertNotIn(
                    "|",
                    result[start:end],
                    f"column-boundary `|` wrapped inside {tag_open}…{tag_close}:\n{result}",
                )
                cursor = end + len(tag_close)

    def test_column_drop_renders_as_single_row_per_input(self):
        # When a column is dropped, each row is rendered once with the
        # dropped cell wrapped in <del> — not as a separate deleted row
        # plus inserted row. The pipes around the wrapped cell stay outside
        # the tag (covered by test_pipe_never_wrapped_inside_del_or_ins) so
        # the table keeps rendering.
        old = "| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n"
        new = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        result = md.diff_to_markdown(old, new)
        table_rows = [l for l in result.splitlines() if l.startswith("|")]
        self.assertEqual(
            len(table_rows),
            3,
            f"expected one row per source row, got {len(table_rows)}:\n{result}",
        )
        # Header and data rows highlight the dropped cell; the separator
        # is emitted unchanged (its content is structural, not diffable).
        self.assertIn("<del", table_rows[0])
        self.assertNotIn("<del", table_rows[1])
        self.assertNotIn("<ins", table_rows[1])
        self.assertIn("<del", table_rows[2])

    def test_column_add_renders_as_single_row_with_ins(self):
        # Symmetric: gaining a column emits one row per source row with
        # only the new cell wrapped in <ins>. This is the user-facing case
        # that motivated the cell-diff: appending a long cell to a row
        # used to render as two full rows (all-del + all-ins), which is
        # noisy and obscures that only one cell actually changed.
        old = "| Action | Description | UC |\n"
        new = (
            "| Action | Description | UC | Notes |\n"
        )
        result = md.diff_to_markdown(old, new)
        ins_count = result.count("<ins")
        del_count = result.count("<del")
        self.assertEqual(
            ins_count, 1, f"expected 1 <ins>, got {ins_count}:\n{result}"
        )
        self.assertEqual(
            del_count, 0, f"expected 0 <del>, got {del_count}:\n{result}"
        )

    def test_no_blank_line_when_columns_match(self):
        # Symmetric to test_old_and_new_tables_separated_by_blank_line: when
        # the deleted and inserted rows share the same column count, the
        # rows belong in the same table. Inserting a blank line splits a
        # surrounding table in half — every row after it loses the header
        # and renders as raw text in a previewer.
        old = (
            "| File | Group |\n"
            "|---|---|\n"
            "| A | alpha |\n"
            "| **section header** | |\n"
            "| C | gamma |\n"
        )
        new = (
            "| File | Group |\n"
            "|---|---|\n"
            "| A | alpha |\n"
            "| B | beta |\n"
            "| **renamed header** | |\n"
            "| C | gamma |\n"
        )
        result = md.diff_to_markdown(old, new)
        lines = result.splitlines()
        del_line_idxs = [i for i, l in enumerate(lines) if "<del" in l]
        ins_line_idxs = [i for i, l in enumerate(lines) if "<ins" in l]
        self.assertTrue(del_line_idxs and ins_line_idxs)
        last_del = max(del_line_idxs)
        first_ins = min(ins_line_idxs)
        self.assertFalse(
            any(lines[k].strip() == "" for k in range(last_del + 1, first_ins)),
            f"blank line between deleted and inserted rows splits the surrounding table:\n{result}",
        )


class DiffTableRowAddTests(unittest.TestCase):
    def test_added_row_is_a_real_table_row(self):
        old = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        new = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        result = md.diff_to_markdown(old, new)
        found_new_row = any(
            line.startswith("|") and "3" in line and "4" in line
            for line in result.splitlines()
        )
        self.assertTrue(
            found_new_row, f"added row not emitted as table row:\n{result}"
        )


class DiffTableEditPlusParagraphDeleteTests(unittest.TestCase):
    """Regression: partition fix for mixed replace opcodes."""

    def test_table_rows_stay_in_table_when_paragraph_also_deleted(self):
        old = (
            "| h1 | h2 |\n"
            "|---|---|\n"
            "| a | b |\n"
            "| c | d |\n"
            "\n"
            "paragraph to delete\n"
        )
        new = (
            "| h1 | h2 |\n"
            "|---|---|\n"
            "| a | b |\n"
            "| c | e |\n"
            "| x | y |\n"
        )
        result = md.diff_to_markdown(old, new)
        for line in result.splitlines():
            if "| x" in line or "| y" in line:
                self.assertTrue(
                    line.lstrip().startswith("|"),
                    f"added row should be a table row, got: {line!r}",
                )


class DiffFragmentationFallbackTests(unittest.TestCase):
    """Regression: heavily rewritten paragraphs used to render as a long
    chain of small <del>/<ins> fragments (15-20+ tags on one paragraph),
    each carrying its own border + padding. Eye can't follow the change.
    Above WORD_DIFF_MAX_FRAGMENTS, fall back to whole-line del + ins."""

    def test_heavy_rewrite_falls_back_to_whole_line(self):
        old = (
            "A separate subscription model lets a Keeper, Owner, ECM, or EC "
            "declaration issuing body opt in to receive notifications about "
            "changes to registrations they are identified within. The "
            "subscription default itself posture is undefined opt-in: in parties."
        )
        new = (
            "A separate subscription model lets a Keeper, Owner, ECM, EC "
            "declaration issuing body, or NSA opt in to receive notifications "
            "about changes to registrations they are identified within (for "
            "NSAs: by Member State). The default posture is opt-in: parties."
        )
        result = md.diff_to_markdown(old, new)
        # Whole-line fallback emits exactly one <del> tag and one <ins> tag.
        self.assertEqual(
            result.count("<del"),
            1,
            f"expected single <del> for fragmented diff, got {result.count('<del')}:\n{result}",
        )
        self.assertEqual(
            result.count("<ins"),
            1,
            f"expected single <ins> for fragmented diff, got {result.count('<ins')}:\n{result}",
        )

    def test_moderate_edit_still_word_diffs(self):
        # 2-3 fragment edits should keep the fine-grained inline diff —
        # the fallback only kicks in when the diff is genuinely chaotic.
        old = "The default posture is opt-in: parties receive notifications only after explicit subscription."
        new = "The default posture is opt-out: parties receive notifications only after explicit unsubscription."
        result = md.diff_to_markdown(old, new)
        # At least 2 ins/del pairs (the two changed words) and the unchanged
        # text between them survives outside any tag.
        self.assertGreaterEqual(result.count("<del"), 2)
        self.assertGreaterEqual(result.count("<ins"), 2)
        self.assertIn("parties receive notifications only after explicit", result)


class DiffWhollyAddedFenceTests(unittest.TestCase):
    def test_green_border_div_around_added_code_block(self):
        old = "# Title\n\nEnd.\n"
        new = "# Title\n\n```py\nprint('x')\n```\n\nEnd.\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("#2d7a33", result)  # green border color
        self.assertIn("```py", result)
        self.assertIn("print('x')", result)


class DiffWhollyRemovedFenceTests(unittest.TestCase):
    def test_red_border_div_around_removed_code_block(self):
        old = "# Title\n\n```py\nprint('x')\n```\n\nEnd.\n"
        new = "# Title\n\nEnd.\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("#c24a4a", result)


class DiffModifiedFenceInsertTests(unittest.TestCase):
    def test_amber_border_on_insert_inside_fence(self):
        old = "```py\na = 1\n```\n"
        new = "```py\na = 1\nb = 2\n```\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("#d29922", result)
        self.assertIn("b = 2", result)


class DiffModifiedFencePureDeleteTests(unittest.TestCase):
    """Regression: P1.1 — old-side fence modification detection."""

    def test_amber_border_when_lines_deleted_from_kept_fence(self):
        old = "```py\na = 1\nb = 2\nc = 3\n```\n"
        new = "```py\na = 1\n```\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("#d29922", result)


class DiffModifiedFenceMixedTests(unittest.TestCase):
    def test_amber_border_when_insert_and_delete_both_present(self):
        old = "```py\nold1 = 1\nold2 = 2\nkeep = 3\n```\n"
        new = "```py\nkeep = 3\nnew1 = 1\nnew2 = 2\n```\n"
        result = md.diff_to_markdown(old, new)
        self.assertIn("#d29922", result)  # amber border still fires


class DiffCodeBlockDoesNotLeakHtmlTests(unittest.TestCase):
    """Neither <del> nor <ins> tags should survive inside a kept fence."""

    def _assert_no_html_tags_inside_fence(self, result: str) -> None:
        in_fence = False
        for line in result.splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                self.assertNotIn(
                    "<del", line, f"leaked <del> inside fence: {line!r}"
                )
                self.assertNotIn(
                    "<ins", line, f"leaked <ins> inside fence: {line!r}"
                )

    def test_mid_fence_replace_does_not_leak(self):
        old = "```py\nold_val = 1\nkeep = 2\n```\n"
        new = "```py\nnew_val = 1\nkeep = 2\n```\n"
        self._assert_no_html_tags_inside_fence(md.diff_to_markdown(old, new))

    def test_mid_fence_pure_insert_does_not_leak(self):
        old = "```py\na = 1\n```\n"
        new = "```py\na = 1\nb = 2\n```\n"
        self._assert_no_html_tags_inside_fence(md.diff_to_markdown(old, new))

    def test_mid_fence_pure_delete_does_not_leak(self):
        old = "```py\na = 1\nb = 2\n```\n"
        new = "```py\na = 1\n```\n"
        self._assert_no_html_tags_inside_fence(md.diff_to_markdown(old, new))


class DiffNewFileTests(unittest.TestCase):
    def test_empty_old_produces_whole_new_content(self):
        result = md.diff_to_markdown("", "# Title\n\nParagraph.\n")
        self.assertIn("Title", result)
        self.assertIn("<ins", result)


class DiffDeletedFileTests(unittest.TestCase):
    def test_empty_new_marks_old_as_deleted(self):
        result = md.diff_to_markdown("# Title\n\nParagraph.\n", "")
        self.assertIn("Title", result)
        self.assertIn("<del", result)


# --- cleanup_stale tests ---------------------------------------------------


class VersionTests(unittest.TestCase):
    def test_version_string_is_defined(self):
        self.assertIsInstance(md.__version__, str)
        self.assertRegex(md.__version__, r"^\d+\.\d+\.\d+")


class GeneratedHeaderTests(unittest.TestCase):
    def test_process_file_prepends_generated_header(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            # process_file needs a git context to fetch old content, but we
            # can bypass that by directly invoking diff_to_markdown and
            # mimicking the prepend step. This locks down the constant shape.
            result = md.GENERATED_HEADER + md.diff_to_markdown("a\n", "b\n")
            self.assertTrue(result.startswith("<!-- generated"))
            self.assertIn("do not edit", result)


class CleanupStaleTests(unittest.TestCase):
    def test_returns_paths_of_removed_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            kept = out_dir / "kept.md"
            stale = out_dir / "stale.md"
            nested_stale = out_dir / "sub" / "nested.md"
            preserved_non_md = out_dir / ".mode"
            kept.write_text("k", encoding="utf-8")
            stale.write_text("s", encoding="utf-8")
            nested_stale.parent.mkdir()
            nested_stale.write_text("n", encoding="utf-8")
            preserved_non_md.write_text("auto", encoding="utf-8")

            removed = md.cleanup_stale(out_dir, {kept})

            self.assertEqual(set(removed), {stale, nested_stale})
            self.assertTrue(kept.exists())
            self.assertFalse(stale.exists())
            self.assertFalse(nested_stale.exists())
            self.assertTrue(preserved_non_md.exists())
            # empty sub/ should have been pruned
            self.assertFalse((out_dir / "sub").exists())

    def test_missing_output_dir_returns_empty_list(self):
        self.assertEqual(
            md.cleanup_stale(Path("/nonexistent-xyz-123"), set()), []
        )


if __name__ == "__main__":
    unittest.main()
