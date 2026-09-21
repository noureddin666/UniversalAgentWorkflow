from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from tooling.workflow_config import DEFAULT_IGNORED_DIRECTORIES, SOURCE_SUFFIXES, OnboardingSettings
from tooling.workflow_features.onboarding.detection import read_text, relative
from tooling.workflow_features.onboarding.manifests import Manifest, matches
from tooling.workflow_features.onboarding.model import (
    COMPATIBILITY,
    DEPLOYMENT,
    DOCUMENTATION_PATHS,
    EXTERNAL_SYSTEMS,
    FROM_DOCUMENTATION,
    FROM_LAYOUT,
    FROM_MANIFEST,
    PROTECTED_PATHS,
    PUBLIC_CONTRACTS,
    PURPOSE,
    SOURCE_PATHS,
    SYSTEM_SHAPE,
    TEST_PATHS,
    FactCandidate,
)
from tooling.workflow_features.onboarding.signals import (
    CONTRACT_PATTERNS,
    DEPLOYMENT_MARKERS,
    DEPLOYMENT_NAME_HINTS,
    DEPLOYMENT_SCRIPT_PATTERNS,
    DEPLOYMENT_SCRIPT_SUFFIXES,
    DOCUMENTATION_DIRECTORIES,
    DOCUMENTATION_FILES,
    EXTERNAL_SYSTEM_PACKAGES,
    FALLBACK_SOURCE_DIRECTORIES,
    FRAMEWORK_PACKAGES,
    FRAMEWORK_SUBSUMES,
    PROTECTED_DIRECTORY_NAMES,
    PROTECTED_PATH_MARKERS,
    README_BOILERPLATE,
    TEST_DIRECTORY_NAMES,
    TEST_FILE_PATTERNS,
    TEST_PROJECT_SUFFIXES,
)


NONE_FOUND = "none found"
MAJOR_VERSION = re.compile(r"(\d+)")
MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MARKDOWN_EMPHASIS = re.compile(r"[*_`]+")
PROSE_START = re.compile(r"^[^\s#!<>|\-*+=`\[\d]")


def walk_files(project_root: Path) -> list[Path]:
    ignored = set(DEFAULT_IGNORED_DIRECTORIES)
    found: list[Path] = []
    for current, directories, files in os.walk(project_root):
        directories[:] = sorted(name for name in directories if name not in ignored and not name.startswith("."))
        found.extend(Path(current) / name for name in sorted(files))
    return found


def _joined(values: list[str], settings: OnboardingSettings) -> str:
    shown = values[: settings.maximum_listed_paths]
    hidden = len(values) - len(shown)
    return ", ".join(shown) + (f", and {hidden} more" if hidden else "")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _first_paragraph(text: str) -> str:
    paragraph: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if paragraph and not stripped:
            break
        if PROSE_START.match(stripped):
            paragraph.append(stripped)
        elif paragraph:
            break
    prose = MARKDOWN_EMPHASIS.sub("", MARKDOWN_LINK.sub(r"\1", " ".join(paragraph)))
    return " ".join(prose.split())


def _purpose(project_root: Path, manifests: list[Manifest], settings: OnboardingSettings) -> list[FactCandidate]:
    root_manifests = [item for item in manifests if "/" not in item.location and item.description]
    if root_manifests:
        manifest = root_manifests[0]
        value = _truncate(manifest.description, settings.maximum_fact_characters)
        return [FactCandidate(PURPOSE, value, f"`{manifest.location}` description", FROM_MANIFEST)]
    for name in DOCUMENTATION_FILES:
        path = project_root / name
        if not name.startswith("README") or not path.is_file():
            continue
        paragraph = _first_paragraph(read_text(path))
        if paragraph and not any(marker in paragraph.lower() for marker in README_BOILERPLATE):
            value = _truncate(paragraph, settings.maximum_fact_characters)
            return [FactCandidate(PURPOSE, value, f"`{name}` opening paragraph", FROM_DOCUMENTATION)]
    return []


def _location(manifest: Manifest) -> str:
    directory = manifest.location.rsplit("/", 1)[0] if "/" in manifest.location else ""
    return f"`{directory}/`" if directory else "root"


def _frameworks(manifest: Manifest) -> list[str]:
    found: dict[str, str] = {}
    for package, name in FRAMEWORK_PACKAGES:
        if name in found:
            continue
        dependency = next((item for item in sorted(manifest.dependencies) if matches(item, package)), None)
        if dependency:
            major = MAJOR_VERSION.search(manifest.versions.get(dependency, ""))
            found[name] = f"{name} {major.group(1)}" if major else name
    return [label for name, label in found.items() if not set(FRAMEWORK_SUBSUMES.get(name, ())) & set(found)]


def _system_shape(manifests: list[Manifest]) -> list[FactCandidate]:
    parts: list[str] = []
    evidence: list[str] = []
    for manifest in manifests:
        frameworks = _frameworks(manifest)
        if frameworks:
            parts.append(f"{' + '.join(frameworks)} ({_location(manifest)})")
            evidence.append(f"`{manifest.location}`")
    if not parts:
        return []
    return [FactCandidate(SYSTEM_SHAPE, ", ".join(parts), ", ".join(evidence), FROM_MANIFEST)]


def _external_systems(manifests: list[Manifest], settings: OnboardingSettings) -> list[FactCandidate]:
    systems: dict[str, list[str]] = {}
    for manifest in manifests:
        for package, system in EXTERNAL_SYSTEM_PACKAGES:
            if any(matches(dependency, package) for dependency in manifest.dependencies):
                locations = systems.setdefault(system, [])
                if f"`{manifest.location}`" not in locations:
                    locations.append(f"`{manifest.location}`")
    if not systems:
        return []
    evidence = sorted({location for locations in systems.values() for location in locations})
    return [FactCandidate(EXTERNAL_SYSTEMS, _joined(sorted(systems), settings), ", ".join(evidence), FROM_MANIFEST)]


def _compatibility(manifests: list[Manifest], settings: OnboardingSettings) -> list[FactCandidate]:
    runtimes: list[str] = []
    evidence: list[str] = []
    for manifest in manifests:
        for runtime in manifest.runtimes:
            if runtime not in runtimes:
                runtimes.append(runtime)
                evidence.append(f"`{manifest.location}`")
    if not runtimes:
        return []
    return [FactCandidate(COMPATIBILITY, _joined(runtimes, settings), ", ".join(evidence), FROM_MANIFEST)]


def _is_test_directory(name: str) -> bool:
    return name.lower() in TEST_DIRECTORY_NAMES or name.endswith(TEST_PROJECT_SUFFIXES)


def _is_test_file(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS)


def _source_paths(project_root: Path, files: list[Path], settings: OnboardingSettings) -> list[FactCandidate]:
    counts: dict[str, int] = {}
    for path in files:
        parts = path.relative_to(project_root).parts
        if len(parts) < 2 or path.suffix not in SOURCE_SUFFIXES:
            continue
        if any(_is_test_directory(part) for part in parts[:-1]) or _is_test_file(path.name):
            continue
        top = parts[0]
        if top.lower() in DOCUMENTATION_DIRECTORIES:
            continue
        counts[top] = counts.get(top, 0) + 1
    chosen = [
        name
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= settings.minimum_directory_sources or name in FALLBACK_SOURCE_DIRECTORIES
    ]
    if not chosen:
        return []
    value = _joined([f"`{name}/`" for name in chosen], settings)
    evidence = ", ".join(f"`{name}/` holds {counts[name]} source file(s)" for name in chosen[: settings.maximum_listed_paths])
    return [FactCandidate(SOURCE_PATHS, value, evidence, FROM_LAYOUT)]


def _test_paths(project_root: Path, files: list[Path], settings: OnboardingSettings) -> list[FactCandidate]:
    directories: dict[str, int] = {}
    patterns: dict[str, int] = {}
    for path in files:
        parts = path.relative_to(project_root).parts
        test_index = next((index for index, part in enumerate(parts[:-1]) if _is_test_directory(part)), None)
        if test_index is not None:
            if path.suffix in SOURCE_SUFFIXES:
                key = "/".join(parts[: test_index + 1]) + "/"
                directories[key] = directories.get(key, 0) + 1
            continue
        pattern = next((item for item in TEST_FILE_PATTERNS if fnmatch.fnmatchcase(path.name, item)), None)
        if pattern:
            key = f"{parts[0]}/**/{pattern}" if len(parts) > 1 else pattern
            patterns[key] = patterns.get(key, 0) + 1
    found = {**directories, **patterns}
    if not found:
        return [FactCandidate(TEST_PATHS, NONE_FOUND, "no test directory, test project, or test file exists", FROM_LAYOUT)]
    ordered = sorted(found, key=lambda key: (-found[key], key))
    value = _joined([f"`{key}`" for key in ordered], settings)
    evidence = ", ".join(f"{found[key]} test file(s) in `{key}`" for key in ordered[: settings.maximum_listed_paths])
    return [FactCandidate(TEST_PATHS, value, evidence, FROM_LAYOUT)]


def _documentation_paths(project_root: Path, settings: OnboardingSettings) -> list[FactCandidate]:
    found = [f"`{name}`" for name in DOCUMENTATION_FILES if (project_root / name).is_file()]
    found.extend(f"`{name}/`" for name in DOCUMENTATION_DIRECTORIES if (project_root / name).is_dir())
    if not found:
        return [FactCandidate(DOCUMENTATION_PATHS, NONE_FOUND, "no README or docs directory at the root", FROM_LAYOUT)]
    return [FactCandidate(DOCUMENTATION_PATHS, _joined(found, settings), "files present at the root", FROM_LAYOUT)]


def _script_platform(name: str) -> str:
    lowered = name.lower()
    return next((platform for hint, platform in DEPLOYMENT_NAME_HINTS if hint in lowered), "")


def _deployment_files(project_root: Path, directories: list[Path]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for directory in directories:
        for marker, platform in DEPLOYMENT_MARKERS:
            if (directory / marker).is_file():
                found.append((relative(project_root, directory / marker), platform))
        for path in sorted(directory.iterdir()):
            lowered = path.name.lower()
            if path.is_file() and lowered.endswith(DEPLOYMENT_SCRIPT_SUFFIXES):
                if any(fnmatch.fnmatchcase(lowered, pattern) for pattern in DEPLOYMENT_SCRIPT_PATTERNS):
                    found.append((relative(project_root, path), _script_platform(path.name)))
    return found


def _deployment(deployments: list[tuple[str, str]], settings: OnboardingSettings) -> list[FactCandidate]:
    platforms = list(dict.fromkeys(platform for _, platform in deployments if platform))
    if not platforms:
        return []
    evidence = ", ".join(f"`{path}`" for path, platform in deployments[: settings.maximum_listed_paths] if platform)
    return [FactCandidate(DEPLOYMENT, _joined(platforms, settings), evidence, FROM_LAYOUT)]


def _public_contracts(project_root: Path, files: list[Path], settings: OnboardingSettings) -> list[FactCandidate]:
    found: list[str] = []
    for path in files:
        for pattern, kind in CONTRACT_PATTERNS:
            if fnmatch.fnmatchcase(path.name, pattern):
                found.append(f"{kind} (`{relative(project_root, path)}`)")
                break
    if not found:
        return []
    return [FactCandidate(PUBLIC_CONTRACTS, _joined(found, settings), "contract files present", FROM_LAYOUT)]


def _protected_paths(
    project_root: Path, directories: list[Path], deployments: list[tuple[str, str]], settings: OnboardingSettings
) -> list[FactCandidate]:
    found: list[str] = []
    for marker, reason in PROTECTED_PATH_MARKERS:
        if (project_root / marker).exists():
            found.append(f"`{marker}` ({reason})")
    for directory in directories:
        for name, reason in PROTECTED_DIRECTORY_NAMES:
            entry = f"`{relative(project_root, directory)}` ({reason})"
            if directory != project_root and directory.name.lower() == name and entry not in found:
                found.append(entry)
    found.extend(
        f"`{path}` (deployment {'script' if path.lower().endswith(DEPLOYMENT_SCRIPT_SUFFIXES) else 'configuration'})"
        for path, _ in deployments
    )
    if not found:
        return []
    return [
        FactCandidate(
            PROTECTED_PATHS,
            _joined(found, settings),
            "paths whose changes reach CI, data, or deployment",
            FROM_LAYOUT,
        )
    ]


def derive_facts(
    project_root: Path,
    directories: list[Path],
    manifests: list[Manifest],
    settings: OnboardingSettings,
) -> list[FactCandidate]:
    files = walk_files(project_root)
    deployments = _deployment_files(project_root, directories)
    return (
        _purpose(project_root, manifests, settings)
        + _system_shape(manifests)
        + _public_contracts(project_root, files, settings)
        + _source_paths(project_root, files, settings)
        + _test_paths(project_root, files, settings)
        + _documentation_paths(project_root, settings)
        + _protected_paths(project_root, directories, deployments, settings)
        + _compatibility(manifests, settings)
        + _deployment(deployments, settings)
        + _external_systems(manifests, settings)
    )
