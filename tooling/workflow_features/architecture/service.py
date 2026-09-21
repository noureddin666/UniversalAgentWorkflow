from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tooling.workflow_config import (
    ADAPTER_MODES,
    DEFAULT_IGNORED_DIRECTORIES,
    PATHS,
    SCHEMA_VERSION,
    SOURCE_SUFFIXES,
    ArchitectureSettings,
)
from tooling.workflow_features.architecture.adapters import dotnet_violations, package_violations
from tooling.workflow_features.architecture.imports import extract_imports


@dataclass
class ArchitectureReport:
    """Separates 'no violations' from 'nothing was checked'."""

    status: str = "checked"
    violations: list[str] = field(default_factory=list)
    configuration_errors: list[str] = field(default_factory=list)
    modules_checked: int = 0
    files_scanned: int = 0

    @property
    def blocking(self) -> list[str]:
        return sorted(set(self.configuration_errors)) + sorted(set(self.violations))

    def summary(self) -> str:
        if self.status == "unconfigured":
            return (
                "No architecture rules configured: .agent/config/architecture.json declares no modules. "
                "This check passed because nothing was checked."
            )
        if self.status == "invalid":
            return "Architecture configuration could not be used; see the errors above."
        return (
            f"Checked {self.modules_checked} module(s) across {self.files_scanned} source file(s); "
            f"{len(self.violations)} violation(s)."
        )


def _load_config(project_root: Path) -> dict[str, Any]:
    path = PATHS.agent_root(project_root) / PATHS.architecture_config
    if not path.is_file():
        raise FileNotFoundError(f"Architecture config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _settings(config: dict[str, Any]) -> ArchitectureSettings:
    mode = config.get("adapter_mode", "auto")
    if mode not in ADAPTER_MODES:
        mode = "auto"
    ignored = config.get("ignored_directories")
    return ArchitectureSettings(
        adapter_mode=mode,
        ignored_directories=tuple(ignored) if ignored is not None else DEFAULT_IGNORED_DIRECTORIES,
    )


def _source_files(module_path: Path, ignored: tuple[str, ...]) -> list[Path]:
    ignored_names = set(ignored)
    found: list[Path] = []
    stack = [module_path]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            if entry.is_dir():
                if entry.name not in ignored_names:
                    stack.append(entry)
            elif entry.suffix.lower() in SOURCE_SUFFIXES:
                found.append(entry)
    return found


def check_architecture(project_root: Path) -> ArchitectureReport:
    config = _load_config(project_root)
    if config.get("schema_version") != SCHEMA_VERSION:
        return ArchitectureReport(status="invalid", configuration_errors=["Architecture config requires migration"])
    modules = config.get("modules", [])
    if not modules:
        return ArchitectureReport(status="unconfigured")
    settings = _settings(config)
    report = ArchitectureReport(modules_checked=len(modules))
    known = {module.get("name") for module in modules}
    for module in modules:
        name = module.get("name")
        if not name or not module.get("path"):
            report.configuration_errors.append("Every architecture module requires a name and a path")
            continue
        for dependency in module.get("may_depend_on", []):
            if dependency not in known:
                report.configuration_errors.append(f"{name}: unknown dependency {dependency}")
        module_path = project_root / module["path"]
        if not module_path.is_dir():
            report.configuration_errors.append(
                f"{name}: configured path does not exist: {module['path']}"
            )
            continue
        allowed = set(module.get("may_depend_on", [])) | {name}
        for path in _source_files(module_path, settings.ignored_directories):
            report.files_scanned += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(project_root).as_posix()
            for imported in extract_imports(text, path.suffix.lower()):
                for target in _targets(modules, imported):
                    if target not in allowed:
                        report.violations.append(
                            f"{relative}: {name} may not depend on {target} ({imported})"
                        )
    if settings.adapters_enabled:
        report.violations.extend(dotnet_violations(project_root, modules))
        report.violations.extend(package_violations(project_root, modules))
    report.violations = sorted(set(report.violations))
    report.configuration_errors = sorted(set(report.configuration_errors))
    return report


def _targets(modules: list[dict[str, Any]], imported: str) -> list[str]:
    return [
        module["name"]
        for module in modules
        if module.get("name")
        and any(imported.startswith(prefix) for prefix in module.get("import_prefixes", []))
    ]
