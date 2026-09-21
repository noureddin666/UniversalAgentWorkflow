from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tooling.workflow_config import (
    DEFAULT_IGNORED_DIRECTORIES,
    SOURCE_SUFFIXES,
    OnboardingSettings,
)
from tooling.workflow_features.onboarding.model import EcosystemFinding, ModuleCandidate, ScopeCandidate
from tooling.workflow_features.onboarding.signals import (
    APPLICATION_DIRECTORY_NAMES,
    ECOSYSTEMS,
    FALLBACK_SOURCE_DIRECTORIES,
    LIBRARY_DIRECTORY_NAMES,
    MANIFEST_MARKERS,
)


NAME_PATTERN = re.compile(r"^\s*name\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
GO_MODULE_PATTERN = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)
NAMESPACE_PATTERN = re.compile(r"<RootNamespace>([^<]+)</RootNamespace>")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def relative(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def scan_directories(project_root: Path, settings: OnboardingSettings) -> list[Path]:
    """Depth-limited, ignore-aware directory list every other detector works from."""
    ignored = set(DEFAULT_IGNORED_DIRECTORIES)
    found = [project_root]
    frontier = [(project_root, 0)]
    while frontier:
        current, depth = frontier.pop()
        if depth >= settings.max_scan_depth:
            continue
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.name in ignored or entry.name.startswith("."):
                continue
            found.append(entry)
            frontier.append((entry, depth + 1))
    return sorted(set(found))


def match_marker(directory: Path, marker: str) -> Path | None:
    if "*" in marker:
        return next(iter(sorted(directory.glob(marker))), None)
    candidate = directory / marker
    return candidate if candidate.is_file() else None


def detect_ecosystems(project_root: Path, directories: list[Path]) -> list[EcosystemFinding]:
    found: dict[str, EcosystemFinding] = {}
    for directory in directories:
        for ecosystem in ECOSYSTEMS:
            if ecosystem.name in found:
                continue
            for marker in ecosystem.markers:
                match = match_marker(directory, marker)
                if not match:
                    continue
                manager = ""
                for lockfile, label in ecosystem.package_managers:
                    if (directory / lockfile).is_file():
                        manager = label
                        break
                found[ecosystem.name] = EcosystemFinding(
                    name=ecosystem.name,
                    profile=ecosystem.profile,
                    evidence=relative(project_root, match),
                    package_manager=manager,
                )
                break
    return [found[key] for key in sorted(found)]


def has_manifest(directory: Path) -> bool:
    return any(match_marker(directory, marker) for marker in MANIFEST_MARKERS)


def _slug(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "scope"


def _kind(directory: Path) -> str:
    parent = directory.parent.name
    if parent in LIBRARY_DIRECTORY_NAMES:
        return "library"
    if parent in APPLICATION_DIRECTORY_NAMES:
        return "application"
    scripts = read_json(directory / "package.json").get("scripts")
    if isinstance(scripts, dict) and any(name in scripts for name in ("dev", "start", "serve")):
        return "application"
    return "library"


def _source_count(directory: Path) -> int:
    ignored = set(DEFAULT_IGNORED_DIRECTORIES)
    count = 0
    for path in directory.rglob("*"):
        if path.suffix in SOURCE_SUFFIXES and path.is_file():
            if not any(part in ignored for part in path.parts):
                count += 1
    return count


def suggest_scopes(
    project_root: Path, directories: list[Path], settings: OnboardingSettings
) -> list[ScopeCandidate]:
    candidates: list[ScopeCandidate] = []
    for directory in directories:
        if directory == project_root or not has_manifest(directory):
            continue
        path = relative(project_root, directory)
        candidates.append(
            ScopeCandidate(
                scope_id=_slug(path),
                title=directory.name,
                kind=_kind(directory),
                path=path,
                evidence=f"{path} owns a manifest",
            )
        )
    if not candidates:
        candidates = _fallback_scopes(project_root, settings)
    return candidates[: settings.maximum_suggested_scopes]


def _fallback_scopes(project_root: Path, settings: OnboardingSettings) -> list[ScopeCandidate]:
    ignored = set(DEFAULT_IGNORED_DIRECTORIES)
    candidates: list[ScopeCandidate] = []
    try:
        entries = sorted(project_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir() or entry.name in ignored or entry.name.startswith("."):
            continue
        count = _source_count(entry)
        below_threshold = count < settings.minimum_directory_sources
        if not count or (below_threshold and entry.name not in FALLBACK_SOURCE_DIRECTORIES):
            continue
        path = relative(project_root, entry)
        candidates.append(
            ScopeCandidate(
                scope_id=_slug(path),
                title=entry.name,
                kind="application",
                path=path,
                evidence=f"{path} holds {count} source file(s) and no manifest",
            )
        )
    return candidates


def _import_prefixes(project_root: Path, directory: Path) -> tuple[tuple[str, ...], str]:
    location = relative(project_root, directory)
    name = read_json(directory / "package.json").get("name")
    if isinstance(name, str) and name:
        return (name,), f"{location}/package.json name"
    for manifest in ("pyproject.toml", "Cargo.toml"):
        match = NAME_PATTERN.search(read_text(directory / manifest))
        if match:
            return (match.group(1),), f"{location}/{manifest} name"
    match = GO_MODULE_PATTERN.search(read_text(directory / "go.mod"))
    if match:
        return (match.group(1),), f"{location}/go.mod module"
    project_file = next(iter(sorted(directory.glob("*.csproj"))), None)
    if project_file:
        namespace = NAMESPACE_PATTERN.search(read_text(project_file))
        prefix = namespace.group(1) if namespace else project_file.stem
        return (prefix,), relative(project_root, project_file)
    package = next(
        (child.name for child in sorted(directory.iterdir()) if (child / "__init__.py").is_file()),
        "",
    )
    if package:
        return (package,), f"{location}/{package}/__init__.py"
    return (), "no import prefix could be derived; declare one before enabling the gate"


def suggest_modules(
    project_root: Path, scopes: list[ScopeCandidate], settings: OnboardingSettings
) -> list[ModuleCandidate]:
    modules: list[ModuleCandidate] = []
    for scope in scopes[: settings.maximum_suggested_scopes]:
        directory = project_root / scope.path
        if not directory.is_dir():
            continue
        prefixes, evidence = _import_prefixes(project_root, directory)
        modules.append(
            ModuleCandidate(
                name=scope.scope_id,
                path=scope.path,
                import_prefixes=prefixes,
                evidence=evidence,
            )
        )
    return modules
