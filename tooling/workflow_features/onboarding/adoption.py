from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, PLACEHOLDER_MARKER, load_onboarding_settings
from tooling.workflow_features.onboarding.detection import read_json
from tooling.workflow_features.onboarding.model import GREENFIELD, BootstrapReport, CommandCandidate
from tooling.workflow_features.onboarding.service import scan
from tooling.workflow_features.onboarding.signals import OPERATION_ORDER, RESTORE


FIELD_LINE = re.compile(rf"^- (?P<field>[^:\n]+): {PLACEHOLDER_MARKER}[ \t]*$", re.MULTILINE)
COMMAND_ROW = re.compile(rf"^\|\s*(?P<operation>[^|\n]+?)\s*\|(?P<cells>(?:[ \t]*{PLACEHOLDER_MARKER}[ \t]*\|)+)[ \t]*$", re.MULTILINE)
DIRECTORY_PREFIX = re.compile(r"^cd (\S+) && ")
SLUG = re.compile(r"[^a-z0-9]+")
NOT_DECLARED = "not declared"
NOT_DECLARED_REASON = "no manifest, Makefile, or CI step declares one"


@dataclass
class AdoptionReport:
    facts: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    not_declared: list[str] = field(default_factory=list)
    project_id: str = ""
    remaining: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts,
            "commands": self.commands,
            "not_declared": self.not_declared,
            "project_id": self.project_id,
            "remaining": self.remaining,
        }


def _adopt_facts(path: Path, report: BootstrapReport, accepted: tuple[str, ...], result: AdoptionReport) -> None:
    if not path.is_file():
        return
    facts = {item.field: item for item in report.facts if item.confidence in accepted}

    def replace(match: re.Match[str]) -> str:
        fact = facts.get(match.group("field"))
        if not fact:
            result.remaining.append(f"PROJECT.md: {match.group('field')}")
            return match.group(0)
        result.facts.append(fact.field)
        return f"- {fact.field}: {fact.value} _(evidence: {fact.evidence})_"

    path.write_text(FIELD_LINE.sub(replace, path.read_text(encoding="utf-8")), encoding="utf-8")


def _prerequisite(candidate: CommandCandidate) -> str:
    directory = DIRECTORY_PREFIX.match(candidate.command)
    command = DIRECTORY_PREFIX.sub("", candidate.command)
    if candidate.operation == RESTORE:
        return f"`{command.split()[0]}` installed"
    return f"`{directory.group(1)}` restored" if directory else "Restore completed"


def _row(operation: str, command: str, prerequisite: str, evidence: str, columns: int) -> str:
    cells = [operation, command, prerequisite, evidence][:columns]
    return "| " + " | ".join(cells) + " |"


def _adopt_commands(path: Path, report: BootstrapReport, accepted: tuple[str, ...], result: AdoptionReport) -> None:
    if not path.is_file():
        return
    strong: dict[str, list[CommandCandidate]] = {}
    weak: set[str] = set()
    for candidate in report.commands:
        if candidate.confidence in accepted:
            strong.setdefault(candidate.operation, []).append(candidate)
        else:
            weak.add(candidate.operation)

    def replace(match: re.Match[str]) -> str:
        operation = match.group("operation")
        columns = 1 + match.group("cells").count("|")
        if operation not in OPERATION_ORDER:
            return match.group(0)
        if operation in strong:
            rows = []
            for candidate in strong[operation]:
                result.commands.append(f"{operation}: {candidate.command}")
                rows.append(
                    _row(operation, f"`{candidate.command}`", _prerequisite(candidate), f"`{candidate.evidence}`", columns)
                )
            return "\n".join(rows)
        if operation in weak:
            result.remaining.append(f"COMMANDS.md: {operation} (only convention-derived candidates; see ONBOARDING.md)")
            return match.group(0)
        result.not_declared.append(operation)
        if columns > 3:
            return _row(operation, NOT_DECLARED, "—", NOT_DECLARED_REASON, columns)
        return _row(operation, NOT_DECLARED, NOT_DECLARED_REASON, "", columns)

    path.write_text(COMMAND_ROW.sub(replace, path.read_text(encoding="utf-8")), encoding="utf-8")


def _project_name(project_root: Path) -> str:
    name = read_json(project_root / "package.json").get("name")
    solution = next(iter(sorted([*project_root.glob("*.slnx"), *project_root.glob("*.sln")])), None)
    if isinstance(name, str) and name:
        source = name
    elif solution:
        source = solution.stem
    else:
        source = project_root.name
    return SLUG.sub("-", source.lower().rsplit("/", 1)[-1]).strip("-")


def _adopt_project_id(project_root: Path, result: AdoptionReport) -> None:
    path = PATHS.agent_root(project_root) / PATHS.scopes_config
    config = read_json(path)
    project = config.get("project")
    if not isinstance(project, dict) or project.get("id") != PLACEHOLDER_MARKER:
        return
    project["id"] = _project_name(project_root)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    result.project_id = project["id"]


def unanswered_fields(project_root: Path) -> list[str]:
    path = PATHS.agent_root(project_root) / "PROJECT.md"
    if not path.is_file():
        return []
    return [match.group("field") for match in FIELD_LINE.finditer(path.read_text(encoding="utf-8"))]


def answer_field(project_root: Path, field_name: str, value: str) -> bool:
    path = PATHS.agent_root(project_root) / "PROJECT.md"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^- {re.escape(field_name)}: {PLACEHOLDER_MARKER}[ 	]*$", re.MULTILINE)
    updated, count = pattern.subn(lambda _: f"- {field_name}: {value.strip()}", text, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")
    return bool(count)


def adopt(project_root: Path) -> AdoptionReport:
    """Fills only placeholders, and only from evidence strong enough to trust; a written value is never replaced."""
    settings = load_onboarding_settings(project_root)
    report = scan(project_root)
    agent_root = PATHS.agent_root(project_root)
    result = AdoptionReport()
    _adopt_facts(agent_root / "PROJECT.md", report, settings.adopt_confidence, result)
    if report.mode == GREENFIELD:
        result.remaining.append("COMMANDS.md: fill after the first successful build")
    else:
        _adopt_commands(agent_root / "COMMANDS.md", report, settings.adopt_confidence, result)
    _adopt_project_id(project_root, result)
    return result
