"""Fence-region detection and old-to-new index mapping for the diff engine.

Identifies code-fence regions in the new file (or old file, for deletions)
that are wholly inserted, wholly deleted, or modified — so the engine can
wrap them in colored block-borders rather than try to mark up individual
fenced lines (HTML inside a code fence wouldn't render).
"""

from __future__ import annotations

from typing import NamedTuple

from .wrap import is_fence_line


def find_uniform_fence_regions(
    lines: list[str], status: list[str], target_statuses: set[str]
) -> dict[int, int]:
    """Find code-fence regions where every line shares one of `target_statuses`.

    A "uniform" fence region is one whose opening fence, closing fence, and
    every interior line all carry a status from `target_statuses` —
    e.g. all `insert` for a wholly-added code block. Returns
    `{start_idx: end_idx}` mapping the opening-fence line to the
    closing-fence line.
    """
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
        """Build a FenceMap from a `{start: end}` dict of fence-region bounds."""
        return cls(
            starts=dict(starts),
            indices=frozenset(
                k for s, e in starts.items() for k in range(s, e + 1)
            ),
            ends=frozenset(starts.values()),
        )


def map_old_to_new_index(old_i: int, opcodes) -> int | None:
    """Translate an old-list index to its corresponding new-list index.

    Only resolves inside `equal` regions of the diff opcodes; returns
    `None` if `old_i` falls inside an insert/delete/replace region. Used to
    align modified-fence regions detected on the old side back onto the
    new side when the engine merges them with regions detected on the
    new side.
    """
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal" and i1 <= old_i < i2:
            return j1 + (old_i - i1)
    return None


def find_modified_fence_regions(
    lines: list[str], status: list[str]
) -> dict[int, int]:
    """Find fenced regions whose markers are unchanged but whose body changed.

    Both fence markers must be `equal` (so the fence itself wasn't added
    or removed), but at least one *interior* line is non-equal — meaning
    the code block was edited in place. Returns `{start_idx: end_idx}`.
    """
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
