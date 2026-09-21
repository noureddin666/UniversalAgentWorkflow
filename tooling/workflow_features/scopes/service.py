from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, SCHEMA_VERSION


SCOPE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CHANGE_CLASSIFICATIONS = ("clarification", "additive", "replacement", "reversal")


def _config_path(project_root: Path) -> Path:
    return PATHS.agent_root(project_root) / PATHS.scopes_config


def _load_config(project_root: Path) -> dict[str, Any]:
    path = _config_path(project_root)
    if not path.is_file():
        raise FileNotFoundError(f"Scopes config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    _config_path(project_root).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def create_scope(
    project_root: Path,
    scope_id: str,
    title: str,
    kind: str,
    paths: list[str],
    parent: str | None,
    depends_on: list[str] | None = None,
    verification: list[dict[str, str]] | None = None,
) -> Path:
    if not SCOPE_ID_PATTERN.fullmatch(scope_id):
        raise ValueError("Scope id must use lowercase kebab-case")
    config = _load_config(project_root)
    scopes = config.setdefault("scopes", [])
    known = {scope.get("id") for scope in scopes}
    if scope_id in known:
        raise FileExistsError(f"Scope already exists: {scope_id}")
    if parent and parent not in known:
        raise ValueError(f"Unknown parent scope: {parent}")
    for dependency in depends_on or []:
        if dependency not in known:
            raise ValueError(f"Unknown dependency scope: {dependency}")
    directory = PATHS.agent_root(project_root) / "scopes" / scope_id
    if directory.exists():
        raise FileExistsError(f"Scope directory already exists: {directory}")
    directory.mkdir(parents=True)
    relative_directory = directory.relative_to(project_root).as_posix()
    artifacts = [
        f"{relative_directory}/PROFILE.md",
        f"{relative_directory}/STATE.md",
        f"{relative_directory}/DECISIONS.md",
        f"{relative_directory}/CHANGES.md",
    ]
    scopes.append(
        {
            "id": scope_id,
            "title": title,
            "kind": kind,
            "parent": parent,
            "paths": paths,
            "context": artifacts,
            "depends_on": depends_on or [],
            "verification": verification or [],
        }
    )
    config["schema_version"] = SCHEMA_VERSION
    _write_config(project_root, config)
    (directory / "PROFILE.md").write_text(_profile(title, scope_id, kind), encoding="utf-8")
    (directory / "STATE.md").write_text(_state(title), encoding="utf-8")
    (directory / "DECISIONS.md").write_text(
        f"# {title} decisions\n\nRecord durable decisions, alternatives, rationale, owner, and consequences.\n",
        encoding="utf-8",
    )
    (directory / "CHANGES.md").write_text(
        f"# {title} change log\n\nRecord material business, boundary, contract, data, or operational changes.\n",
        encoding="utf-8",
    )
    return directory


def _profile(title: str, scope_id: str, kind: str) -> str:
    return f"""# {title} scope profile

- Scope id: `{scope_id}`
- Kind: {kind}
- Business owner: TODO
- Technical owner: TODO
- Lifecycle: discovery | active | production | maintenance

## Business purpose

TODO

## Users and stakeholders

- TODO

## Outcomes and success measures

| Outcome | Measure | Current baseline | Target | Source |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO |

## Capabilities and responsibilities

- TODO

## Out of scope

- TODO

## Business rules and invariants

- TODO

## Domain language

| Term | Meaning | Avoid |
|---|---|---|
| TODO | TODO | TODO |

## Actors, entities, and lifecycle

- Actors: TODO
- Entities: TODO
- State transitions: TODO
- Domain events: TODO

## Contracts and dependencies

- Inbound contracts: TODO
- Outbound contracts: TODO
- Upstream scopes: TODO
- Downstream scopes: TODO

## Data ownership

- Source of truth: TODO
- Sensitive data: TODO
- Retention and deletion: TODO

## Constraints, risks, and failure modes

- TODO
"""


def _state(title: str) -> str:
    return f"""# {title} current state

- Last reviewed: {date.today().isoformat()}
- Reviewed by: TODO

## Active business variables

| Variable or policy | Current value or rule | Source/owner | Effective date | Impact if changed |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO |

## Active assumptions

| Assumption | Validation | Owner | Consequence if false |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Open questions

| Question | Owner | Needed by | Impact |
|---|---|---|---|
| TODO | TODO | TODO | TODO |

## Operational health

- Known limitations: TODO
- Current incidents or risks: TODO
- Relevant dashboards: TODO
"""


def record_scope_change(
    project_root: Path,
    scope_id: str,
    summary: str,
    actor: str,
    classification: str,
    impact: list[str],
) -> Path:
    if classification not in CHANGE_CLASSIFICATIONS:
        raise ValueError(f"Unknown change classification: {classification}")
    directory = PATHS.agent_root(project_root) / "scopes" / scope_id
    path = directory / "CHANGES.md"
    if not path.is_file():
        raise FileNotFoundError(f"Scope change log not found: {scope_id}")
    entry = (
        f"\n## {date.today().isoformat()} — {summary}\n\n"
        f"- Requested by: {actor}\n"
        f"- Classification: {classification}\n"
        f"- Impact: {', '.join(impact) if impact else 'Not yet assessed'}\n"
        "- Affected specs: TODO\n"
        "- Invalidated rules, variables, assumptions, or decisions: TODO\n"
        "- Required verification: TODO\n"
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(entry)
    return path
