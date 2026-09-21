from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXISTING_CODE = "existing-code"
GREENFIELD = "greenfield"

FROM_CI = "ci"
FROM_MANIFEST = "declared"
FROM_DOCUMENTATION = "documented"
FROM_LAYOUT = "observed"
FROM_CONVENTION = "derived"

CONFIDENCE_ORDER = (FROM_CI, FROM_MANIFEST, FROM_DOCUMENTATION, FROM_LAYOUT, FROM_CONVENTION)

CONFIDENCE_MEANING = {
    FROM_CI: "appears in a CI pipeline in this repository",
    FROM_MANIFEST: "declared in a manifest in this repository",
    FROM_DOCUMENTATION: "stated in this repository's own documentation",
    FROM_LAYOUT: "observed in this repository's files and directories",
    FROM_CONVENTION: "inferred from ecosystem convention only",
}


PURPOSE = "Purpose"
SYSTEM_SHAPE = "System shape"
PUBLIC_CONTRACTS = "Public contracts"
SOURCE_PATHS = "Main source paths"
TEST_PATHS = "Test paths"
DOCUMENTATION_PATHS = "Documentation paths"
PROTECTED_PATHS = "Protected paths requiring approval"
COMPATIBILITY = "Compatibility"
DEPLOYMENT = "Deployment environment"
EXTERNAL_SYSTEMS = "External systems"


@dataclass(frozen=True)
class EcosystemFinding:
    name: str
    profile: str
    evidence: str
    package_manager: str = ""


@dataclass(frozen=True)
class CommandCandidate:
    """No candidate is ever 'verified': bootstrap reads files, it never runs them."""

    operation: str
    command: str
    evidence: str
    confidence: str


@dataclass(frozen=True)
class FactCandidate:
    field: str
    value: str
    evidence: str
    confidence: str


@dataclass(frozen=True)
class ScopeCandidate:
    scope_id: str
    title: str
    kind: str
    path: str
    evidence: str

    def creation_command(self) -> str:
        return (
            f"python .agent/workflow.py create-scope {self.scope_id} "
            f'--title "{self.title}" --kind {self.kind} --path {self.path}'
        )


@dataclass(frozen=True)
class ModuleCandidate:
    name: str
    path: str
    import_prefixes: tuple[str, ...]
    evidence: str

    def as_rule(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "import_prefixes": list(self.import_prefixes),
            "may_depend_on": [],
        }


@dataclass
class BootstrapReport:
    mode: str = EXISTING_CODE
    ecosystems: list[EcosystemFinding] = field(default_factory=list)
    commands: list[CommandCandidate] = field(default_factory=list)
    facts: list[FactCandidate] = field(default_factory=list)
    scopes: list[ScopeCandidate] = field(default_factory=list)
    modules: list[ModuleCandidate] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    document: str = ""

    @property
    def profiles(self) -> list[str]:
        return sorted({item.profile for item in self.ecosystems if item.profile})

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "document": self.document,
            "profiles": self.profiles,
            "ecosystems": [vars(item) for item in self.ecosystems],
            "commands": [vars(item) for item in self.commands],
            "facts": [vars(item) for item in self.facts],
            "scopes": [vars(item) for item in self.scopes],
            "modules": [item.as_rule() | {"evidence": item.evidence} for item in self.modules],
            "entry_points": self.entry_points,
            "open_questions": self.open_questions,
        }
