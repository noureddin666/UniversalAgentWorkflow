from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any


TASK_LINE = re.compile(
    r"^- \[(?P<done>[ xX])\] (?P<id>TASK-\d{3,})(?: `(?P<requirement>[^`]+)`)? *(?P<title>.*)$"
)


def read_plan(directory: Path) -> list[dict[str, Any]]:
    path = directory / "tasks.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing tasks.md: {directory.name}")
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = TASK_LINE.match(line.rstrip())
        if not match:
            continue
        task_id = match["id"]
        if task_id in seen:
            raise ValueError(f"Duplicate task id in tasks.md: {task_id}")
        seen.add(task_id)
        tasks.append(
            {
                "id": task_id,
                "requirement_id": match["requirement"],
                "title": match["title"].strip(),
            }
        )
    if not tasks:
        raise ValueError(f"tasks.md declares no tasks: {directory.name}")
    return tasks


def plan_digest(tasks: list[dict[str, Any]]) -> str:
    payload = [[task["id"], task["requirement_id"], task["title"]] for task in tasks]
    return sha256(repr(payload).encode("utf-8")).hexdigest()
