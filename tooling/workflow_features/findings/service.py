from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, SCHEMA_VERSION


FINDING_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FINDING_TYPES = {"bug": "bugs", "discovery": "discoveries"}
FINDING_STATUSES = ("Open", "Triaged", "Planned", "Resolved", "Dismissed")
FINDING_TRANSITIONS = {
    "Open": {"Triaged", "Dismissed"},
    "Triaged": {"Planned", "Resolved", "Dismissed"},
    "Planned": {"Resolved", "Dismissed", "Triaged"},
    "Resolved": {"Open"},
    "Dismissed": {"Open"},
}


def create_finding(
    project_root: Path,
    finding_type: str,
    finding_id: str,
    title: str,
    reporter: str,
    severity: str,
    scope_ids: list[str],
    spec_ids: list[str],
) -> Path:
    if finding_type not in FINDING_TYPES:
        raise ValueError(f"Unknown finding type: {finding_type}")
    if not FINDING_ID_PATTERN.fullmatch(finding_id):
        raise ValueError("Finding id must use lowercase kebab-case")
    directory = PATHS.agent_root(project_root) / "findings" / FINDING_TYPES[finding_type] / finding_id
    if directory.exists():
        raise FileExistsError(f"Finding already exists: {finding_id}")
    directory.mkdir(parents=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "id": finding_id,
        "type": finding_type,
        "title": title,
        "status": "Open",
        "severity": severity,
        "reporter": reporter,
        "created": date.today().isoformat(),
        "scope_ids": scope_ids,
        "spec_ids": spec_ids,
        "related_findings": [],
    }
    (directory / "finding.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (directory / "details.md").write_text(
        f"# {title}\n\n## Observation\n\nTODO\n\n## Expected or implication\n\nTODO\n\n"
        "## Reproduction or validation\n\nTODO\n\n## Suspected boundaries\n\nTODO\n",
        encoding="utf-8",
    )
    (directory / "evidence.md").write_text(
        "# Evidence\n\n- Logs, screenshots, traces, measurements, or source references: TODO\n",
        encoding="utf-8",
    )
    return directory


def load_findings(project_root: Path) -> list[dict[str, Any]]:
    root = PATHS.agent_root(project_root) / "findings"
    result = []
    for path in sorted(root.glob("*/*/finding.json")):
        result.append(json.loads(path.read_text(encoding="utf-8")))
    return result


def transition_finding(
    project_root: Path,
    finding_type: str,
    finding_id: str,
    target: str,
    actor: str,
    evidence: list[str],
) -> None:
    if finding_type not in FINDING_TYPES:
        raise ValueError(f"Unknown finding type: {finding_type}")
    path = PATHS.agent_root(project_root) / "findings" / FINDING_TYPES[finding_type] / finding_id / "finding.json"
    if not path.is_file():
        raise FileNotFoundError(f"Finding not found: {finding_id}")
    finding = json.loads(path.read_text(encoding="utf-8"))
    current = finding.get("status")
    if target not in FINDING_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid finding transition: {current} -> {target}")
    if target in {"Resolved", "Dismissed"} and not evidence:
        raise ValueError(f"{target} requires evidence")
    finding["status"] = target
    finding.setdefault("history", []).append(
        {"state": target, "actor": actor, "date": date.today().isoformat(), "evidence": evidence}
    )
    path.write_text(json.dumps(finding, indent=2) + "\n", encoding="utf-8")


def validate_findings(project_root: Path) -> list[str]:
    errors: list[str] = []
    agent_root = PATHS.agent_root(project_root)
    scopes_path = agent_root / PATHS.scopes_config
    scopes = json.loads(scopes_path.read_text(encoding="utf-8")) if scopes_path.is_file() else {"scopes": []}
    known_scopes = {scope.get("id") for scope in scopes.get("scopes", [])}
    known_specs = {path.parent.name for path in (agent_root / PATHS.specs_directory).glob("*/spec.json")}
    for finding in load_findings(project_root):
        finding_id = finding.get("id", "")
        if finding.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{finding_id}: finding requires migration")
        if finding.get("type") not in FINDING_TYPES:
            errors.append(f"{finding_id}: invalid finding type")
        if finding.get("status") not in FINDING_STATUSES:
            errors.append(f"{finding_id}: invalid finding status")
        for scope_id in finding.get("scope_ids", []):
            if scope_id not in known_scopes:
                errors.append(f"{finding_id}: unknown scope {scope_id}")
        for spec_id in finding.get("spec_ids", []):
            if spec_id not in known_specs:
                errors.append(f"{finding_id}: unknown spec {spec_id}")
    return errors
