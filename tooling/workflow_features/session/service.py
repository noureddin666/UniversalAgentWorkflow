from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, load_workflow_settings
from tooling.workflow_features.routing import resolve_route


WORKFLOW_INTENTS = ("feature", "bugfix", "diagnosis", "refactor", "review", "discovery")


def agent_budget(project_root: Path, agents: int, concurrency: int, high_effort: int) -> dict[str, Any]:
    settings = load_workflow_settings(project_root)
    violations = []
    if agents > settings.agent_maximum_count:
        violations.append(f"agent count {agents} exceeds {settings.agent_maximum_count}")
    if concurrency > settings.agent_maximum_concurrency:
        violations.append(f"concurrency {concurrency} exceeds {settings.agent_maximum_concurrency}")
    if high_effort > settings.agent_maximum_high_effort:
        violations.append(f"high-effort count {high_effort} exceeds {settings.agent_maximum_high_effort}")
    status = "over-limit" if violations else "warning" if agents > settings.agent_warning_count else "healthy"
    return {"status": status, "agents": agents, "concurrency": concurrency, "high_effort": high_effort, "violations": violations}


def _handoff_path(project_root: Path) -> Path:
    settings = load_workflow_settings(project_root)
    return PATHS.agent_root(project_root) / settings.handoff_path


def read_handoff(project_root: Path) -> dict[str, Any]:
    path = _handoff_path(project_root)
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    status = "missing"
    for line in content.splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", 1)[1].strip().lower()
            break
    return {
        "path": path.relative_to(project_root).as_posix(),
        "status": status,
        "active": status == "active",
        "content": content,
    }


def validate_handoff(project_root: Path) -> list[str]:
    settings = load_workflow_settings(project_root)
    handoff = read_handoff(project_root)
    content = handoff["content"]
    if not content:
        return []
    errors: list[str] = []
    lines = content.splitlines()
    if len(lines) > settings.handoff_max_lines:
        errors.append(f"Handoff has {len(lines)} lines; maximum is {settings.handoff_max_lines}")
    if len(content) > settings.handoff_max_characters:
        errors.append(
            f"Handoff has {len(content)} characters; maximum is {settings.handoff_max_characters}"
        )
    if handoff["status"] not in {"active", "complete", "empty"}:
        errors.append("Handoff Status must be active, complete, or empty")
    if handoff["active"] and not any(line.lower().startswith("next:") for line in lines):
        errors.append("Active handoff must contain a Next field")
    return errors


def clear_handoff(project_root: Path) -> Path:
    path = _handoff_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Handoff\n\nStatus: empty\n", encoding="utf-8")
    return path


def context_budget(project_root: Path, requested_path: str, intent: str) -> dict[str, Any]:
    if intent not in WORKFLOW_INTENTS:
        raise ValueError(f"Unknown intent: {intent}")
    settings = load_workflow_settings(project_root)
    route = resolve_route(project_root, requested_path, intent)
    candidates = [
        "AGENTS.md",
        ".agent/ROUTER.md",
        ".agent/vendor/universal-agent-workflow/core/WORKFLOW.md",
        *route["context"],
        route["workflow"],
        *(f".agent/specs/{spec_id}/spec.md" for spec_id in route["specs"]),
    ]
    handoff = read_handoff(project_root)
    if handoff["active"]:
        candidates.append(handoff["path"])
    files: list[dict[str, Any]] = []
    total_characters = 0
    for reference in dict.fromkeys(candidates):
        path = project_root / reference
        if not path.is_file():
            files.append({"path": reference, "missing": True, "characters": 0, "tokens": 0})
            continue
        characters = len(path.read_text(encoding="utf-8"))
        tokens = math.ceil(characters / settings.context_characters_per_token)
        total_characters += characters
        files.append(
            {"path": reference, "missing": False, "characters": characters, "tokens": tokens}
        )
    total_tokens = math.ceil(total_characters / settings.context_characters_per_token)
    status = "healthy"
    if total_tokens > settings.context_max_tokens:
        status = "over-limit"
    elif total_tokens > settings.context_warning_tokens:
        status = "warning"
    return {
        "path": route["path"],
        "intent": intent,
        "status": status,
        "total_characters": total_characters,
        "estimated_tokens": total_tokens,
        "warning_tokens": settings.context_warning_tokens,
        "max_tokens": settings.context_max_tokens,
        "files": files,
    }
