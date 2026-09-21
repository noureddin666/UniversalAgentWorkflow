from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, WorkflowSettings, load_workflow_settings
from tooling.workflow_features.execution.changes import snapshot, unchanged_since
from tooling.workflow_features.execution.plan import plan_digest, read_plan
from tooling.workflow_features.execution.state import (
    active_task,
    blocked_tasks,
    counts,
    find_task,
    load_run,
    merge_plan,
    new_run,
    next_pending,
    now,
    run_path,
    unfinished,
    save_run,
)
from tooling.workflow_features.local_runtime import run_verification
from tooling.workflow_features.routing import (
    analyze_impact,
    project_context,
    resolve_route,
    scope_paths,
)
from tooling.workflow_features.specs import link_requirement, load_spec, load_spec_requirements


def start_run(project_root: Path, spec_id: str, force: bool) -> dict[str, Any]:
    directory, _ = load_spec(project_root, spec_id)
    if run_path(directory).is_file() and not force:
        raise FileExistsError(f"Run already started for {spec_id}; pass --force to restart it")
    save_run(directory, new_run(spec_id, read_plan(directory)))
    return status(project_root, spec_id)


def next_task(project_root: Path, spec_id: str) -> dict[str, Any]:
    directory, spec = load_spec(project_root, spec_id)
    run = _current_run(directory)
    blocked = blocked_tasks(run)
    if blocked:
        return {
            "spec_id": spec_id,
            "task": None,
            "done": False,
            "halted": True,
            "blocked": [task["id"] for task in blocked],
            "reason": "A blocked task halts the chain; fix it and run `run retry <task-id>`",
            "last_failure": blocked[0]["last_failure"],
            "counts": counts(run),
        }
    task = active_task(run) or next_pending(run)
    if task is None:
        return {"spec_id": spec_id, "task": None, "done": True, "halted": False, "counts": counts(run)}
    if task["state"] == "pending":
        task["state"] = "active"
        task["baseline"] = snapshot(project_root)
        task["started"] = task.get("started") or now()
        save_run(directory, run)
    return _brief(project_root, directory, spec, run, task)


def complete_task(
    project_root: Path,
    spec_id: str,
    task_id: str,
    evidence: list[str],
    handoff: str | None,
    code_paths: list[str],
    test_paths: list[str],
    allow_no_change: bool,
) -> dict[str, Any]:
    directory, spec = load_spec(project_root, spec_id)
    run = _current_run(directory)
    task = find_task(run, task_id)
    if task["state"] != "active":
        raise ValueError(f"{task_id} is {task['state']}, not active")
    _check_task_delivered(project_root, task, code_paths, test_paths, allow_no_change)
    settings = load_workflow_settings(project_root)
    verification = _verification(project_root, spec)
    result = (
        run_verification(project_root, verification)
        if verification
        else {"passed": True, "results": []}
    )
    if not result["passed"]:
        return _record_failure(directory, run, task, result, settings)
    task["state"] = "done"
    task["last_failure"] = None
    task["evidence"] = evidence
    task["code_paths"] = code_paths
    task["test_paths"] = test_paths
    task["completed"] = now()
    save_run(directory, run)
    traced = _trace(project_root, spec_id, task, evidence, code_paths, test_paths)
    carry = handoff and unfinished(run, task_id)
    written = _write_handoff(project_root, settings, handoff) if carry else None
    return {
        "spec_id": spec_id,
        "task_id": task_id,
        "passed": True,
        "verification": result["results"],
        "handoff": written,
        "traceability": traced,
        "counts": counts(run),
    }


def retry_task(project_root: Path, spec_id: str, task_id: str) -> dict[str, Any]:
    directory, _ = load_spec(project_root, spec_id)
    run = _current_run(directory)
    task = find_task(run, task_id)
    if task["state"] != "blocked":
        raise ValueError(f"{task_id} is {task['state']}, not blocked")
    running = active_task(run)
    if running:
        raise ValueError(f"{running['id']} is still active; finish it before retrying {task_id}")
    task["state"] = "active"
    task["attempts"] = 0
    save_run(directory, run)
    return next_task(project_root, spec_id)


def replan(project_root: Path, spec_id: str) -> dict[str, Any]:
    directory, _ = load_spec(project_root, spec_id)
    run = load_run(directory)
    save_run(directory, merge_plan(run, read_plan(directory)))
    return status(project_root, spec_id)


def status(project_root: Path, spec_id: str) -> dict[str, Any]:
    directory, _ = load_spec(project_root, spec_id)
    run = load_run(directory)
    return {
        "spec_id": spec_id,
        "revision": run["revision"],
        "plan_changed": run["plan_digest"] != plan_digest(read_plan(directory)),
        "counts": counts(run),
        "tasks": [
            {key: task[key] for key in ("id", "requirement_id", "title", "state", "attempts")}
            for task in run["tasks"]
        ],
    }


def report(project_root: Path, spec_id: str) -> dict[str, Any]:
    """What the chain actually cost. It cannot compare itself against one long session."""
    directory, _ = load_spec(project_root, spec_id)
    run = load_run(directory)
    tasks = run["tasks"]
    failed = sum(task["attempts"] for task in tasks)
    finished = [task for task in tasks if task["state"] == "done"]
    clean = [task for task in finished if not task["attempts"]]
    return {
        "spec_id": spec_id,
        "revision": run["revision"],
        "replans": run.get("replans", 0),
        "counts": counts(run),
        "failed_attempts": failed,
        "retry_cost": round(failed / len(finished), 3) if finished else None,
        "first_pass_rate": round(len(clean) / len(finished), 3) if finished else None,
        "elapsed_seconds": _elapsed(tasks),
        "tasks": [
            {
                "id": task["id"],
                "state": task["state"],
                "attempts": task["attempts"],
                "started": task.get("started"),
                "completed": task.get("completed"),
                "code_paths": task.get("code_paths", []),
            }
            for task in tasks
        ],
    }


def _elapsed(tasks: list[dict[str, Any]]) -> int | None:
    stamps = [task.get(key) for task in tasks for key in ("started", "completed") if task.get(key)]
    if len(stamps) < 2:
        return None
    return int((datetime.fromisoformat(max(stamps)) - datetime.fromisoformat(min(stamps))).total_seconds())


def _current_run(directory: Path) -> dict[str, Any]:
    run = load_run(directory)
    if run["plan_digest"] != plan_digest(read_plan(directory)):
        raise ValueError("tasks.md changed since the run started; adopt it with `run replan`")
    return run


def _record_failure(
    directory: Path,
    run: dict[str, Any],
    task: dict[str, Any],
    result: dict[str, Any],
    settings: WorkflowSettings,
) -> dict[str, Any]:
    """A failed attempt must not reach the next task: no evidence, no handoff, no advance."""
    task["attempts"] += 1
    task["last_failure"] = _failure_summary(result)
    exhausted = task["attempts"] >= settings.task_max_attempts
    if exhausted:
        task["state"] = "blocked"
    save_run(directory, run)
    return {
        "spec_id": run["spec_id"],
        "task_id": task["id"],
        "passed": False,
        "attempts": task["attempts"],
        "max_attempts": settings.task_max_attempts,
        "blocked": exhausted,
        "verification": result["results"],
        "counts": counts(run),
    }


def _check_task_delivered(
    project_root: Path,
    task: dict[str, Any],
    code_paths: list[str],
    test_paths: list[str],
    allow_no_change: bool,
) -> None:
    """Scope verification can pass without the task having been done; the declared paths must move."""
    declared = list(code_paths) + list(test_paths)
    if not declared:
        if allow_no_change:
            return
        raise ValueError(
            f"{task['id']} needs --code (and usually --test) naming what it changed, "
            "or --allow-no-change for a task that legitimately edits nothing"
        )
    missing = [relative for relative in declared if not (project_root / relative).is_file()]
    if missing:
        raise ValueError(f"{task['id']} declares files that do not exist: " + ", ".join(missing))
    if allow_no_change:
        return
    stale = unchanged_since(project_root, task.get("baseline"), declared)
    if stale:
        raise ValueError(f"{task['id']} declares files unchanged since it started: " + ", ".join(stale))


def _trace(
    project_root: Path,
    spec_id: str,
    task: dict[str, Any],
    evidence: list[str],
    code_paths: list[str],
    test_paths: list[str],
) -> str | None:
    if not (task["requirement_id"] and code_paths and test_paths):
        return None
    link_requirement(
        project_root, spec_id, task["requirement_id"], [task["id"]], code_paths, test_paths, evidence
    )
    return task["requirement_id"]


def _failure_summary(result: dict[str, Any]) -> str:
    failed = [item for item in result["results"] if not item["passed"]]
    return "; ".join(f"{item.get('scope', 'project')}: {item['command']}" for item in failed)


def _verification(project_root: Path, spec: dict[str, Any]) -> list[dict[str, str]]:
    paths = scope_paths(project_root, list(spec.get("scope_ids", [])))
    return analyze_impact(project_root, paths)["verification"] if paths else []


def _brief(
    project_root: Path,
    directory: Path,
    spec: dict[str, Any],
    run: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    settings = load_workflow_settings(project_root)
    paths = scope_paths(project_root, list(spec.get("scope_ids", [])))
    impact = analyze_impact(project_root, paths) if paths else None
    return {
        "spec_id": spec["id"],
        "spec_title": spec["title"],
        "revision": run["revision"],
        "task": {key: task[key] for key in ("id", "requirement_id", "title", "state")},
        "requirement": _requirement(directory, spec, task["requirement_id"]),
        "context": _context(project_root, paths),
        "verification": impact["verification"] if impact else [],
        "attempt": task["attempts"] + 1,
        "max_attempts": settings.task_max_attempts,
        "last_failure": task["last_failure"],
        "handoff": _read_handoff(project_root, settings),
        "remaining": counts(run)["pending"],
        "done": False,
    }


def _context(project_root: Path, paths: list[str]) -> list[str]:
    context = project_context(project_root)
    for path in paths:
        context.extend(resolve_route(project_root, path)["context"])
    return list(dict.fromkeys(context))


def _requirement(
    directory: Path, spec: dict[str, Any], requirement_id: str | None
) -> dict[str, Any] | None:
    if not requirement_id:
        return None
    for requirement in load_spec_requirements(directory, spec):
        if requirement.get("id") == requirement_id:
            return requirement
    return None


def _handoff_file(project_root: Path, settings: WorkflowSettings) -> Path:
    return PATHS.agent_root(project_root) / settings.handoff_path


def _read_handoff(project_root: Path, settings: WorkflowSettings) -> str | None:
    path = _handoff_file(project_root, settings)
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    return content if "status: active" in content.lower() else None


def _write_handoff(project_root: Path, settings: WorkflowSettings, handoff: str) -> str:
    lines = handoff.splitlines()
    if len(lines) > settings.handoff_max_lines:
        raise ValueError(f"Handoff has {len(lines)} lines; maximum is {settings.handoff_max_lines}")
    if len(handoff) > settings.handoff_max_characters:
        raise ValueError(
            f"Handoff has {len(handoff)} characters; maximum is {settings.handoff_max_characters}"
        )
    path = _handoff_file(project_root, settings)
    path.write_text(f"Status: active\n\n{handoff.strip()}\n", encoding="utf-8")
    return path.relative_to(project_root).as_posix()
