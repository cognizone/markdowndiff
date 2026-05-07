"""Per-file diff generation and stale-output cleanup."""

from __future__ import annotations

from pathlib import Path

from .engine import diff_to_markdown
from .git_ops import get_new_content, get_old_content
from .styles import GENERATED_HEADER


def process_file(path: str, base: str, root: Path, out_dir: Path) -> bool:
    """Generate the rendered diff for `path` (`base` → working tree) under `out_dir`.

    Returns False (and writes nothing) if the file is empty in both the base
    revision and the working tree; True if a diff file was written.
    """
    old = get_old_content(path, base, root)
    new = get_new_content(path, root)
    if not old and not new:
        return False
    content = GENERATED_HEADER + diff_to_markdown(old, new)
    out_path = out_dir / path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return True


def cleanup_stale(out_dir: Path, written: set[Path]) -> list[Path]:
    """Delete every .md under `out_dir` not in `written`, then prune empty dirs.

    Returns the list of deleted files. Non-`.md` files (and the persistent
    `.mode` file) are preserved.
    """
    if not out_dir.exists():
        return []
    removed: list[Path] = []
    for p in out_dir.rglob("*.md"):
        if p not in written:
            p.unlink()
            removed.append(p)
    for d in sorted(
        (p for p in out_dir.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            d.rmdir()
        except OSError:
            pass
    return removed
