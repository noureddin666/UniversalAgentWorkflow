from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _git(project_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def available(project_root: Path) -> bool:
    try:
        return _git(project_root, "rev-parse", "--is-inside-work-tree").returncode == 0
    except OSError:
        return False


def _dirty_paths(project_root: Path) -> list[str]:
    result = _git(project_root, "status", "--porcelain", "--untracked-files=all")
    if result.returncode != 0:
        return []
    paths = []
    for line in result.stdout.splitlines():
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        if entry:
            paths.append(entry.strip('"'))
    return paths


def _working_hash(project_root: Path, relative: str) -> str | None:
    if not (project_root / relative).is_file():
        return None
    result = _git(project_root, "hash-object", "--", relative)
    return result.stdout.strip() if result.returncode == 0 else None


def _head_hash(project_root: Path, relative: str) -> str | None:
    result = _git(project_root, "rev-parse", f"HEAD:{relative}")
    return result.stdout.strip() if result.returncode == 0 else None


def snapshot(project_root: Path) -> dict[str, Any] | None:
    """Content hashes of everything already dirty, so a later edit to the same file is still visible."""
    if not available(project_root):
        return None
    return {path: _working_hash(project_root, path) for path in _dirty_paths(project_root)}


def unchanged_since(project_root: Path, taken: dict[str, Any] | None, paths: list[str]) -> list[str]:
    if taken is None:
        return []
    stale = []
    for relative in paths:
        baseline = taken[relative] if relative in taken else _head_hash(project_root, relative)
        if _working_hash(project_root, relative) == baseline:
            stale.append(relative)
    return stale
