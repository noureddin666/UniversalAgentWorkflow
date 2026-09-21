from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Universal Agent Workflow into an existing repository."
    )
    parser.add_argument("project_path", type=Path)
    return parser.parse_args()


def copy_directory(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def install(project_path: Path) -> None:
    package_root = Path(__file__).resolve().parent.parent
    template_root = package_root / "template"
    project_root = project_path.expanduser().resolve(strict=True)
    agents_target = project_root / "AGENTS.md"
    agent_target = project_root / ".agent"

    existing = [path for path in (agents_target, agent_target) if path.exists()]
    if existing:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Installation stopped because these paths exist: {paths}")

    shutil.copy2(template_root / "AGENTS.md", agents_target)
    copy_directory(template_root / ".agent", agent_target)

    vendor_target = agent_target / "vendor" / "universal-agent-workflow"
    vendor_target.mkdir(parents=True)
    for directory in ("core", "workflows", "profiles", "tooling"):
        copy_directory(package_root / directory, vendor_target / directory)
    for filename in ("VERSION", "LICENSE", "MANUAL.md", "GUIDE.ar.md"):
        shutil.copy2(package_root / filename, vendor_target / filename)

    github_workflows = project_root / ".github" / "workflows"
    github_workflows.mkdir(parents=True, exist_ok=True)
    workflow_source = template_root / ".github" / "workflows" / "agent-workflow.yml"
    workflow_target = github_workflows / "agent-workflow.yml"
    if not workflow_target.exists():
        shutil.copy2(workflow_source, workflow_target)

    print(f"Installed Universal Agent Workflow into {project_root}")
    print(f"Next: cd {project_root}")
    print("      python .agent/workflow.py setup --ask   (fills what the repository proves, asks you the rest)")
    print("Optional: python .agent/workflow.py install-hooks   (keep .agent/INDEX.json current)")


if __name__ == "__main__":
    install(parse_args().project_path)
