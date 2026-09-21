from __future__ import annotations

import html
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tooling.workflow_config import PATHS, load_local_settings
from tooling.workflow_features.architecture import check_architecture
from tooling.workflow_features.findings import load_findings, validate_findings
from tooling.workflow_features.reporting import build_report
from tooling.workflow_features.routing import check_index, resolve_git_changes, validate_routing
from tooling.workflow_features.specs import validate_specs


def run_verification(project_root: Path, verification: list[dict[str, str]]) -> dict[str, Any]:
    settings = load_local_settings(project_root)
    started = datetime.now(timezone.utc)
    results = []
    for item in verification:
        working_directory = project_root / item.get("working_directory", ".")
        began = time.monotonic()
        try:
            process = subprocess.run(
                item["command"],
                cwd=working_directory,
                capture_output=True,
                text=True,
                shell=True,
                timeout=settings.command_timeout_seconds,
                check=False,
            )
            result = {
                **item,
                "exit_code": process.returncode,
                "duration_seconds": round(time.monotonic() - began, 3),
                "stdout": process.stdout[-settings.max_output_characters :],
                "stderr": process.stderr[-settings.max_output_characters :],
                "passed": process.returncode == 0,
            }
        except subprocess.TimeoutExpired as error:
            result = {
                **item,
                "exit_code": None,
                "duration_seconds": round(time.monotonic() - began, 3),
                "stdout": (error.stdout or "")[-settings.max_output_characters :],
                "stderr": (error.stderr or "")[-settings.max_output_characters :],
                "passed": False,
                "timed_out": True,
            }
        results.append(result)
    report = {
        "started": started.isoformat(),
        "finished": datetime.now(timezone.utc).isoformat(),
        "passed": all(item["passed"] for item in results),
        "results": results,
    }
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    directory = project_root / settings.runs_directory / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "verification.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = path.relative_to(project_root).as_posix()
    return report


def run_local_check(project_root: Path, base: str | None, execute: bool) -> dict[str, Any]:
    errors = (
        validate_routing(project_root)
        + validate_specs(project_root)
        + validate_findings(project_root)
    )
    errors.extend(check_architecture(project_root).blocking)
    index_error = check_index(project_root)
    if index_error:
        errors.append(index_error)
    impact: dict[str, Any] | None = None
    try:
        impact = resolve_git_changes(project_root, base)
    except ValueError as error:
        errors.append(str(error))
    verification = None
    if execute and impact and impact["verification"]:
        verification = run_verification(project_root, impact["verification"])
        if not verification["passed"]:
            errors.append("One or more local verification commands failed")
    return {"passed": not errors, "errors": sorted(set(errors)), "impact": impact, "verification": verification}


def _traceability_cell(spec: dict[str, Any]) -> str:
    if not spec.get("requirements_readable", True):
        return "unknown &mdash; requirement files could not be read"
    return f"{spec['traceability_percent']}% ({spec['traceability_covered']}/{spec['requirements']})"


def build_dashboard(project_root: Path) -> Path:
    settings = load_local_settings(project_root)
    report = build_report(project_root)
    findings = load_findings(project_root)
    index_path = PATHS.agent_root(project_root) / PATHS.project_index
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {"scopes": []}
    spec_rows = "".join(
        f"<tr><td>{html.escape(str(item['id']))}</td><td>{html.escape(str(item['title']))}</td>"
        f"<td>{html.escape(str(item['status']))}</td>"
        f"<td>{_traceability_cell(item)}</td></tr>"
        for item in report["specs"]
    )
    finding_rows = "".join(
        f"<tr><td>{html.escape(str(item['id']))}</td><td>{html.escape(str(item['type']))}</td>"
        f"<td>{html.escape(str(item['title']))}</td><td>{html.escape(str(item['status']))}</td></tr>"
        for item in findings
    )
    scope_rows = "".join(
        f"<tr><td>{html.escape(str(item['id']))}</td><td>{html.escape(str(item.get('title', '')))}</td>"
        f"<td>{html.escape(', '.join(item.get('paths', [])))}</td></tr>"
        for item in index.get("scopes", [])
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Universal Agent Workflow</title><style>
body{{font:16px system-ui;margin:2rem;max-width:1100px;color:#17202a}}table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th,td{{border-bottom:1px solid #d5d8dc;padding:.65rem;text-align:left}}th{{background:#f4f6f7}}h1,h2{{color:#12344d}}
</style></head><body><h1>Local workflow dashboard</h1>
<p>Generated {html.escape(datetime.now(timezone.utc).isoformat())}</p>
<h2>Scopes</h2><table><tr><th>Id</th><th>Title</th><th>Paths</th></tr>{scope_rows}</table>
<h2>Specs</h2><table><tr><th>Id</th><th>Title</th><th>Status</th><th>Traceability</th></tr>{spec_rows}</table>
<h2>Bugs and discoveries</h2><table><tr><th>Id</th><th>Type</th><th>Title</th><th>Status</th></tr>{finding_rows}</table>
</body></html>"""
    path = project_root / settings.dashboard_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path
