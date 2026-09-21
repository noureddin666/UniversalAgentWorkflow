from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tooling.workflow_config import (
    PATHS,
    PLACEHOLDER_MARKER,
    SCHEMA_VERSION,
    load_local_settings,
    load_onboarding_settings,
)
from tooling.workflow_features.architecture import check_architecture
from tooling.workflow_features.findings import validate_findings
from tooling.workflow_features.integration import entry_point_warnings
from tooling.workflow_features.routing import check_index, validate_routing
from tooling.workflow_features.session import validate_handoff
from tooling.workflow_features.specs import validate_specs


@dataclass
class DoctorReport:
    """Errors block; warnings say the installation is green but not yet described."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def _upgrade_json(path: Path) -> bool:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    current = value.get("schema_version", 0)
    if current > SCHEMA_VERSION:
        raise ValueError(f"{path} uses unsupported schema version {current}")
    if current == SCHEMA_VERSION:
        return False
    value["schema_version"] = SCHEMA_VERSION
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return True


def migrate(project_root: Path) -> list[str]:
    agent_root = PATHS.agent_root(project_root)
    patterns = (
        "config/*.json",
        "specs/*/spec.json",
        "specs/*/traceability.json",
        "specs/*/requirements/*.json",
        "findings/*/*/finding.json",
    )
    changed = []
    for pattern in patterns:
        for path in sorted(agent_root.glob(pattern)):
            if _upgrade_json(path):
                changed.append(path.relative_to(project_root).as_posix())
    return changed


def _placeholder_warnings(project_root: Path) -> list[str]:
    agent_root = PATHS.agent_root(project_root)
    targets = [agent_root / "PROJECT.md", agent_root / "COMMANDS.md"]
    targets.extend(sorted(agent_root.glob("scopes/*/PROFILE.md")))
    targets.extend(sorted(agent_root.glob("scopes/*/STATE.md")))
    warnings = []
    for path in targets:
        if not path.is_file():
            continue
        count = path.read_text(encoding="utf-8").count(PLACEHOLDER_MARKER)
        if count:
            location = path.relative_to(project_root).as_posix()
            warnings.append(f"{location}: {count} unfilled placeholder(s)")
    return warnings


def _vendor_warnings(project_root: Path) -> list[str]:
    """Each project carries its own copy of the framework, so it drifts silently behind the source."""
    installed = PATHS.agent_root(project_root) / "vendor" / "universal-agent-workflow" / "VERSION"
    if not installed.is_file():
        return ["Vendored workflow has no VERSION file; reinstall or update it"]
    current = Path(__file__).resolve().parents[3] / "VERSION"
    if not current.is_file():
        return []
    here = installed.read_text(encoding="utf-8").strip()
    there = current.read_text(encoding="utf-8").strip()
    if here == there:
        return []
    return [
        f"Vendored workflow is {here} but the source is {there}; "
        "run scripts/update_workflow.py <project> --migrate"
    ]


def doctor(project_root: Path) -> DoctorReport:
    report = DoctorReport()
    agent_root = PATHS.agent_root(project_root)
    for relative in ("PROJECT.md", "COMMANDS.md", "ROUTER.md", "config/scopes.json"):
        if not (agent_root / relative).is_file():
            report.errors.append(f"Missing required workflow file: .agent/{relative}")
    try:
        settings = load_local_settings(project_root)
        if settings.command_timeout_seconds <= 0 or settings.max_output_characters <= 0:
            report.errors.append("Local command limits must be positive")
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        report.errors.append(f"Invalid local config: {error}")
    try:
        architecture = check_architecture(project_root)
        report.errors.extend(architecture.configuration_errors)
        if architecture.status == "unconfigured":
            report.warnings.append(
                "config/architecture.json declares no modules; check-architecture inspects nothing"
            )
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as error:
        report.errors.append(f"Invalid architecture config: {error}")
    report.errors.extend(validate_routing(project_root))
    report.errors.extend(validate_specs(project_root))
    report.errors.extend(validate_findings(project_root))
    report.warnings.extend(validate_handoff(project_root))
    index_error = check_index(project_root)
    if index_error:
        report.errors.append(index_error)
    placeholders = _placeholder_warnings(project_root)
    report.warnings.extend(placeholders)
    if placeholders and not (agent_root / load_onboarding_settings(project_root).document_path).is_file():
        report.warnings.append("Run 'setup' to fill what the repository can prove, then answer the rest")
    report.warnings.extend(entry_point_warnings(project_root))
    report.warnings.extend(_vendor_warnings(project_root))
    report.errors = sorted(set(report.errors))
    report.warnings = sorted(set(report.warnings))
    return report
