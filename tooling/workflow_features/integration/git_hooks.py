from __future__ import annotations

from pathlib import Path


MARKER = "Universal Agent Workflow"

PRE_COMMIT = """#!/usr/bin/env sh
# Universal Agent Workflow: rebuild the project index so it never lags its sources.
set -eu

root=$(git rev-parse --show-toplevel)
cd "$root"

PYTHON="${PYTHON:-python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    PYTHON=python3
fi

"$PYTHON" .agent/workflow.py build-index >/dev/null

for index in .agent/INDEX.json .agent/INDEX.md .agent/scopes/*/INDEX.json .agent/scopes/*/INDEX.md; do
    if [ -f "$index" ]; then
        git add "$index"
    fi
done
"""


def _git_directory(project_root: Path) -> Path:
    marker = project_root / ".git"
    if not marker.exists():
        raise FileNotFoundError(f"Not a Git repository: {marker}")
    if marker.is_dir():
        return marker
    reference = marker.read_text(encoding="utf-8").strip()
    if not reference.startswith("gitdir:"):
        raise ValueError(f"Unsupported .git file: {marker}")
    return (project_root / reference.split(":", 1)[1].strip()).resolve()


def install_git_hooks(project_root: Path, force: bool = False) -> Path:
    hooks = _git_directory(project_root) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    path = hooks / "pre-commit"
    if path.exists() and not force:
        if MARKER not in path.read_text(encoding="utf-8", errors="ignore"):
            raise FileExistsError(
                f"A pre-commit hook already exists at {path}. Review it, then re-run with --force."
            )
    path.write_text(PRE_COMMIT, encoding="utf-8")
    path.chmod(0o755)
    return path
