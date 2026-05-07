"""Command-line interface for markdowndiff."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .git_ops import (
    find_changed_md_files,
    repo_root,
    run_git,
    verify_ref,
)
from .processing import cleanup_stale, process_file


def resolve_base(
    args: argparse.Namespace, root: Path, mode_file: Path
) -> tuple[str, str]:
    """Return (base_ref, human_label) for the current invocation.

    Precedence: --branch > --base > persisted .mode file > auto-detect
    (on trunk → HEAD; elsewhere → merge-base with trunk).
    """
    if args.branch:
        use_branch_mode = True
    elif args.base is not None:
        use_branch_mode = False
    elif mode_file.exists():
        saved = mode_file.read_text(encoding="utf-8").strip()
        if saved == "branch":
            use_branch_mode = True
        elif saved == "uncommitted":
            use_branch_mode = False
        else:
            _, current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
            use_branch_mode = current.strip() != args.trunk
    else:
        _, current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
        use_branch_mode = current.strip() != args.trunk

    if use_branch_mode:
        code, merge_base = run_git(["merge-base", "HEAD", args.trunk], root)
        merge_base = merge_base.strip()
        if code != 0 or not merge_base:
            sys.exit(
                f"error: could not compute merge-base with '{args.trunk}'"
            )
        return merge_base, f"merge-base with {args.trunk} ({merge_base[:8]})"
    base = args.base or "HEAD"
    verify_ref(base, root)
    return base, base


def main() -> int:
    """Entry point for the `markdowndiff` CLI.

    Parses flags, resolves the base ref (via `resolve_base`), iterates over
    changed `.md` files, and writes the rendered-diff output under
    `<output>/`. Returns the process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generate rendered-markdown diff files. For each changed .md "
            "file between <base> and the working tree, write a sibling file "
            "under <output>/ containing the same markdown with inline "
            "<ins>/<del> HTML tags highlighting additions and deletions. "
            "Open the result in IntelliJ's markdown preview to see the "
            "rendered diff with green/red backgrounds."
        )
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--base",
        default=None,
        help=(
            "Git ref to compare the working tree against. Overrides the "
            "auto-detected default and the persistent mode file."
        ),
    )
    parser.add_argument(
        "--branch",
        action="store_true",
        help=(
            "Compare against the merge-base with <trunk>, showing everything "
            "that changed on this branch. Overrides --base."
        ),
    )
    parser.add_argument(
        "--trunk",
        default="main",
        help="Trunk branch used by --branch and auto-detect (default: main).",
    )
    parser.add_argument(
        "--output",
        default=".markdowndiff",
        help="Output directory relative to the repo root (default: .markdowndiff).",
    )
    mode_ops = parser.add_mutually_exclusive_group()
    mode_ops.add_argument(
        "--set-mode",
        choices=["uncommitted", "branch", "auto"],
        help=(
            "Persist a default mode in <output>/.mode and exit without "
            "regenerating. 'auto' removes the file so auto-detect resumes."
        ),
    )
    mode_ops.add_argument(
        "--show-mode",
        action="store_true",
        help="Print the persisted mode (or 'auto' if no mode file) and exit.",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file progress and summary output (errors still print).",
    )
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="List each stale file that cleanup removed.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional pathspecs to limit which files are processed.",
    )
    args = parser.parse_args()

    root = repo_root()
    out_dir = root / args.output
    mode_file = out_dir / ".mode"

    def say(msg: str) -> None:
        if not args.quiet:
            print(msg)

    if args.show_mode:
        if mode_file.exists():
            print(mode_file.read_text(encoding="utf-8").strip())
        else:
            print("auto")
        return 0

    if args.set_mode:
        if args.set_mode == "auto":
            if mode_file.exists():
                mode_file.unlink()
                say(f"Mode reset to auto (removed {mode_file}).")
            elif args.verbose:
                print("Mode already auto (no mode file present).")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            mode_file.write_text(args.set_mode + "\n", encoding="utf-8")
            say(f"Mode set to '{args.set_mode}' (wrote {mode_file}).")
        return 0

    base, base_label = resolve_base(args, root, mode_file)

    files = find_changed_md_files(base, root, args.paths)

    written: set[Path] = set()
    for path in files:
        if process_file(path, base, root, out_dir):
            written.add(out_dir / path)
            say(f"  {path} -> {args.output}/{path}")

    removed: list[Path] = []
    if not args.paths:
        removed = cleanup_stale(out_dir, written)

    if args.verbose and removed:
        for p in removed:
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            print(f"  removed stale {rel}")

    if not written and not removed:
        say(f"No changed .md files found vs {base_label}.")
        return 0

    parts = []
    if written:
        parts.append(f"Wrote {len(written)} file(s)")
    if removed:
        parts.append(f"removed {len(removed)} stale file(s)")
    say(f"{', '.join(parts)} in {args.output}/ (vs {base_label})")
    return 0
