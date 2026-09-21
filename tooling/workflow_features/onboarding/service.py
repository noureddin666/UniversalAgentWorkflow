from __future__ import annotations

from pathlib import Path

from tooling.workflow_config import PATHS, SOURCE_SUFFIXES, load_onboarding_settings, load_workflow_settings
from tooling.workflow_features.onboarding.commands import collect_commands
from tooling.workflow_features.onboarding.detection import (
    detect_ecosystems,
    relative,
    scan_directories,
    suggest_modules,
    suggest_scopes,
)
from tooling.workflow_features.onboarding.document import UNDERIVABLE_FACTS, render
from tooling.workflow_features.onboarding.facts import derive_facts
from tooling.workflow_features.onboarding.manifests import read_manifests
from tooling.workflow_features.onboarding.model import EXISTING_CODE, GREENFIELD, BootstrapReport


def _holds_source(directories: list[Path]) -> bool:
    for directory in directories:
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        if any(entry.is_file() and entry.suffix in SOURCE_SUFFIXES for entry in entries):
            return True
    return False


def _existing_entry_points(project_root: Path) -> list[str]:
    settings = load_workflow_settings(project_root)
    return [name for name in settings.entry_points if (project_root / name).is_file()]


def scan(project_root: Path) -> BootstrapReport:
    agent_root = PATHS.agent_root(project_root)
    if not agent_root.is_dir():
        raise FileNotFoundError(f"Workflow is not installed in {project_root}: {agent_root} is missing")
    settings = load_onboarding_settings(project_root)
    directories = scan_directories(project_root, settings)
    ecosystems = detect_ecosystems(project_root, directories)
    greenfield = not ecosystems and not _holds_source(directories)
    scopes = [] if greenfield else suggest_scopes(project_root, directories, settings)
    manifests = read_manifests(project_root, directories)
    return BootstrapReport(
        mode=GREENFIELD if greenfield else EXISTING_CODE,
        ecosystems=ecosystems,
        commands=collect_commands(project_root, directories, ecosystems, settings),
        facts=[] if greenfield else derive_facts(project_root, directories, manifests, settings),
        scopes=scopes,
        modules=suggest_modules(project_root, scopes, settings),
        entry_points=_existing_entry_points(project_root),
        open_questions=list(UNDERIVABLE_FACTS),
    )


def bootstrap(project_root: Path, force: bool = False) -> BootstrapReport:
    """Reads the repository into onboarding suggestions. Writes one document and nothing else."""
    settings = load_onboarding_settings(project_root)
    document_path = PATHS.agent_root(project_root) / settings.document_path
    if document_path.exists() and not force:
        raise FileExistsError(
            f"{relative(project_root, document_path)} already exists; pass --force to regenerate it"
        )
    report = scan(project_root)
    document_path.parent.mkdir(parents=True, exist_ok=True)
    document_path.write_text(render(report), encoding="utf-8")
    report.document = relative(project_root, document_path)
    return report
