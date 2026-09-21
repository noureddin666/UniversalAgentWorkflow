from __future__ import annotations

import re
from pathlib import Path

from tooling.workflow_config import PATHS, OnboardingSettings
from tooling.workflow_features.onboarding.detection import match_marker, read_json, read_text, relative
from tooling.workflow_features.onboarding.manifests import PROJECT_SDK_PATTERN
from tooling.workflow_features.onboarding.model import (
    CONFIDENCE_ORDER,
    FROM_CI,
    FROM_CONVENTION,
    FROM_MANIFEST,
    CommandCandidate,
    EcosystemFinding,
)
from tooling.workflow_features.onboarding.signals import (
    CI_FILES,
    CI_COMMAND_PREFIXES,
    CI_OPERATION_KEYWORDS,
    COMMAND_TOOLS,
    CONVENTION_COMMANDS,
    DOTNET_COMMANDS,
    DOTNET_RUN_COMMAND,
    DOTNET_RUNNABLE_SDKS,
    DOTNET_TEST_COMMAND,
    DOTNET_TEST_SDK,
    MAKE_TARGET_OPERATIONS,
    NODE_INSTALL_COMMANDS,
    OPERATION_ORDER,
    PYTHON_RESTORE_COMMANDS,
    PYTHON_TOOL_COMMANDS,
    RESTORE,
    RUN_LOCALLY,
    SCRIPT_OPERATIONS,
    TEST_PROJECT_SUFFIXES,
    UNIT_TESTS,
)


MAKE_TARGET_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)", re.MULTILINE)
CI_RUN_PATTERN = re.compile(r"^\s*-?\s*run:\s*(?!\||>)(.+?)\s*$", re.MULTILINE)
DEFAULT_PACKAGE_MANAGER = "npm"
WORKFLOW_SELF_CALL = f"{PATHS.agent_directory}/workflow"


def _node_manager(project_root: Path, directory: Path, ecosystems: list[EcosystemFinding]) -> str:
    for candidate in (directory, project_root):
        for lockfile, label in (
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("bun.lockb", "bun"),
            ("package-lock.json", "npm"),
        ):
            if (candidate / lockfile).is_file():
                return label
    declared = next((item.package_manager for item in ecosystems if item.name == "node"), "")
    return declared or DEFAULT_PACKAGE_MANAGER


def _node_commands(
    project_root: Path, directories: list[Path], ecosystems: list[EcosystemFinding]
) -> list[CommandCandidate]:
    found: list[CommandCandidate] = []
    for directory in directories:
        manifest = directory / "package.json"
        if not manifest.is_file():
            continue
        scripts = read_json(manifest).get("scripts")
        if not isinstance(scripts, dict):
            continue
        manager = _node_manager(project_root, directory, ecosystems)
        location = relative(project_root, manifest)
        prefix = "" if directory == project_root else f"cd {relative(project_root, directory)} && "
        found.append(
            CommandCandidate(RESTORE, prefix + NODE_INSTALL_COMMANDS[manager], location, FROM_MANIFEST)
        )
        for name, operation in SCRIPT_OPERATIONS.items():
            if name in scripts:
                command = f"{prefix}{manager} run {name}"
                found.append(CommandCandidate(operation, command, f"{location} scripts.{name}", FROM_MANIFEST))
    return found


def _make_commands(project_root: Path, directories: list[Path]) -> list[CommandCandidate]:
    found: list[CommandCandidate] = []
    for directory in directories:
        for marker in ("Makefile", "makefile"):
            path = directory / marker
            if not path.is_file():
                continue
            location = relative(project_root, path)
            prefix = "" if directory == project_root else f"cd {relative(project_root, directory)} && "
            for target in MAKE_TARGET_PATTERN.findall(read_text(path)):
                operation = MAKE_TARGET_OPERATIONS.get(target)
                if operation:
                    found.append(
                        CommandCandidate(
                            operation, f"{prefix}make {target}", f"{location} target {target}", FROM_MANIFEST
                        )
                    )
    return found


def _dotnet_commands(
    project_root: Path, directories: list[Path], ecosystems: list[EcosystemFinding]
) -> list[CommandCandidate]:
    """A solution file drives the whole build; a single project file is the fallback target."""
    if not any(item.name == "dotnet" for item in ecosystems):
        return []
    target = None
    for marker in ("*.slnx", "*.sln", "*.csproj"):
        target = next((found for directory in directories if (found := match_marker(directory, marker))), None)
        if target:
            break
    if not target:
        return []
    location = relative(project_root, target)
    found = [
        CommandCandidate(operation, template.format(solution=location), location, FROM_MANIFEST)
        for operation, template in DOTNET_COMMANDS
    ]
    projects = sorted({path for directory in directories for path in directory.glob("*.csproj")})
    test_projects = [
        path for path in projects if path.stem.endswith(TEST_PROJECT_SUFFIXES) or DOTNET_TEST_SDK in read_text(path)
    ]
    if test_projects:
        evidence = relative(project_root, test_projects[0])
        found.append(CommandCandidate(UNIT_TESTS, DOTNET_TEST_COMMAND.format(solution=location), evidence, FROM_MANIFEST))
    for project in projects:
        sdk = PROJECT_SDK_PATTERN.search(read_text(project))
        if sdk and sdk.group(1) in DOTNET_RUNNABLE_SDKS and project not in test_projects:
            path = relative(project_root, project)
            found.append(
                CommandCandidate(RUN_LOCALLY, DOTNET_RUN_COMMAND.format(project=path), f"{path} Sdk {sdk.group(1)}", FROM_MANIFEST)
            )
    return found


def _python_commands(project_root: Path, directories: list[Path]) -> list[CommandCandidate]:
    found: list[CommandCandidate] = []
    declarations = ""
    for directory in directories:
        for marker in ("pyproject.toml", "requirements.txt", "setup.cfg", "Pipfile"):
            path = directory / marker
            if path.is_file():
                declarations += read_text(path)
    if not declarations:
        return []
    for lockfile, command in PYTHON_RESTORE_COMMANDS:
        for directory in directories:
            if (directory / lockfile).is_file():
                found.append(
                    CommandCandidate(RESTORE, command, relative(project_root, directory / lockfile), FROM_MANIFEST)
                )
                break
        if found:
            break
    for tool, operation, command in PYTHON_TOOL_COMMANDS:
        if tool in declarations:
            found.append(CommandCandidate(operation, command, f"{tool} declared in a Python manifest", FROM_MANIFEST))
    return found


def _convention_commands(
    project_root: Path, directories: list[Path], ecosystems: list[EcosystemFinding]
) -> list[CommandCandidate]:
    names = {item.name for item in ecosystems}
    found: list[CommandCandidate] = []
    if "dart" in names:
        pubspec = next(
            (directory / "pubspec.yaml" for directory in directories if (directory / "pubspec.yaml").is_file()),
            None,
        )
        flavour = "flutter" if pubspec and "flutter:" in read_text(pubspec) else "dart"
        evidence = relative(project_root, pubspec) if pubspec else "pubspec.yaml"
        found.extend(
            CommandCandidate(operation, command, evidence, FROM_CONVENTION)
            for operation, command in CONVENTION_COMMANDS[flavour]
        )
    for finding in ecosystems:
        for operation, command in CONVENTION_COMMANDS.get(finding.name, ()):
            found.append(CommandCandidate(operation, command, finding.evidence, FROM_CONVENTION))
    return found


def _classify(command: str) -> str:
    lowered = command.lower()
    for prefix, operation in CI_COMMAND_PREFIXES:
        if lowered.startswith(prefix):
            return operation
    for keyword, operation in CI_OPERATION_KEYWORDS:
        if keyword in lowered:
            return operation
    return ""


def _ci_commands(project_root: Path) -> list[CommandCandidate]:
    found: list[CommandCandidate] = []
    for pattern in CI_FILES:
        for path in sorted(project_root.glob(pattern)):
            if not path.is_file():
                continue
            location = relative(project_root, path)
            for raw in CI_RUN_PATTERN.findall(read_text(path)):
                command = raw.strip().strip("\"'")
                if not command or command.split()[0] not in COMMAND_TOOLS:
                    continue
                if WORKFLOW_SELF_CALL in command.replace("\\", "/"):
                    continue
                operation = _classify(command)
                if operation:
                    found.append(CommandCandidate(operation, command, location, FROM_CI))
    return found


def _rank(candidate: CommandCandidate) -> tuple[int, int, str]:
    operation = (
        OPERATION_ORDER.index(candidate.operation)
        if candidate.operation in OPERATION_ORDER
        else len(OPERATION_ORDER)
    )
    return operation, CONFIDENCE_ORDER.index(candidate.confidence), candidate.command


def collect_commands(
    project_root: Path,
    directories: list[Path],
    ecosystems: list[EcosystemFinding],
    settings: OnboardingSettings,
) -> list[CommandCandidate]:
    """Strongest evidence wins for an identical command; competing commands all survive."""
    collected = (
        _ci_commands(project_root)
        + _node_commands(project_root, directories, ecosystems)
        + _make_commands(project_root, directories)
        + _python_commands(project_root, directories)
        + _dotnet_commands(project_root, directories, ecosystems)
        + _convention_commands(project_root, directories, ecosystems)
    )
    best: dict[tuple[str, str], CommandCandidate] = {}
    for candidate in sorted(collected, key=_rank):
        best.setdefault((candidate.operation, candidate.command), candidate)
    return sorted(best.values(), key=_rank)
