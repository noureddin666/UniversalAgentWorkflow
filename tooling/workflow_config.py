from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class WorkflowPaths:
    agent_directory: str = ".agent"
    specs_directory: str = "specs"
    workflow_config: str = "config/workflow.json"
    architecture_config: str = "config/architecture.json"
    scopes_config: str = "config/scopes.json"
    project_index: str = "INDEX.json"
    local_config: str = "config/local.json"
    onboarding_config: str = "config/onboarding.json"
    current_requirement: str = "requirements/CURRENT.md"

    def agent_root(self, project_root: Path) -> Path:
        return project_root / self.agent_directory


PATHS = WorkflowPaths()
SCHEMA_VERSION = 1
PLACEHOLDER_MARKER = "TODO"


def discover_project_root(start: Path | None = None) -> Path:
    """Walk up from start until the agent directory is found; agents rarely run from the root."""
    current = (start or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if PATHS.agent_root(candidate).is_dir():
            return candidate
    return current


@dataclass(frozen=True)
class LocalSettings:
    command_timeout_seconds: int
    max_output_characters: int
    runs_directory: str
    dashboard_path: str


def load_local_settings(project_root: Path) -> LocalSettings:
    path = PATHS.agent_root(project_root) / PATHS.local_config
    if not path.is_file():
        raise FileNotFoundError(f"Local config not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    return LocalSettings(
        command_timeout_seconds=int(value["command_timeout_seconds"]),
        max_output_characters=int(value["max_output_characters"]),
        runs_directory=value["runs_directory"],
        dashboard_path=value["dashboard_path"],
    )


DEFAULT_ENTRY_POINTS = (
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    ".cursor/rules/agent-workflow.mdc",
)


@dataclass(frozen=True)
class WorkflowSettings:
    require_approval_for: tuple[str, ...] = ("Accepted", "Implemented")
    require_traceability_for_implemented: bool = True
    entry_points: tuple[str, ...] = DEFAULT_ENTRY_POINTS
    handoff_path: str = "HANDOFF.md"
    handoff_max_lines: int = 30
    handoff_max_characters: int = 3000
    context_warning_tokens: int = 4000
    context_max_tokens: int = 8000
    context_characters_per_token: float = 4.0
    agent_warning_count: int = 12
    agent_maximum_count: int = 24
    agent_maximum_concurrency: int = 6
    agent_maximum_high_effort: int = 2
    task_max_attempts: int = 3
    document_whole_file_lines: int = 80


DEFAULT_WORKFLOW_SETTINGS = WorkflowSettings()


def load_workflow_settings(project_root: Path) -> WorkflowSettings:
    path = PATHS.agent_root(project_root) / PATHS.workflow_config
    if not path.is_file():
        return DEFAULT_WORKFLOW_SETTINGS
    value = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowSettings(
        require_approval_for=tuple(
            value.get("require_approval_for", DEFAULT_WORKFLOW_SETTINGS.require_approval_for)
        ),
        require_traceability_for_implemented=bool(
            value.get(
                "require_traceability_for_implemented",
                DEFAULT_WORKFLOW_SETTINGS.require_traceability_for_implemented,
            )
        ),
        entry_points=tuple(value.get("entry_points", DEFAULT_WORKFLOW_SETTINGS.entry_points)),
        handoff_path=value.get("handoff_path", DEFAULT_WORKFLOW_SETTINGS.handoff_path),
        handoff_max_lines=int(
            value.get("handoff_max_lines", DEFAULT_WORKFLOW_SETTINGS.handoff_max_lines)
        ),
        handoff_max_characters=int(
            value.get("handoff_max_characters", DEFAULT_WORKFLOW_SETTINGS.handoff_max_characters)
        ),
        context_warning_tokens=int(
            value.get("context_warning_tokens", DEFAULT_WORKFLOW_SETTINGS.context_warning_tokens)
        ),
        context_max_tokens=int(
            value.get("context_max_tokens", DEFAULT_WORKFLOW_SETTINGS.context_max_tokens)
        ),
        context_characters_per_token=float(
            value.get(
                "context_characters_per_token",
                DEFAULT_WORKFLOW_SETTINGS.context_characters_per_token,
            )
        ),
        agent_warning_count=int(
            value.get("agent_warning_count", DEFAULT_WORKFLOW_SETTINGS.agent_warning_count)
        ),
        agent_maximum_count=int(
            value.get("agent_maximum_count", DEFAULT_WORKFLOW_SETTINGS.agent_maximum_count)
        ),
        document_whole_file_lines=int(
            value.get(
                "document_whole_file_lines", DEFAULT_WORKFLOW_SETTINGS.document_whole_file_lines
            )
        ),
        task_max_attempts=int(
            value.get("task_max_attempts", DEFAULT_WORKFLOW_SETTINGS.task_max_attempts)
        ),
        agent_maximum_concurrency=int(
            value.get(
                "agent_maximum_concurrency", DEFAULT_WORKFLOW_SETTINGS.agent_maximum_concurrency
            )
        ),
        agent_maximum_high_effort=int(
            value.get(
                "agent_maximum_high_effort", DEFAULT_WORKFLOW_SETTINGS.agent_maximum_high_effort
            )
        ),
    )


DEFAULT_IGNORED_DIRECTORIES = (
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vs",
    ".vscode",
    ".agent",
    "node_modules",
    "bower_components",
    "vendor",
    "bin",
    "obj",
    "build",
    "dist",
    "out",
    "target",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    ".dart_tool",
    "Pods",
    "DerivedData",
)


@dataclass(frozen=True)
class ArchitectureSettings:
    adapter_mode: str = "auto"
    ignored_directories: tuple[str, ...] = DEFAULT_IGNORED_DIRECTORIES

    @property
    def adapters_enabled(self) -> bool:
        return self.adapter_mode != "off"


DEFAULT_ARCHITECTURE_SETTINGS = ArchitectureSettings()
ADAPTER_MODES = ("auto", "off")


SPEC_STATES = ("Proposed", "Accepted", "Implemented", "Superseded", "Blocked")
TRANSITIONS = {
    "Proposed": {"Accepted", "Blocked", "Superseded"},
    "Accepted": {"Implemented", "Blocked", "Superseded"},
    "Blocked": {"Proposed", "Accepted", "Superseded"},
    "Implemented": {"Superseded"},
    "Superseded": set(),
}
SOURCE_SUFFIXES = {
    ".cs",
    ".c",
    ".cc",
    ".cpp",
    ".dart",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".ts",
    ".tsx",
}


@dataclass(frozen=True)
class OnboardingSettings:
    document_path: str = "ONBOARDING.md"
    max_scan_depth: int = 3
    minimum_directory_sources: int = 3
    maximum_suggested_scopes: int = 12
    maximum_listed_paths: int = 8
    maximum_fact_characters: int = 300
    adopt_confidence: tuple[str, ...] = ("ci", "declared", "documented", "observed")


DEFAULT_ONBOARDING_SETTINGS = OnboardingSettings()


def load_onboarding_settings(project_root: Path) -> OnboardingSettings:
    path = PATHS.agent_root(project_root) / PATHS.onboarding_config
    if not path.is_file():
        return DEFAULT_ONBOARDING_SETTINGS
    value = json.loads(path.read_text(encoding="utf-8"))
    default = DEFAULT_ONBOARDING_SETTINGS
    return OnboardingSettings(
        document_path=value.get("document_path", default.document_path),
        max_scan_depth=int(value.get("max_scan_depth", default.max_scan_depth)),
        minimum_directory_sources=int(
            value.get("minimum_directory_sources", default.minimum_directory_sources)
        ),
        maximum_suggested_scopes=int(
            value.get("maximum_suggested_scopes", default.maximum_suggested_scopes)
        ),
        maximum_listed_paths=int(value.get("maximum_listed_paths", default.maximum_listed_paths)),
        maximum_fact_characters=int(
            value.get("maximum_fact_characters", default.maximum_fact_characters)
        ),
        adopt_confidence=tuple(value.get("adopt_confidence", default.adopt_confidence)),
    )
