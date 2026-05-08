#!/usr/bin/env python3
"""Generate rendered-markdown diff files under .markdowndiff/.

For each changed .md file between a git base ref and the working tree, emits a
sibling file containing the same markdown with inline <ins>/<del> HTML tags
highlighting additions and deletions. Open the result in IntelliJ's markdown
preview to see the rendered diff with green/red backgrounds.
"""

from __future__ import annotations

# Re-exports — see README "Project layout" for the dependency graph and
# README "Public API" for the stability contract. Names listed in `__all__`
# (below) are the supported library surface; everything else here is
# re-exported for tests and cross-module use, and may move without notice.
from .engine import diff_to_markdown  # noqa: F401
from .fence import (  # noqa: F401
    FenceMap,
    find_modified_fence_regions,
    find_uniform_fence_regions,
    map_old_to_new_index,
)
from .git_ops import (  # noqa: F401
    find_changed_md_files,
    get_new_content,
    get_old_content,
    repo_root,
    run_git,
    verify_ref,
)
from .processing import cleanup_stale, process_file  # noqa: F401
from .styles import (  # noqa: F401
    BLOCK_ADDED_STYLE,
    BLOCK_MODIFIED_STYLE,
    BLOCK_REMOVED_STYLE,
    DEL_STYLE,
    GENERATED_HEADER,
    INS_STYLE,
)
from .word_diff import (  # noqa: F401
    WORD_DIFF_RATIO_THRESHOLD,
    cell_diff_table_row,
    inline_word_diff,
    should_word_diff,
)
from .wrap import (  # noqa: F401
    BLOCK_PREFIX_RE,
    FENCE_RE,
    TOKEN_RE,
    is_fence_line,
    is_table_row,
    is_table_separator_row,
    split_block_prefix,
    table_column_count,
    tokenize_line,
    wrap_del,
    wrap_ins,
    wrap_line,
    wrap_table_row,
)

__version__ = "0.4.2"
__all__ = ["__version__", "diff_to_markdown", "main"]

# `cli` imports `__version__` back from this package root, so it must be
# loaded after `__version__` is defined here. Keeping this at the bottom
# breaks the circular import that would otherwise occur.
from .cli import main  # noqa: F401, E402  -- keeps `markdowndiff:main` script entry working
