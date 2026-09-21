from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS
from tooling.workflow_features.specs import load_spec_requirements


def build_report(project_root: Path) -> dict[str, Any]:
    specs_root = PATHS.agent_root(project_root) / PATHS.specs_directory
    report: dict[str, Any] = {"specs": [], "summary": {}}
    counts: dict[str, int] = {}
    for manifest in sorted(specs_root.glob("*/spec.json")):
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        directory = manifest.parent
        trace_path = directory / "traceability.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.is_file() else {"links": []}
        try:
            requirements = {item["id"] for item in load_spec_requirements(directory, spec)}
            complete = True
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError):
            requirements = {item["id"] for item in spec.get("requirements", []) if item.get("id")}
            complete = False
        linked = {
            item.get("requirement_id")
            for item in trace.get("links", [])
            if item.get("task_ids")
            and item.get("code_paths")
            and item.get("test_paths")
            and item.get("evidence")
        }
        covered = len(requirements & linked)
        status = spec.get("status", "Unknown")
        counts[status] = counts.get(status, 0) + 1
        report["specs"].append(
            {
                "id": spec.get("id"),
                "title": spec.get("title"),
                "status": status,
                "requirements": len(requirements),
                "requirements_readable": complete,
                "traceability_covered": covered,
                "traceability_percent": round(covered * 100 / len(requirements)) if requirements else 0,
            }
        )
    report["summary"] = {"total": len(report["specs"]), "by_status": counts}
    return report
