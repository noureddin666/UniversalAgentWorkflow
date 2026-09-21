from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


VENDOR_DIRECTORIES = ("core", "workflows", "profiles", "tooling")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely update an installed Universal Agent Workflow vendor bundle")
    parser.add_argument("project_path", type=Path)
    parser.add_argument("--migrate", action="store_true")
    return parser.parse_args()


REQUIRED_IGNORES = ("/runs/", "/backups/", "/dashboard.html", "__pycache__/", "*.pyc")


def _ensure_ignored(path: Path) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    missing = [entry for entry in REQUIRED_IGNORES if entry not in existing]
    if missing:
        path.write_text("\n".join(existing + missing).strip() + "\n", encoding="utf-8")


def update(project_path: Path, migrate: bool) -> Path:
    package_root = Path(__file__).resolve().parent.parent
    project_root = project_path.expanduser().resolve(strict=True)
    agent_root = project_root / ".agent"
    vendor_root = agent_root / "vendor" / "universal-agent-workflow"
    if not vendor_root.is_dir():
        raise FileNotFoundError(f"Installed vendor bundle not found: {vendor_root}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = agent_root / "backups" / f"universal-agent-workflow-{timestamp}"
    staging = agent_root / "vendor" / f".universal-agent-workflow-{timestamp}"
    if backup.exists() or staging.exists():
        raise FileExistsError("Update target already exists; retry after the current UTC second")
    staging.mkdir(parents=True)
    try:
        for directory in VENDOR_DIRECTORIES:
            shutil.copytree(
                package_root / directory,
                staging / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        for filename in ("VERSION", "LICENSE", "MANUAL.md", "GUIDE.ar.md"):
            shutil.copy2(package_root / filename, staging / filename)
        backup.parent.mkdir(parents=True, exist_ok=True)
        vendor_root.rename(backup)
        staging.rename(vendor_root)
    except Exception:
        if not vendor_root.exists() and backup.exists():
            backup.rename(vendor_root)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    if migrate:
        template_agent = package_root / "template" / ".agent"
        for relative in ("LOCAL.md", "workflow.cmd", "workflow.ps1", "workflow.sh", "config/local.json"):
            source = template_agent / relative
            target = agent_root / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        _ensure_ignored(agent_root / ".gitignore")
        result = subprocess.run(
            [sys.executable, str(agent_root / "workflow.py"), "--project", str(project_root), "migrate"],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Vendor updated, but migration failed; backup retained at {backup}")
    return backup


if __name__ == "__main__":
    arguments = parse_args()
    print(f"Updated workflow; backup: {update(arguments.project_path, arguments.migrate)}")
