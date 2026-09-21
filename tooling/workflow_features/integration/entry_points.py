from __future__ import annotations

from pathlib import Path
from typing import Any

from tooling.workflow_config import WorkflowSettings, load_workflow_settings


POINTER = """# Agent instructions

This repository uses the Universal Agent Workflow.

Read `AGENTS.md` first and follow it. Project facts, path routing, verified commands, feature specs,
and architectural boundaries live under `.agent/`.

Resolve the paths you are about to touch before reading anything else:

```shell
./.agent/workflow.sh route-changes    # PowerShell: ./.agent/workflow.ps1 route-changes
```

Do not restate project facts here. This file only points at the real source.
"""

CURSOR_FRONTMATTER = "---\ndescription: Universal Agent Workflow entry point\nalwaysApply: true\n---\n\n"


def _content(relative: str) -> str:
    if relative.endswith(".mdc"):
        return CURSOR_FRONTMATTER + POINTER
    return POINTER


def sync_entry_points(
    project_root: Path, settings: WorkflowSettings | None = None
) -> dict[str, Any]:
    """Create pointer files for agent tools that do not read AGENTS.md. Never overwrites."""
    resolved = settings or load_workflow_settings(project_root)
    created: list[str] = []
    existing: list[str] = []
    for relative in resolved.entry_points:
        path = project_root / relative
        if path.exists():
            existing.append(relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_content(relative), encoding="utf-8")
        created.append(relative)
    return {"created": created, "left_alone": existing}


def entry_point_warnings(project_root: Path) -> list[str]:
    settings = load_workflow_settings(project_root)
    warnings = []
    for relative in settings.entry_points:
        path = project_root / relative
        if path.is_file() and "AGENTS.md" not in path.read_text(encoding="utf-8", errors="ignore"):
            warnings.append(f"{relative} exists but does not point at AGENTS.md")
    return warnings
