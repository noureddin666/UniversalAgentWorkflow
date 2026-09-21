from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tooling.workflow_config import PATHS, discover_project_root
from tooling.workflow_features.architecture import check_architecture
from tooling.workflow_features.documents import document_outline, find_sections, read_section
from tooling.workflow_features.execution import (
    complete_task,
    next_task,
    replan,
    report as run_report,
    retry_task,
    run_status,
    start_run,
)
from tooling.workflow_features.findings import create_finding, transition_finding, validate_findings
from tooling.workflow_features.integration import install_git_hooks, sync_entry_points
from tooling.workflow_features.maintenance import doctor, migrate
from tooling.workflow_features.onboarding import AdoptionReport, adopt, answer_field, bootstrap, unanswered_fields
from tooling.workflow_features.local_runtime import build_dashboard, run_local_check, run_verification
from tooling.workflow_features.reporting import build_report
from tooling.workflow_features.routing import (
    analyze_impact,
    build_index,
    check_index,
    resolve_git_changes,
    resolve_route,
    infer_intent,
    validate_routing,
)
from tooling.workflow_features.scopes import create_scope, record_scope_change
from tooling.workflow_features.session import (
    WORKFLOW_INTENTS,
    agent_budget,
    clear_handoff,
    context_budget,
    read_handoff,
    validate_handoff,
)
from tooling.workflow_features.specs import (
    add_requirement_set,
    create_spec,
    generate_plan,
    generate_tasks,
    link_requirement,
    sync_spec,
    transition_spec,
    validate_specs,
)


def print_adoption(result: AdoptionReport) -> None:
    print(f"adopted {len(result.facts)} project fact(s): {', '.join(result.facts) or 'none'}")
    print(f"adopted {len(result.commands)} command(s)")
    for command in result.commands:
        print(f"  {command}")
    if result.not_declared:
        print(f"not declared anywhere: {', '.join(result.not_declared)}")
    if result.project_id:
        print(f"project id: {result.project_id}")
    if result.remaining:
        print("still needs a person:")
        for item in result.remaining:
            print(f"  - {item}")


def ask_remaining(project: Path) -> None:
    fields = unanswered_fields(project)
    if not fields:
        return
    print("Answer what only a person knows. Press Enter to skip; type 'unknown' if nobody knows.")
    for field_name in fields:
        try:
            value = input(f"{field_name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print("Stopped asking; the remaining fields stay TODO.")
            return
        if value:
            answer_field(project, field_name, value)


def setup(project: Path, ask: bool) -> int:
    report = bootstrap(project, force=True)
    print(f"{report.document}: {len(report.commands)} command(s), {len(report.facts)} fact(s), {len(report.scopes)} scope(s)")
    print_adoption(adopt(project))
    if ask:
        ask_remaining(project)
    migrate(project)
    build_index(project)
    print(f"dashboard: {build_dashboard(project)}")
    created = sync_entry_points(project)["created"]
    if created:
        print(f"entry points: {', '.join(created)}")
    health = doctor(project)
    for error in health.errors:
        print(f"error: {error}", file=sys.stderr)
    for warning in health.warnings:
        print(f"warning: {warning}")
    return 0 if health.passed else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Manage Universal Agent Workflow specs and quality gates")
    root.add_argument("--project", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-spec")
    create.add_argument("spec_id")
    create.add_argument("--title", required=True)
    create.add_argument("--owner", required=True)
    create.add_argument("--scope", action="append", default=[])
    for name in ("generate-plan", "generate-tasks"):
        command = commands.add_parser(name)
        command.add_argument("spec_id")
    transition = commands.add_parser("transition")
    transition.add_argument("spec_id")
    transition.add_argument("state")
    transition.add_argument("--actor", required=True)
    transition.add_argument("--evidence", action="append", default=[])
    for name in ("validate", "check-architecture"):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true")
    commands.add_parser("build-index")
    route = commands.add_parser("route")
    route.add_argument("path")
    route.add_argument("--intent", choices=WORKFLOW_INTENTS)
    route.add_argument("--task")
    budget = commands.add_parser("context-budget")
    budget.add_argument("path")
    budget.add_argument("--intent", choices=WORKFLOW_INTENTS, required=True)
    document = commands.add_parser("outline")
    document.add_argument("path")
    read = commands.add_parser("read")
    read.add_argument("path")
    read.add_argument("--section")
    find = commands.add_parser("find")
    find.add_argument("query")
    find.add_argument("--path", action="append", default=[])
    find.add_argument("--limit", type=int, default=10)
    run = commands.add_parser("run")
    run_actions = run.add_subparsers(dest="run_action", required=True)
    for name in ("start", "replan", "status", "report"):
        command = run_actions.add_parser(name)
        command.add_argument("spec_id")
        if name == "start":
            command.add_argument("--force", action="store_true")
    run_next = run_actions.add_parser("next")
    run_next.add_argument("spec_id")
    run_retry = run_actions.add_parser("retry")
    run_retry.add_argument("spec_id")
    run_retry.add_argument("task_id")
    run_complete = run_actions.add_parser("complete")
    run_complete.add_argument("spec_id")
    run_complete.add_argument("task_id")
    run_complete.add_argument("--evidence", action="append", default=[])
    run_complete.add_argument("--handoff")
    run_complete.add_argument("--code", action="append", default=[])
    run_complete.add_argument("--test", action="append", default=[])
    run_complete.add_argument("--allow-no-change", action="store_true")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("action", choices=("show", "validate", "clear"))
    agents = commands.add_parser("agent-budget")
    agents.add_argument("--agents", type=int, required=True)
    agents.add_argument("--concurrency", type=int, required=True)
    agents.add_argument("--high-effort", type=int, default=0)
    create_scope_command = commands.add_parser("create-scope")
    create_scope_command.add_argument("scope_id")
    create_scope_command.add_argument("--title", required=True)
    create_scope_command.add_argument("--kind", required=True)
    create_scope_command.add_argument("--path", action="append", required=True)
    create_scope_command.add_argument("--parent")
    create_scope_command.add_argument("--depends-on", action="append", default=[])
    create_scope_command.add_argument("--verify", action="append", default=[])
    change = commands.add_parser("record-scope-change")
    change.add_argument("scope_id")
    change.add_argument("--summary", required=True)
    change.add_argument("--actor", required=True)
    change.add_argument("--classification", required=True)
    change.add_argument("--impact", action="append", default=[])
    finding = commands.add_parser("create-finding")
    finding.add_argument("finding_type", choices=("bug", "discovery"))
    finding.add_argument("finding_id")
    finding.add_argument("--title", required=True)
    finding.add_argument("--reporter", required=True)
    finding.add_argument("--severity", required=True)
    finding.add_argument("--scope", action="append", default=[])
    finding.add_argument("--spec", action="append", default=[])
    link = commands.add_parser("link-requirement")
    link.add_argument("spec_id")
    link.add_argument("requirement_id")
    link.add_argument("--task", action="append", default=[])
    link.add_argument("--code", action="append", default=[])
    link.add_argument("--test", action="append", default=[])
    link.add_argument("--evidence", action="append", default=[])
    requirement_set = commands.add_parser("add-requirement-set")
    requirement_set.add_argument("spec_id")
    requirement_set.add_argument("set_id")
    requirement_set.add_argument("--title", required=True)
    finding_transition = commands.add_parser("transition-finding")
    finding_transition.add_argument("finding_type", choices=("bug", "discovery"))
    finding_transition.add_argument("finding_id")
    finding_transition.add_argument("state")
    finding_transition.add_argument("--actor", required=True)
    finding_transition.add_argument("--evidence", action="append", default=[])
    commands.add_parser("check-index")
    route_changes = commands.add_parser("route-changes")
    route_changes.add_argument("--base")
    impact = commands.add_parser("impact")
    impact.add_argument("path", nargs="+")
    commands.add_parser("migrate")
    doctor_command = commands.add_parser("doctor")
    doctor_command.add_argument("--json", action="store_true")
    sync = commands.add_parser("sync-spec")
    sync.add_argument("spec_id")
    boot = commands.add_parser("bootstrap")
    boot.add_argument("--json", action="store_true")
    boot.add_argument("--force", action="store_true")
    adopt_command = commands.add_parser("adopt")
    adopt_command.add_argument("--json", action="store_true")
    setup_command = commands.add_parser("setup")
    setup_command.add_argument("--ask", action="store_true")
    commands.add_parser("local-init")
    local_check = commands.add_parser("local-check")
    local_check.add_argument("--base")
    local_check.add_argument("--execute", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("path", nargs="*")
    verify.add_argument("--changed", action="store_true")
    verify.add_argument("--base")
    commands.add_parser("sync-entrypoints")
    hooks = commands.add_parser("install-hooks")
    hooks.add_argument("--force", action="store_true")
    commands.add_parser("dashboard")
    report = commands.add_parser("report")
    report.add_argument("--output", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project = args.project.expanduser().resolve() if args.project else discover_project_root()
    try:
        if args.command == "create-spec":
            print(create_spec(project, args.spec_id, args.title, args.owner, args.scope))
        elif args.command == "generate-plan":
            print(generate_plan(project, args.spec_id))
        elif args.command == "generate-tasks":
            print(generate_tasks(project, args.spec_id))
        elif args.command == "transition":
            transition_spec(project, args.spec_id, args.state, args.actor, args.evidence)
        elif args.command == "validate":
            errors = (
                validate_routing(project)
                + validate_specs(project)
                + validate_findings(project)
            )
            if args.json:
                print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
            elif errors:
                print("\n".join(errors), file=sys.stderr)
            if errors:
                return 1
        elif args.command == "check-architecture":
            report = check_architecture(project)
            blocking = report.blocking
            if args.json:
                print(
                    json.dumps(
                        {
                            "status": report.status,
                            "passed": not blocking,
                            "summary": report.summary(),
                            "modules_checked": report.modules_checked,
                            "files_scanned": report.files_scanned,
                            "configuration_errors": report.configuration_errors,
                            "violations": report.violations,
                        },
                        indent=2,
                    )
                )
            else:
                if blocking:
                    print("\n".join(blocking), file=sys.stderr)
                print(report.summary())
            if blocking:
                return 1
        elif args.command == "build-index":
            build_index(project)
            print(PATHS.agent_root(project) / PATHS.project_index)
        elif args.command == "route":
            intent = args.intent or (infer_intent(args.task) if args.task else None)
            result = resolve_route(project, args.path, intent)
            result["intent_inferred"] = args.intent is None and args.task is not None
            print(json.dumps(result, indent=2))
        elif args.command == "context-budget":
            result = context_budget(project, args.path, args.intent)
            print(json.dumps(result, indent=2))
            if result["status"] == "over-limit":
                return 1
        elif args.command == "outline":
            print(json.dumps(document_outline(project, args.path), indent=2))
        elif args.command == "read":
            if args.section:
                print(json.dumps(read_section(project, args.path, args.section), indent=2))
            else:
                print(json.dumps(document_outline(project, args.path), indent=2))
        elif args.command == "find":
            print(json.dumps(find_sections(project, args.query, args.path, args.limit), indent=2))
        elif args.command == "run":
            if args.run_action == "start":
                result = start_run(project, args.spec_id, args.force)
            elif args.run_action == "next":
                result = next_task(project, args.spec_id)
            elif args.run_action == "complete":
                result = complete_task(
                    project,
                    args.spec_id,
                    args.task_id,
                    args.evidence,
                    args.handoff,
                    args.code,
                    args.test,
                    args.allow_no_change,
                )
            elif args.run_action == "retry":
                result = retry_task(project, args.spec_id, args.task_id)
            elif args.run_action == "replan":
                result = replan(project, args.spec_id)
            elif args.run_action == "report":
                result = run_report(project, args.spec_id)
            else:
                result = run_status(project, args.spec_id)
            print(json.dumps(result, indent=2))
            if args.run_action == "complete" and not result["passed"]:
                return 1
        elif args.command == "handoff":
            if args.action == "show":
                print(json.dumps(read_handoff(project), indent=2))
            elif args.action == "clear":
                print(clear_handoff(project))
            else:
                errors = validate_handoff(project)
                print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
                if errors:
                    return 1
        elif args.command == "agent-budget":
            result = agent_budget(project, args.agents, args.concurrency, args.high_effort)
            print(json.dumps(result, indent=2))
            if result["status"] == "over-limit":
                return 1
        elif args.command == "create-scope":
            verification = []
            for value in args.verify:
                if "=" not in value:
                    raise ValueError("Verification must use operation=command")
                operation, command = value.split("=", 1)
                verification.append({"operation": operation, "command": command})
            print(
                create_scope(
                    project,
                    args.scope_id,
                    args.title,
                    args.kind,
                    args.path,
                    args.parent,
                    args.depends_on,
                    verification,
                )
            )
        elif args.command == "record-scope-change":
            print(
                record_scope_change(
                    project,
                    args.scope_id,
                    args.summary,
                    args.actor,
                    args.classification,
                    args.impact,
                )
            )
        elif args.command == "create-finding":
            print(
                create_finding(
                    project,
                    args.finding_type,
                    args.finding_id,
                    args.title,
                    args.reporter,
                    args.severity,
                    args.scope,
                    args.spec,
                )
            )
        elif args.command == "link-requirement":
            print(
                json.dumps(
                    link_requirement(
                        project,
                        args.spec_id,
                        args.requirement_id,
                        args.task,
                        args.code,
                        args.test,
                        args.evidence,
                    ),
                    indent=2,
                )
            )
        elif args.command == "add-requirement-set":
            print(add_requirement_set(project, args.spec_id, args.set_id, args.title))
        elif args.command == "transition-finding":
            transition_finding(
                project,
                args.finding_type,
                args.finding_id,
                args.state,
                args.actor,
                args.evidence,
            )
        elif args.command == "check-index":
            error = check_index(project)
            if error:
                print(error, file=sys.stderr)
                return 1
        elif args.command == "route-changes":
            print(json.dumps(resolve_git_changes(project, args.base), indent=2))
        elif args.command == "impact":
            print(json.dumps(analyze_impact(project, args.path), indent=2))
        elif args.command == "migrate":
            print(json.dumps({"changed": migrate(project)}, indent=2))
        elif args.command == "doctor":
            health = doctor(project)
            if args.json:
                print(
                    json.dumps(
                        {"passed": health.passed, "errors": health.errors, "warnings": health.warnings},
                        indent=2,
                    )
                )
            else:
                if health.errors:
                    print("\n".join(health.errors), file=sys.stderr)
                for warning in health.warnings:
                    print(f"warning: {warning}")
            if not health.passed:
                return 1
        elif args.command == "sync-spec":
            print(sync_spec(project, args.spec_id))
        elif args.command == "bootstrap":
            report = bootstrap(project, args.force)
            if args.json:
                print(json.dumps(report.to_dict(), indent=2))
            else:
                print(report.document)
                print(
                    f"mode={report.mode} "
                    f"commands={len(report.commands)} "
                    f"scopes={len(report.scopes)} "
                    f"modules={len(report.modules)}"
                )
                print("Suggestions only. Confirm each one before it becomes a project fact.")
        elif args.command == "adopt":
            result = adopt(project)
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print_adoption(result)
        elif args.command == "setup":
            return setup(project, args.ask)
        elif args.command == "local-init":
            changed = migrate(project)
            build_index(project)
            dashboard = build_dashboard(project)
            print(json.dumps({"migrated": changed, "dashboard": str(dashboard)}, indent=2))
        elif args.command == "local-check":
            result = run_local_check(project, args.base, args.execute)
            print(json.dumps(result, indent=2))
            if not result["passed"]:
                return 1
        elif args.command == "verify":
            if args.changed:
                impact = resolve_git_changes(project, args.base)
            elif args.path:
                impact = analyze_impact(project, args.path)
            else:
                raise ValueError("verify requires paths or --changed")
            result = run_verification(project, impact["verification"])
            print(json.dumps(result, indent=2))
            if not result["passed"]:
                return 1
        elif args.command == "sync-entrypoints":
            print(json.dumps(sync_entry_points(project), indent=2))
        elif args.command == "install-hooks":
            print(install_git_hooks(project, args.force))
        elif args.command == "dashboard":
            print(build_dashboard(project))
        elif args.command == "report":
            result = json.dumps(build_report(project), indent=2) + "\n"
            if args.output:
                args.output.write_text(result, encoding="utf-8")
            else:
                print(result, end="")
        return 0
    except (FileNotFoundError, FileExistsError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
