"""Git subprocess wrappers and content readers used by the CLI and engine."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout


def repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        sys.exit("error: git is not installed or not on PATH")
    except subprocess.CalledProcessError:
        sys.exit("error: not inside a git repository")
    return Path(result.stdout.strip())


def verify_ref(ref: str, root: Path) -> None:
    code, _ = run_git(["rev-parse", "--verify", "--quiet", ref], root)
    if code != 0:
        sys.exit(f"error: base ref '{ref}' is not a valid git reference")


def find_changed_md_files(base: str, root: Path, paths: list[str]) -> list[str]:
    pathspec = ["--", *paths] if paths else []
    _, tracked = run_git(["diff", "--name-only", base, *pathspec], root)
    _, untracked = run_git(
        ["ls-files", "--others", "--exclude-standard", *pathspec], root
    )
    files = set()
    for line in (tracked + untracked).splitlines():
        line = line.strip()
        if line.lower().endswith(".md"):
            files.add(line)
    return sorted(files)


def get_old_content(path: str, base: str, root: Path) -> str:
    _, out = run_git(["show", f"{base}:{path}"], root)
    return out


def get_new_content(path: str, root: Path) -> str:
    abs_path = root / path
    if abs_path.exists():
        return abs_path.read_text(encoding="utf-8")
    return ""
