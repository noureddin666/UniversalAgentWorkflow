from __future__ import annotations

import json
import re
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from tooling.workflow_config import (
    DEFAULT_WORKFLOW_SETTINGS,
    PATHS,
    PLACEHOLDER_MARKER,
    SCHEMA_VERSION,
    SPEC_STATES,
    TRANSITIONS,
    WorkflowSettings,
    load_workflow_settings,
)


SPEC_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIREMENT_ID_PATTERN = re.compile(r"^REQ-[0-9]{3,}$")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _spec_directory(project_root: Path, spec_id: str) -> Path:
    return PATHS.agent_root(project_root) / PATHS.specs_directory / spec_id


def _load_spec(project_root: Path, spec_id: str) -> tuple[Path, dict[str, Any]]:
    directory = _spec_directory(project_root, spec_id)
    manifest = directory / "spec.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"Spec not found: {spec_id}")
    return directory, json.loads(manifest.read_text(encoding="utf-8"))


def load_spec(project_root: Path, spec_id: str) -> tuple[Path, dict[str, Any]]:
    return _load_spec(project_root, spec_id)


def create_spec(
    project_root: Path,
    spec_id: str,
    title: str,
    owner: str,
    scope_ids: list[str] | None = None,
) -> Path:
    if not SPEC_ID_PATTERN.fullmatch(spec_id):
        raise ValueError("Spec id must use lowercase kebab-case")
    directory = _spec_directory(project_root, spec_id)
    if directory.exists():
        raise FileExistsError(f"Spec already exists: {spec_id}")
    directory.mkdir(parents=True)
    today = date.today().isoformat()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "id": spec_id,
        "title": title,
        "status": "Proposed",
        "owner": owner,
        "updated": today,
        "approvals": [],
        "scope_ids": scope_ids or [],
        "requirements": [
            {
                "id": "REQ-001",
                "statement": "TODO",
                "acceptance_evidence": ["TODO"],
            }
        ],
        "requirement_files": [],
        "scope": {"in": ["TODO"], "out": ["TODO"]},
        "assumptions": [],
        "open_decisions": [],
    }
    _write_json(directory / "spec.json", manifest)
    (directory / "spec.md").write_text(
        f"# {title}\n\n- Spec: `{spec_id}`\n- Status: Proposed\n- Owner: {owner}\n"
        f"- Updated: {today}\n\n## Outcome\n\nTODO\n\n## Context\n\nTODO\n",
        encoding="utf-8",
    )
    _write_json(
        directory / "traceability.json",
        {"schema_version": SCHEMA_VERSION, "spec_id": spec_id, "links": []},
    )
    generate_plan(project_root, spec_id)
    generate_tasks(project_root, spec_id)
    return directory


def generate_plan(project_root: Path, spec_id: str) -> Path:
    directory, spec = _load_spec(project_root, spec_id)
    items = load_spec_requirements(directory, spec)
    requirements = "\n".join(f"- [ ] {item['id']}: {item['statement']}" for item in items)
    digest = _requirements_digest(items)
    path = directory / "plan.md"
    path.write_text(
        f"# Implementation plan: {spec['title']}\n\n<!-- requirements-digest: {digest} -->\n\n"
        f"## Requirement coverage\n\n{requirements}\n\n"
        "## Impact\n\n- Behavior: TODO\n- Data: TODO\n- APIs: TODO\n- Operations: TODO\n"
        "- Documentation: TODO\n\n## Delivery slices\n\n1. TODO\n\n## Verification\n\n- TODO\n",
        encoding="utf-8",
    )
    return path


def generate_tasks(project_root: Path, spec_id: str) -> Path:
    directory, spec = _load_spec(project_root, spec_id)
    items = load_spec_requirements(directory, spec)
    tasks = []
    for index, requirement in enumerate(items, start=1):
        tasks.append(f"- [ ] TASK-{index:03d} `{requirement['id']}` TODO")
    path = directory / "tasks.md"
    digest = _requirements_digest(items)
    path.write_text(
        f"# Tasks: {spec['title']}\n\n<!-- requirements-digest: {digest} -->\n\n"
        + "\n".join(tasks)
        + "\n",
        encoding="utf-8",
    )
    return path


def transition_spec(project_root: Path, spec_id: str, target: str, actor: str, evidence: list[str]) -> None:
    directory, spec = _load_spec(project_root, spec_id)
    current = spec.get("status")
    if target not in SPEC_STATES:
        raise ValueError(f"Unknown state: {target}")
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid transition: {current} -> {target}")
    settings = load_workflow_settings(project_root)
    candidate = {**spec, "status": target}
    errors = validate_spec(directory, candidate, settings=settings, include_metadata_drift=False)
    if target in settings.require_approval_for and errors:
        raise ValueError("Spec is not valid:\n" + "\n".join(errors))
    if target == "Implemented" and not evidence:
        raise ValueError("Implemented requires at least one verification evidence reference")
    spec["status"] = target
    spec["updated"] = date.today().isoformat()
    spec.setdefault("approvals", []).append(
        {"state": target, "actor": actor, "date": spec["updated"], "evidence": evidence}
    )
    _write_json(directory / "spec.json", spec)
    _sync_spec_metadata(directory, spec)


def validate_spec(
    directory: Path,
    spec: dict[str, Any],
    known_scopes: set[str] | None = None,
    settings: WorkflowSettings = DEFAULT_WORKFLOW_SETTINGS,
    include_metadata_drift: bool = True,
) -> list[str]:
    errors = _structure_errors(directory, spec, known_scopes)
    try:
        requirements = load_spec_requirements(directory, spec)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        errors.append(f"{directory.name}: invalid requirement file: {error}")
        requirements = spec.get("requirements", [])
    errors.extend(_digest_errors(directory, requirements))
    errors.extend(_identity_errors(directory, requirements))
    status = spec.get("status")
    if status in settings.require_approval_for:
        errors.extend(_completeness_errors(directory, requirements))
        errors.extend(_scope_statement_errors(directory, spec))
        errors.extend(_uncertainty_errors(directory, spec))
    errors.extend(_artifact_errors(directory))
    if include_metadata_drift:
        errors.extend(_metadata_drift_errors(directory, spec))
    if status == "Implemented" and settings.require_traceability_for_implemented:
        errors.extend(_traceability_errors(directory, requirements))
    return errors


def _structure_errors(
    directory: Path, spec: dict[str, Any], known_scopes: set[str] | None
) -> list[str]:
    errors: list[str] = []
    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{directory.name}: spec requires migration")
    for field in ("id", "title", "status", "owner", "requirements", "scope"):
        if not spec.get(field):
            errors.append(f"{directory.name}: missing {field}")
    if spec.get("status") not in SPEC_STATES:
        errors.append(f"{directory.name}: invalid status")
    if known_scopes is not None:
        for scope_id in spec.get("scope_ids", []):
            if scope_id not in known_scopes:
                errors.append(f"{directory.name}: unknown scope {scope_id}")
    return errors


def _digest_errors(directory: Path, requirements: list[dict[str, Any]]) -> list[str]:
    digest = _requirements_digest(requirements)
    errors = []
    for filename in ("plan.md", "tasks.md"):
        artifact = directory / filename
        if artifact.is_file() and f"requirements-digest: {digest}" not in artifact.read_text(encoding="utf-8"):
            errors.append(f"{directory.name}: stale {filename}; regenerate it")
    return errors


def _identity_errors(directory: Path, requirements: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        requirement_id = requirement.get("id", "")
        if not REQUIREMENT_ID_PATTERN.fullmatch(requirement_id):
            errors.append(f"{directory.name}: invalid requirement id {requirement_id!r}")
        if requirement_id in seen:
            errors.append(f"{directory.name}: duplicate requirement {requirement_id}")
        seen.add(requirement_id)
    return errors


def _completeness_errors(directory: Path, requirements: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for requirement in requirements:
        requirement_id = requirement.get("id", "")
        if requirement.get("statement") in {None, "", "TODO"}:
            errors.append(f"{directory.name}/{requirement_id}: missing statement")
        evidence = requirement.get("acceptance_evidence", [])
        if not evidence or any(item == "TODO" for item in evidence):
            errors.append(f"{directory.name}/{requirement_id}: missing acceptance evidence")
    return errors


def _scope_statement_errors(directory: Path, spec: dict[str, Any]) -> list[str]:
    scope = spec.get("scope") or {}
    errors = []
    for side in ("in", "out"):
        values = [str(value).strip() for value in scope.get(side, []) if str(value).strip()]
        if not values or any(value == PLACEHOLDER_MARKER for value in values):
            errors.append(f"{directory.name}: scope '{side}' is not defined")
    return errors


def _uncertainty_errors(directory: Path, spec: dict[str, Any]) -> list[str]:
    """An accepted spec may carry assumptions, but never unowned ones or unresolved decisions."""
    errors: list[str] = []
    for index, assumption in enumerate(spec.get("assumptions", []), start=1):
        label = f"assumption {index}"
        if not isinstance(assumption, dict):
            errors.append(f"{directory.name}/{label}: must be an object with statement, owner or validation, and consequence")
            continue
        if not _filled(assumption.get("statement")):
            errors.append(f"{directory.name}/{label}: missing statement")
        if not _filled(assumption.get("owner")) and not _filled(assumption.get("validation")):
            errors.append(f"{directory.name}/{label}: needs an owner or a validation method")
        if not _filled(assumption.get("consequence")):
            errors.append(f"{directory.name}/{label}: needs a consequence if false")
    for index, decision in enumerate(spec.get("open_decisions", []), start=1):
        label = f"open decision {index}"
        if not isinstance(decision, dict):
            errors.append(f"{directory.name}/{label}: must be an object with question, impact, and resolution")
            continue
        if not _filled(decision.get("question")):
            errors.append(f"{directory.name}/{label}: missing question")
        if not _filled(decision.get("resolution")):
            errors.append(
                f"{directory.name}/{label}: unresolved; record a resolution or move the spec to Blocked"
            )
    return errors


def _filled(value: Any) -> bool:
    return bool(value) and str(value).strip() not in {"", PLACEHOLDER_MARKER}


def _artifact_errors(directory: Path) -> list[str]:
    return [
        f"{directory.name}: missing {filename}"
        for filename in ("spec.md", "plan.md", "tasks.md", "traceability.json")
        if not (directory / filename).is_file()
    ]


def _metadata_drift_errors(directory: Path, spec: dict[str, Any]) -> list[str]:
    path = directory / "spec.md"
    if not path.is_file():
        return []
    markdown = path.read_text(encoding="utf-8")
    expected = (
        f"# {spec.get('title')}\n",
        f"- Status: {spec.get('status')}\n",
        f"- Owner: {spec.get('owner')}\n",
        f"- Updated: {spec.get('updated')}\n",
    )
    if any(value not in markdown for value in expected):
        return [f"{directory.name}: spec.md metadata is stale; run sync-spec"]
    return []


def _traceability_errors(directory: Path, requirements: list[dict[str, Any]]) -> list[str]:
    path = directory / "traceability.json"
    if not path.is_file():
        return []
    try:
        trace = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return [f"{directory.name}: invalid traceability.json: {error}"]
    linked = {
        item.get("requirement_id")
        for item in trace.get("links", [])
        if _complete_link(directory, item)
    }
    required = {requirement.get("id", "") for requirement in requirements}
    return [
        f"{directory.name}/{requirement_id}: incomplete traceability"
        for requirement_id in sorted(required - linked)
    ]


def load_spec_requirements(directory: Path, spec: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = list(spec.get("requirements", []))
    for relative in spec.get("requirement_files", []):
        path = directory / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(bundle.get("requirements"), list):
            raise ValueError(f"{relative} must contain a requirements array")
        requirements.extend(bundle["requirements"])
    return requirements


def _requirements_digest(requirements: list[dict[str, Any]]) -> str:
    return sha256(json.dumps(requirements, sort_keys=True).encode("utf-8")).hexdigest()


def _sync_spec_metadata(directory: Path, spec: dict[str, Any]) -> Path:
    path = directory / "spec.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing spec.md: {directory.name}")
    lines = path.read_text(encoding="utf-8").splitlines()
    replacements = {
        "# ": f"# {spec['title']}",
        "- Spec: ": f"- Spec: `{spec['id']}`",
        "- Status: ": f"- Status: {spec['status']}",
        "- Owner: ": f"- Owner: {spec['owner']}",
        "- Updated: ": f"- Updated: {spec['updated']}",
    }
    for index, line in enumerate(lines):
        for prefix, replacement in replacements.items():
            if line.startswith(prefix):
                lines[index] = replacement
                break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def sync_spec(project_root: Path, spec_id: str) -> Path:
    directory, spec = _load_spec(project_root, spec_id)
    return _sync_spec_metadata(directory, spec)


def link_requirement(
    project_root: Path,
    spec_id: str,
    requirement_id: str,
    task_ids: list[str],
    code_paths: list[str],
    test_paths: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    directory, spec = _load_spec(project_root, spec_id)
    known = {item.get("id") for item in load_spec_requirements(directory, spec)}
    if requirement_id not in known:
        raise ValueError(f"Unknown requirement in {spec_id}: {requirement_id}")
    tasks_path = directory / "tasks.md"
    tasks = tasks_path.read_text(encoding="utf-8") if tasks_path.is_file() else ""
    rejected = [f"{task_id} does not appear in tasks.md" for task_id in task_ids if task_id not in tasks]
    rejected.extend(
        f"file does not exist: {relative}"
        for relative in list(code_paths) + list(test_paths)
        if not (project_root / relative).is_file()
    )
    if rejected:
        raise ValueError("Cannot link requirement:\n" + "\n".join(rejected))
    trace_path = directory / "traceability.json"
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    else:
        trace = {"schema_version": SCHEMA_VERSION, "spec_id": spec_id, "links": []}
    links = trace.setdefault("links", [])
    link = next((item for item in links if item.get("requirement_id") == requirement_id), None)
    if link is None:
        link = {"requirement_id": requirement_id}
        links.append(link)
    for key, values in (
        ("task_ids", task_ids),
        ("code_paths", code_paths),
        ("test_paths", test_paths),
        ("evidence", evidence),
    ):
        link[key] = list(dict.fromkeys(list(link.get(key, [])) + list(values)))
    links.sort(key=lambda item: str(item.get("requirement_id", "")))
    _write_json(trace_path, trace)
    missing = [key for key in ("task_ids", "code_paths", "test_paths", "evidence") if not link.get(key)]
    return {
        "path": trace_path.relative_to(project_root).as_posix(),
        "requirement_id": requirement_id,
        "link": link,
        "complete": not missing,
        "missing": missing,
    }


def add_requirement_set(project_root: Path, spec_id: str, set_id: str, title: str) -> Path:
    if not SPEC_ID_PATTERN.fullmatch(set_id):
        raise ValueError("Requirement set id must use lowercase kebab-case")
    directory, spec = _load_spec(project_root, spec_id)
    requirements_directory = directory / "requirements"
    requirements_directory.mkdir(exist_ok=True)
    relative = f"requirements/{set_id}.json"
    path = directory / relative
    if path.exists():
        raise FileExistsError(f"Requirement set already exists: {set_id}")
    numeric_ids = [
        int(match.group(1))
        for requirement in load_spec_requirements(directory, spec)
        if (match := re.fullmatch(r"REQ-([0-9]+)", requirement.get("id", "")))
    ]
    next_id = max(numeric_ids, default=0) + 1
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "id": set_id,
        "title": title,
        "requirements": [
            {"id": f"REQ-{next_id:03d}", "statement": "TODO", "acceptance_evidence": ["TODO"]}
        ],
    }
    _write_json(path, bundle)
    spec.setdefault("requirement_files", []).append(relative)
    _write_json(directory / "spec.json", spec)
    return path


def _complete_link(directory: Path, link: dict[str, Any]) -> bool:
    task_ids = link.get("task_ids", [])
    code_paths = link.get("code_paths", [])
    test_paths = link.get("test_paths", [])
    tasks = (directory / "tasks.md").read_text(encoding="utf-8") if (directory / "tasks.md").is_file() else ""
    project_root = directory.parents[2]
    return bool(
        link.get("requirement_id")
        and task_ids
        and all(task_id in tasks for task_id in task_ids)
        and code_paths
        and all((project_root / path).is_file() for path in code_paths)
        and test_paths
        and all((project_root / path).is_file() for path in test_paths)
        and link.get("evidence")
    )


def validate_specs(project_root: Path) -> list[str]:
    root = PATHS.agent_root(project_root) / PATHS.specs_directory
    if not root.is_dir():
        return []
    errors: list[str] = []
    settings = load_workflow_settings(project_root)
    scopes_path = PATHS.agent_root(project_root) / PATHS.scopes_config
    known_scopes: set[str] | None = None
    if scopes_path.is_file():
        try:
            scopes_config = json.loads(scopes_path.read_text(encoding="utf-8"))
            known_scopes = {scope["id"] for scope in scopes_config.get("scopes", []) if scope.get("id")}
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            errors.append(f"Invalid scopes config: {error}")
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest = directory / "spec.json"
        if not manifest.is_file():
            errors.append(f"{directory.name}: missing spec.json")
            continue
        try:
            spec = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            errors.append(f"{directory.name}: invalid spec.json: {error}")
            continue
        errors.extend(validate_spec(directory, spec, known_scopes, settings))
    return errors
