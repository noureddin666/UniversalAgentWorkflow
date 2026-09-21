from __future__ import annotations

import json
import re
import subprocess
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from tooling.workflow_config import PATHS, SCHEMA_VERSION
from tooling.workflow_features.findings import load_findings


SCOPE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _config_path(project_root: Path) -> Path:
    return PATHS.agent_root(project_root) / PATHS.scopes_config


def _load_config(project_root: Path) -> dict[str, Any]:
    path = _config_path(project_root)
    if not path.is_file():
        raise FileNotFoundError(f"Scopes config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_path(value: str) -> str:
    normalized = PurePosixPath(value.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"Scope paths must be project-relative: {value}")
    return normalized.as_posix().strip("/")


def _is_same_or_child(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _scope_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {scope["id"]: scope for scope in config.get("scopes", []) if scope.get("id")}


def validate_routing(project_root: Path) -> list[str]:
    try:
        config = _load_config(project_root)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return [str(error)]
    errors: list[str] = []
    scopes = config.get("scopes", [])
    if config.get("schema_version") != SCHEMA_VERSION:
        errors.append("Scopes config requires migration")
    by_id = _scope_map(config)
    if len(by_id) != len(scopes):
        errors.append("Scope ids must be present and unique")
    normalized_paths: dict[str, list[str]] = {}
    for scope in scopes:
        scope_id = scope.get("id", "")
        if not SCOPE_ID_PATTERN.fullmatch(scope_id):
            errors.append(f"Invalid scope id: {scope_id!r}")
        parent = scope.get("parent")
        if parent and parent not in by_id:
            errors.append(f"{scope_id}: unknown parent {parent}")
        for dependency in scope.get("depends_on", []):
            if dependency not in by_id:
                errors.append(f"{scope_id}: unknown dependency {dependency}")
            if dependency == scope_id:
                errors.append(f"{scope_id}: scope may not depend on itself")
        for verification in scope.get("verification", []):
            if not verification.get("operation") or not verification.get("command"):
                errors.append(f"{scope_id}: verification requires operation and command")
        for value in scope.get("paths", []):
            try:
                path = _normalize_path(value)
                normalized_paths.setdefault(path, []).append(scope_id)
            except ValueError as error:
                errors.append(str(error))
        for reference in scope.get("context", []):
            try:
                relative = _normalize_path(reference)
                if not (project_root / relative).is_file():
                    errors.append(f"{scope_id}: missing context {reference}")
            except ValueError as error:
                errors.append(str(error))
    for path, owners in normalized_paths.items():
        if len(owners) > 1:
            errors.append(f"Path {path} has multiple owners: {', '.join(owners)}")
    for scope_id in by_id:
        visited: set[str] = set()
        current = scope_id
        while current:
            if current in visited:
                errors.append(f"Scope hierarchy contains a cycle at {current}")
                break
            visited.add(current)
            current = by_id.get(current, {}).get("parent")
    path_owners = [(path, owners[0]) for path, owners in normalized_paths.items() if len(owners) == 1]
    for index, (left_path, left_owner) in enumerate(path_owners):
        for right_path, right_owner in path_owners[index + 1 :]:
            if _is_same_or_child(left_path, right_path) or _is_same_or_child(right_path, left_path):
                if not _related(by_id, left_owner, right_owner):
                    errors.append(
                        f"Overlapping paths require parent/child scopes: {left_owner} ({left_path}), "
                        f"{right_owner} ({right_path})"
                    )
    return sorted(set(errors))


def _related(by_id: dict[str, dict[str, Any]], left: str, right: str) -> bool:
    def ancestors(scope_id: str) -> set[str]:
        result: set[str] = set()
        current = scope_id
        while current and current not in result:
            result.add(current)
            current = by_id.get(current, {}).get("parent")
        return result

    return left in ancestors(right) or right in ancestors(left)


def _chain(by_id: dict[str, dict[str, Any]], scope_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current = scope_id
    while current:
        scope = by_id[current]
        result.append(scope)
        current = scope.get("parent")
    return list(reversed(result))


def _specs(project_root: Path) -> list[dict[str, Any]]:
    root = PATHS.agent_root(project_root) / PATHS.specs_directory
    result = []
    for path in sorted(root.glob("*/spec.json")):
        result.append(json.loads(path.read_text(encoding="utf-8")))
    return result


def build_index(project_root: Path) -> dict[str, Any]:
    errors = validate_routing(project_root)
    if errors:
        raise ValueError("Routing is not valid:\n" + "\n".join(errors))
    config = _load_config(project_root)
    specs = _specs(project_root)
    findings = load_findings(project_root)
    source = {
        "project": config.get("project", {}),
        "scopes": config.get("scopes", []),
        "specs": [
            {
                "id": spec.get("id"),
                "title": spec.get("title"),
                "status": spec.get("status"),
                "scope_ids": spec.get("scope_ids", []),
            }
            for spec in specs
        ],
        "findings": findings,
    }
    digest = sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()
    index = {"source_digest": digest, **source}
    agent_root = PATHS.agent_root(project_root)
    (agent_root / PATHS.project_index).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    lines = ["# Project index", "", "## Scopes", ""]
    for scope in index["scopes"]:
        parent = f"; parent: `{scope['parent']}`" if scope.get("parent") else ""
        paths = ", ".join(f"`{path}`" for path in scope.get("paths", [])) or "No owned paths"
        lines.append(f"- `{scope['id']}`: {paths}{parent}")
    lines.extend(["", "## Specs", ""])
    for spec in index["specs"]:
        scopes = ", ".join(f"`{scope}`" for scope in spec["scope_ids"]) or "project-wide"
        lines.append(f"- `{spec['id']}` — {spec['title']} ({spec['status']}); {scopes}")
    (agent_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for scope in index["scopes"]:
        scope_id = scope["id"]
        scope_directory = agent_root / "scopes" / scope_id
        scope_directory.mkdir(parents=True, exist_ok=True)
        scope_index = {
            "scope": scope,
            "children": [item["id"] for item in index["scopes"] if item.get("parent") == scope_id],
            "specs": [item for item in index["specs"] if scope_id in item["scope_ids"]],
            "findings": [item for item in findings if scope_id in item.get("scope_ids", [])],
        }
        (scope_directory / "INDEX.json").write_text(
            json.dumps(scope_index, indent=2) + "\n", encoding="utf-8"
        )
        scope_lines = [f"# {scope.get('title', scope_id)} scope index", "", "## Owned paths", ""]
        scope_lines.extend(f"- `{path}`" for path in scope.get("paths", []))
        scope_lines.extend(["", "## Child scopes", ""])
        scope_lines.extend(f"- `{child}`" for child in scope_index["children"])
        scope_lines.extend(["", "## Specs", ""])
        scope_lines.extend(
            f"- `{spec['id']}` — {spec['title']} ({spec['status']})" for spec in scope_index["specs"]
        )
        scope_lines.extend(["", "## Bugs and discoveries", ""])
        scope_lines.extend(
            f"- `{finding['id']}` — {finding['title']} ({finding['status']})"
            for finding in scope_index["findings"]
        )
        (scope_directory / "INDEX.md").write_text("\n".join(scope_lines) + "\n", encoding="utf-8")
    return index


def check_index(project_root: Path) -> str | None:
    path = PATHS.agent_root(project_root) / PATHS.project_index
    if not path.is_file():
        return "Project index is missing; run build-index"
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
        config = _load_config(project_root)
        source = {
            "project": config.get("project", {}),
            "scopes": config.get("scopes", []),
            "specs": [
                {
                    "id": spec.get("id"),
                    "title": spec.get("title"),
                    "status": spec.get("status"),
                    "scope_ids": spec.get("scope_ids", []),
                }
                for spec in _specs(project_root)
            ],
            "findings": load_findings(project_root),
        }
        digest = sha256(json.dumps(source, sort_keys=True).encode("utf-8")).hexdigest()
        if index.get("source_digest") != digest:
            return "Project index is stale; run build-index"
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return f"Project index is invalid: {error}"


def resolve_route(
    project_root: Path, requested_path: str, intent: str | None = None
) -> dict[str, Any]:
    errors = validate_routing(project_root)
    if errors:
        raise ValueError("Routing is not valid:\n" + "\n".join(errors))
    config = _load_config(project_root)
    by_id = _scope_map(config)
    path = _normalize_path(requested_path)
    matches: list[tuple[int, str]] = []
    for scope in config.get("scopes", []):
        for owned_path in scope.get("paths", []):
            normalized = _normalize_path(owned_path)
            if _is_same_or_child(path, normalized):
                matches.append((len(PurePosixPath(normalized).parts), scope["id"]))
    scope_chain = _chain(by_id, max(matches)[1]) if matches else []
    scope_ids = [scope["id"] for scope in scope_chain]
    context = list(config.get("project", {}).get("context", []))
    for scope in scope_chain:
        context.extend(scope.get("context", []))
    context = list(dict.fromkeys(context))
    applicable_specs = [
        spec["id"]
        for spec in _specs(project_root)
        if not spec.get("scope_ids") or set(spec.get("scope_ids", [])) & set(scope_ids)
    ]
    applicable_findings = [
        finding["id"]
        for finding in load_findings(project_root)
        if set(finding.get("scope_ids", [])) & set(scope_ids)
        or set(finding.get("spec_ids", [])) & set(applicable_specs)
    ]
    return {
        "path": path,
        "intent": intent,
        "workflow": (
            f".agent/vendor/universal-agent-workflow/workflows/{intent}.md" if intent else None
        ),
        "scope_chain": scope_ids,
        "context": context,
        "specs": applicable_specs,
        "findings": applicable_findings,
    }


def scope_paths(project_root: Path, scope_ids: list[str]) -> list[str]:
    config = _load_config(project_root)
    by_id = _scope_map(config)
    unknown = sorted(set(scope_ids) - set(by_id))
    if unknown:
        raise ValueError("Unknown scopes: " + ", ".join(unknown))
    paths: list[str] = []
    for scope_id in scope_ids:
        paths.extend(_normalize_path(path) for path in by_id[scope_id].get("paths", []))
    return list(dict.fromkeys(paths))


def project_context(project_root: Path) -> list[str]:
    return list(_load_config(project_root).get("project", {}).get("context", []))


def analyze_impact(project_root: Path, paths: list[str]) -> dict[str, Any]:
    config = _load_config(project_root)
    by_id = _scope_map(config)
    routes = [resolve_route(project_root, path) for path in paths]
    direct = {scope_id for route in routes for scope_id in route["scope_chain"]}
    impacted = set(direct)
    changed = True
    while changed:
        changed = False
        for scope in config.get("scopes", []):
            if scope["id"] not in impacted and set(scope.get("depends_on", [])) & impacted:
                impacted.add(scope["id"])
                changed = True
    verification: list[dict[str, str]] = []
    for scope_id in sorted(impacted):
        for item in by_id.get(scope_id, {}).get("verification", []):
            verification.append({"scope": scope_id, **item})
    specs = sorted({spec for route in routes for spec in route["specs"]})
    findings = sorted({finding for route in routes for finding in route["findings"]})
    return {
        "changed_paths": paths,
        "direct_scopes": sorted(direct),
        "impacted_scopes": sorted(impacted),
        "cross_scope": len(direct) > 1,
        "specs": specs,
        "findings": findings,
        "verification": verification,
    }


def resolve_git_changes(project_root: Path, base: str | None = None) -> dict[str, Any]:
    commands = [
        ["git", "diff", "--name-only", "--find-renames"],
        ["git", "diff", "--cached", "--name-only", "--find-renames"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    if base:
        commands.append(["git", "diff", "--name-only", "--find-renames", f"{base}...HEAD"])
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=project_root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "Unable to read Git changes")
        paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return analyze_impact(project_root, sorted(paths))
