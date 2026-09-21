from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tooling.workflow_config import DEFAULT_IGNORED_DIRECTORIES


def _project_files(root: Path) -> list[Path]:
    ignored = set(DEFAULT_IGNORED_DIRECTORIES)
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            if entry.is_dir():
                if entry.name not in ignored:
                    stack.append(entry)
            elif entry.suffix.endswith("proj"):
                found.append(entry)
    return found


def dotnet_violations(project_root: Path, modules: list[dict[str, Any]]) -> list[str]:
    project_owners: dict[Path, str] = {}
    for module in modules:
        module_path = project_root / module["path"]
        if module_path.is_dir():
            for path in _project_files(module_path):
                project_owners[path.resolve()] = module["name"]
    violations = []
    for project, owner in project_owners.items():
        module = next(item for item in modules if item["name"] == owner)
        allowed = set(module.get("may_depend_on", [])) | {owner}
        location = project.relative_to(project_root).as_posix()
        try:
            root = ElementTree.parse(project).getroot()
        except ElementTree.ParseError as error:
            violations.append(f"{location}: invalid project XML: {error}")
            continue
        for reference in root.findall(".//ProjectReference"):
            include = reference.get("Include")
            if not include:
                continue
            target_path = (project.parent / include.replace("\\", "/")).resolve()
            target = project_owners.get(target_path)
            if target and target not in allowed:
                violations.append(f"{location}: {owner} may not reference {target} ({include})")
    return violations


def package_violations(project_root: Path, modules: list[dict[str, Any]]) -> list[str]:
    packages: dict[str, tuple[Path, str]] = {}
    for module in modules:
        path = project_root / module["path"] / "package.json"
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("name"):
                packages[value["name"]] = (path, module["name"])
    violations = []
    for path, owner in packages.values():
        value = json.loads(path.read_text(encoding="utf-8"))
        dependencies: set[str] = set()
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            dependencies.update(value.get(field, {}))
        module = next(item for item in modules if item["name"] == owner)
        allowed = set(module.get("may_depend_on", [])) | {owner}
        location = path.relative_to(project_root).as_posix()
        for dependency in dependencies:
            target = packages.get(dependency)
            if target and target[1] not in allowed:
                violations.append(f"{location}: {owner} may not depend on {target[1]} ({dependency})")
    return violations
