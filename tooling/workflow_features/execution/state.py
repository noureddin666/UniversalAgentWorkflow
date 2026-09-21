from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tooling.workflow_features.execution.plan import plan_digest


RUN_SCHEMA_VERSION = 1
TASK_STATES = ("pending", "active", "done", "blocked")
RUN_FILENAME = "run.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_path(directory: Path) -> Path:
    return directory / RUN_FILENAME


def load_run(directory: Path) -> dict[str, Any]:
    path = run_path(directory)
    if not path.is_file():
        raise FileNotFoundError(f"No run started for spec: {directory.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_run(directory: Path, run: dict[str, Any]) -> Path:
    path = run_path(directory)
    path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return path


def new_run(spec_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "spec_id": spec_id,
        "revision": 1,
        "plan_digest": plan_digest(tasks),
        "replans": 0,
        "tasks": [_new_task(task) for task in tasks],
    }


def _new_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        **task,
        "state": "pending",
        "attempts": 0,
        "evidence": [],
        "last_failure": None,
        "baseline": None,
        "code_paths": [],
        "test_paths": [],
        "started": None,
        "completed": None,
    }


def find_task(run: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in run["tasks"]:
        if task["id"] == task_id:
            return task
    raise ValueError(f"Unknown task: {task_id}")


def active_task(run: dict[str, Any]) -> dict[str, Any] | None:
    return next((task for task in run["tasks"] if task["state"] == "active"), None)


def blocked_tasks(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [task for task in run["tasks"] if task["state"] == "blocked"]


def next_pending(run: dict[str, Any]) -> dict[str, Any] | None:
    return next((task for task in run["tasks"] if task["state"] == "pending"), None)


def unfinished(run: dict[str, Any], exclude_id: str) -> list[dict[str, Any]]:
    return [task for task in run["tasks"] if task["id"] != exclude_id and task["state"] != "done"]


def counts(run: dict[str, Any]) -> dict[str, int]:
    return {state: sum(1 for task in run["tasks"] if task["state"] == state) for state in TASK_STATES}


def merge_plan(run: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep finished work, replace everything still open. Losing a finished task would orphan its evidence."""
    completed = {task["id"]: task for task in run["tasks"] if task["state"] in ("done", "blocked")}
    incoming = {task["id"] for task in tasks}
    missing = sorted(set(completed) - incoming)
    if missing:
        raise ValueError("tasks.md no longer declares finished tasks: " + ", ".join(missing))
    merged = [completed[task["id"]] if task["id"] in completed else _new_task(task) for task in tasks]
    return {
        **run,
        "revision": run["revision"] + 1,
        "replans": run.get("replans", 0) + 1,
        "plan_digest": plan_digest(tasks),
        "tasks": merged,
    }
