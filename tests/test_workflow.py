from __future__ import annotations

import json
import tempfile
import unittest
import subprocess
from pathlib import Path

from tooling.workflow import main
from tooling.workflow_features.architecture import check_architecture
from tooling.workflow_features.findings import create_finding, transition_finding, validate_findings
from tooling.workflow_features.integration import (
    entry_point_warnings,
    install_git_hooks,
    sync_entry_points,
)
from tooling.workflow_features.reporting import build_report
from tooling.workflow_features.maintenance import doctor, migrate
from tooling.workflow_features.local_runtime import build_dashboard, run_verification
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
from tooling.workflow_features.specs import (
    add_requirement_set,
    create_spec,
    generate_plan,
    generate_tasks,
    link_requirement,
    transition_spec,
    validate_specs,
)


class SpecWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / ".agent" / "specs").mkdir(parents=True)
        (self.project / ".agent" / "config").mkdir(parents=True)
        (self.project / ".agent" / "config" / "scopes.json").write_text(
            json.dumps({"schema_version": 1, "project": {"context": []}, "scopes": []}), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def complete_spec(self, spec_id: str) -> Path:
        directory = create_spec(self.project, spec_id, "Checkout", "Product")
        manifest = directory / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["requirements"][0]["statement"] = "A customer can complete checkout"
        spec["requirements"][0]["acceptance_evidence"] = ["Checkout integration test"]
        spec["scope"] = {"in": ["Card checkout"], "out": ["Refunds"]}
        manifest.write_text(json.dumps(spec), encoding="utf-8")
        generate_plan(self.project, spec_id)
        generate_tasks(self.project, spec_id)
        return directory

    def test_create_spec_scaffolds_owned_artifacts(self) -> None:
        directory = create_spec(self.project, "customer-checkout", "Checkout", "Product")

        self.assertEqual(
            {"plan.md", "spec.json", "spec.md", "tasks.md", "traceability.json"},
            {path.name for path in directory.iterdir()},
        )

    def test_acceptance_requires_complete_requirement(self) -> None:
        create_spec(self.project, "customer-checkout", "Checkout", "Product")

        with self.assertRaisesRegex(ValueError, "missing statement"):
            transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

    def test_lifecycle_and_report(self) -> None:
        directory = self.complete_spec("customer-checkout")

        transition_spec(self.project, "customer-checkout", "Accepted", "Product", [])
        (self.project / "src").mkdir()
        (self.project / "tests").mkdir()
        (self.project / "src" / "checkout.py").write_text("", encoding="utf-8")
        (self.project / "tests" / "test_checkout.py").write_text("", encoding="utf-8")
        (directory / "traceability.json").write_text(
            json.dumps(
                {
                    "spec_id": "customer-checkout",
                    "links": [
                        {
                            "requirement_id": "REQ-001",
                            "task_ids": ["TASK-001"],
                            "code_paths": ["src/checkout.py"],
                            "test_paths": ["tests/test_checkout.py"],
                            "evidence": ["CI run 42"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        transition_spec(self.project, "customer-checkout", "Implemented", "Engineering", ["CI run 42"])

        report = build_report(self.project)
        self.assertEqual("Implemented", report["specs"][0]["status"])
        self.assertEqual(100, report["specs"][0]["traceability_percent"])

    def test_a_project_that_uses_no_specs_still_validates(self) -> None:
        import shutil

        shutil.rmtree(self.project / ".agent" / "specs")

        self.assertEqual([], validate_specs(self.project))
        self.assertEqual(0, main(["--project", str(self.project), "validate"]))

    def test_proposed_draft_passes_validation_but_cannot_be_accepted(self) -> None:
        create_spec(self.project, "customer-checkout", "Checkout", "Product")

        self.assertEqual(0, main(["--project", str(self.project), "validate"]))
        with self.assertRaisesRegex(ValueError, "missing statement"):
            transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

    def test_report_counts_requirements_from_every_requirement_file(self) -> None:
        self.complete_spec("checkout-platform")
        requirement_set = add_requirement_set(
            self.project, "checkout-platform", "payment-rules", "Payment rules"
        )
        bundle = json.loads(requirement_set.read_text(encoding="utf-8"))
        bundle["requirements"][0]["statement"] = "Rejected payments preserve the basket"
        bundle["requirements"][0]["acceptance_evidence"] = ["Rejected payment test"]
        requirement_set.write_text(json.dumps(bundle), encoding="utf-8")
        generate_plan(self.project, "checkout-platform")
        generate_tasks(self.project, "checkout-platform")
        (self.project / "src").mkdir(exist_ok=True)
        (self.project / "tests").mkdir(exist_ok=True)
        (self.project / "src" / "checkout.py").write_text("", encoding="utf-8")
        (self.project / "tests" / "test_checkout.py").write_text("", encoding="utf-8")
        trace = self.project / ".agent" / "specs" / "checkout-platform" / "traceability.json"
        trace.write_text(
            json.dumps(
                {
                    "spec_id": "checkout-platform",
                    "links": [
                        {
                            "requirement_id": "REQ-001",
                            "task_ids": ["TASK-001"],
                            "code_paths": ["src/checkout.py"],
                            "test_paths": ["tests/test_checkout.py"],
                            "evidence": ["CI run 42"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        report = build_report(self.project)["specs"][0]

        self.assertEqual(2, report["requirements"])
        self.assertEqual(1, report["traceability_covered"])
        self.assertEqual(50, report["traceability_percent"])

    def test_long_spec_aggregates_multiple_requirement_files(self) -> None:
        directory = self.complete_spec("checkout-platform")

        requirement_set = add_requirement_set(
            self.project, "checkout-platform", "payment-rules", "Payment rules"
        )
        bundle = json.loads(requirement_set.read_text(encoding="utf-8"))
        bundle["requirements"][0]["statement"] = "Rejected payments preserve the basket"
        bundle["requirements"][0]["acceptance_evidence"] = ["Rejected payment test"]
        requirement_set.write_text(json.dumps(bundle), encoding="utf-8")
        generate_plan(self.project, "checkout-platform")
        tasks = generate_tasks(self.project, "checkout-platform").read_text(encoding="utf-8")

        self.assertIn("REQ-001", tasks)
        self.assertIn("REQ-002", tasks)
        self.assertEqual([], validate_specs(self.project))
        manifest = json.loads((directory / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(["requirements/payment-rules.json"], manifest["requirement_files"])


    def test_undefined_scope_statement_blocks_acceptance(self) -> None:
        directory = create_spec(self.project, "customer-checkout", "Checkout", "Product")
        manifest = directory / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["requirements"][0]["statement"] = "A customer can complete checkout"
        spec["requirements"][0]["acceptance_evidence"] = ["Checkout integration test"]
        manifest.write_text(json.dumps(spec), encoding="utf-8")
        generate_plan(self.project, "customer-checkout")
        generate_tasks(self.project, "customer-checkout")

        with self.assertRaisesRegex(ValueError, "scope 'in' is not defined"):
            transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

    def test_unowned_assumption_blocks_acceptance(self) -> None:
        directory = self.complete_spec("customer-checkout")
        manifest = directory / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["assumptions"] = [{"statement": "Orders settle within a day"}]
        manifest.write_text(json.dumps(spec), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "needs an owner or a validation method"):
            transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

    def test_complete_assumption_is_accepted(self) -> None:
        directory = self.complete_spec("customer-checkout")
        manifest = directory / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["assumptions"] = [
            {
                "statement": "Orders settle within a day",
                "owner": "Payments",
                "consequence": "Cancellation window is wrong",
            }
        ]
        manifest.write_text(json.dumps(spec), encoding="utf-8")

        transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

        self.assertEqual(
            "Accepted", json.loads(manifest.read_text(encoding="utf-8"))["status"]
        )

    def test_unresolved_open_decision_blocks_acceptance(self) -> None:
        directory = self.complete_spec("customer-checkout")
        manifest = directory / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["open_decisions"] = [{"question": "Do we refund shipping?", "impact": "billing"}]
        manifest.write_text(json.dumps(spec), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unresolved"):
            transition_spec(self.project, "customer-checkout", "Accepted", "Owner", [])

    def test_link_requirement_builds_traceability_incrementally(self) -> None:
        self.complete_spec("customer-checkout")
        (self.project / "src").mkdir()
        (self.project / "tests").mkdir()
        (self.project / "src" / "checkout.py").write_text("", encoding="utf-8")
        (self.project / "tests" / "test_checkout.py").write_text("", encoding="utf-8")

        partial = link_requirement(
            self.project, "customer-checkout", "REQ-001", ["TASK-001"], ["src/checkout.py"], [], []
        )
        self.assertFalse(partial["complete"])
        self.assertEqual(["test_paths", "evidence"], partial["missing"])

        complete = link_requirement(
            self.project,
            "customer-checkout",
            "REQ-001",
            [],
            [],
            ["tests/test_checkout.py"],
            ["CI run 42"],
        )

        self.assertTrue(complete["complete"])
        self.assertEqual(["TASK-001"], complete["link"]["task_ids"])
        self.assertEqual(["src/checkout.py"], complete["link"]["code_paths"])

    def test_link_requirement_rejects_files_and_tasks_that_do_not_exist(self) -> None:
        self.complete_spec("customer-checkout")

        with self.assertRaisesRegex(ValueError, "file does not exist: src/missing.py"):
            link_requirement(
                self.project, "customer-checkout", "REQ-001", ["TASK-001"], ["src/missing.py"], [], []
            )
        with self.assertRaisesRegex(ValueError, "TASK-999 does not appear in tasks.md"):
            link_requirement(self.project, "customer-checkout", "REQ-001", ["TASK-999"], [], [], [])
        with self.assertRaisesRegex(ValueError, "Unknown requirement"):
            link_requirement(self.project, "customer-checkout", "REQ-404", [], [], [], [])


class ArchitectureTests(unittest.TestCase):
    def test_forbidden_dependency_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            domain = project / "src" / "Orders" / "Domain"
            infrastructure = project / "src" / "Orders" / "Infrastructure"
            config = project / ".agent" / "config"
            domain.mkdir(parents=True)
            infrastructure.mkdir(parents=True)
            config.mkdir(parents=True)
            (domain / "order.py").write_text("from orders.infrastructure.store import Store\n", encoding="utf-8")
            (config / "architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/Orders/Domain",
                                "import_prefixes": ["orders.domain"],
                                "may_depend_on": [],
                            },
                            {
                                "name": "infrastructure",
                                "path": "src/Orders/Infrastructure",
                                "import_prefixes": ["orders.infrastructure"],
                                "may_depend_on": ["domain"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            violations = check_architecture(project).violations

            self.assertEqual(1, len(violations))
            self.assertIn("domain may not depend on infrastructure", violations[0])

    def test_generic_boundaries_cover_multiple_technology_stacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            domain = project / "src" / "domain"
            infrastructure = project / "src" / "infrastructure"
            config = project / ".agent" / "config"
            domain.mkdir(parents=True)
            infrastructure.mkdir(parents=True)
            config.mkdir(parents=True)
            (domain / "order.dart").write_text("import 'package:infra/store.dart';\n", encoding="utf-8")
            (domain / "order.ts").write_text("import {Store} from '@infra/store';\n", encoding="utf-8")
            (domain / "order.rs").write_text("use infra::store::Store;\n", encoding="utf-8")
            (config / "architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/domain",
                                "import_prefixes": ["domain"],
                                "may_depend_on": [],
                            },
                            {
                                "name": "infrastructure",
                                "path": "src/infrastructure",
                                "import_prefixes": ["package:infra", "@infra", "infra::"],
                                "may_depend_on": ["domain"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            violations = check_architecture(project).violations

            self.assertEqual(3, len(violations))


    def test_comment_prose_is_not_treated_as_a_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            domain = project / "src" / "domain"
            config = project / ".agent" / "config"
            domain.mkdir(parents=True)
            (project / "src" / "infrastructure").mkdir(parents=True)
            config.mkdir(parents=True)
            (domain / "order.ts").write_text("/** Callers should use infrastructure adapters, never the DB. */\nexport class Order {}\n", encoding="utf-8")
            (domain / "order.py").write_text("# We deliberately do not use infrastructure.store here.\nVALUE = 1\n", encoding="utf-8")
            config.joinpath("architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/domain",
                                "import_prefixes": ["domain"],
                                "may_depend_on": [],
                            },
                            {
                                "name": "infrastructure",
                                "path": "src/infrastructure",
                                "import_prefixes": ["infrastructure"],
                                "may_depend_on": ["domain"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = check_architecture(project)

            self.assertEqual([], report.violations)
            self.assertEqual(2, report.files_scanned)

    def test_real_import_is_still_reported_next_to_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            domain = project / "src" / "domain"
            config = project / ".agent" / "config"
            domain.mkdir(parents=True)
            (project / "src" / "infrastructure").mkdir(parents=True)
            config.mkdir(parents=True)
            (domain / "order.py").write_text("# We deliberately do not use infrastructure.store here.\nVALUE = 1\n" + "import infrastructure.store" + chr(10), encoding="utf-8")
            config.joinpath("architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/domain",
                                "import_prefixes": ["domain"],
                                "may_depend_on": [],
                            },
                            {
                                "name": "infrastructure",
                                "path": "src/infrastructure",
                                "import_prefixes": ["infrastructure"],
                                "may_depend_on": ["domain"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = check_architecture(project)

            self.assertEqual(
                ["src/domain/order.py: domain may not depend on infrastructure (infrastructure.store)"],
                report.violations,
            )

    def test_ignored_directories_are_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            dependencies = project / "src" / "domain" / "node_modules" / "package"
            config = project / ".agent" / "config"
            dependencies.mkdir(parents=True)
            (project / "src" / "infrastructure").mkdir(parents=True)
            config.mkdir(parents=True)
            (dependencies / "index.js").write_text("import x from 'infrastructure/thing';\n", encoding="utf-8")
            config.joinpath("architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/domain",
                                "import_prefixes": ["domain"],
                                "may_depend_on": [],
                            },
                            {
                                "name": "infrastructure",
                                "path": "src/infrastructure",
                                "import_prefixes": ["infrastructure"],
                                "may_depend_on": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = check_architecture(project)

            self.assertEqual(0, report.files_scanned)
            self.assertEqual([], report.violations)

    def test_unconfigured_rules_are_reported_instead_of_passing_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config = project / ".agent" / "config"
            config.mkdir(parents=True)
            config.joinpath("architecture.json").write_text(
                json.dumps({"schema_version": 1, "modules": []}), encoding="utf-8"
            )

            report = check_architecture(project)

            self.assertEqual("unconfigured", report.status)
            self.assertEqual([], report.blocking)
            self.assertIn("nothing was checked", report.summary())

    def test_module_path_that_does_not_exist_is_a_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            config = project / ".agent" / "config"
            config.mkdir(parents=True)
            config.joinpath("architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "modules": [
                            {
                                "name": "domain",
                                "path": "src/Features/Example/Domain",
                                "import_prefixes": ["domain"],
                                "may_depend_on": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = check_architecture(project)

            self.assertEqual(
                ["domain: configured path does not exist: src/Features/Example/Domain"],
                report.configuration_errors,
            )


class RoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        agent = self.project / ".agent"
        (agent / "config").mkdir(parents=True)
        (agent / "specs").mkdir()
        for reference in ("PROJECT.md", "web.md", "checkout.md", "api.md", "mobile.md"):
            (agent / reference).write_text(reference, encoding="utf-8")
        config = {
            "schema_version": 1,
            "project": {"id": "commerce", "context": [".agent/PROJECT.md"]},
            "scopes": [
                {
                    "id": "frontend",
                    "parent": None,
                    "paths": ["apps/web"],
                    "context": [".agent/web.md"],
                },
                {
                    "id": "frontend-checkout",
                    "parent": "frontend",
                    "paths": ["apps/web/src/checkout"],
                    "context": [".agent/checkout.md"],
                },
                {"id": "api", "parent": None, "paths": ["apps/api"], "context": [".agent/api.md"]},
                {
                    "id": "mobile",
                    "parent": None,
                    "paths": ["apps/mobile"],
                    "context": [".agent/mobile.md"],
                    "depends_on": ["api"],
                    "verification": [{"operation": "test", "command": "mobile-test"}],
                },
            ],
        }
        (agent / "config" / "scopes.json").write_text(json.dumps(config), encoding="utf-8")
        create_spec(self.project, "checkout", "Checkout", "Product", ["frontend-checkout", "api"])

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_nested_scope_inherits_project_and_parent_context(self) -> None:
        route = resolve_route(self.project, "apps/web/src/checkout/page.tsx")

        self.assertEqual(["frontend", "frontend-checkout"], route["scope_chain"])
        self.assertEqual(
            [".agent/PROJECT.md", ".agent/web.md", ".agent/checkout.md"], route["context"]
        )
        self.assertEqual(["checkout"], route["specs"])

    def test_route_selects_workflow_from_intent(self) -> None:
        route = resolve_route(self.project, "apps/web/src/checkout/page.tsx", "bugfix")

        self.assertEqual("bugfix", route["intent"])
        self.assertEqual(
            ".agent/vendor/universal-agent-workflow/workflows/bugfix.md", route["workflow"]
        )

    def test_task_intent_inference_is_lightweight_and_multilingual(self) -> None:
        self.assertEqual("review", infer_intent("راجع تصميم واجهة الدفع"))
        self.assertEqual("bugfix", infer_intent("Fix the checkout regression"))
        self.assertEqual("feature", infer_intent("Add customer cancellation"))

    def test_api_and_mobile_are_routed_independently(self) -> None:
        api = resolve_route(self.project, "apps/api/src/orders.py")
        mobile = resolve_route(self.project, "apps/mobile/lib/orders.dart")

        self.assertEqual(["api"], api["scope_chain"])
        self.assertEqual(["checkout"], api["specs"])
        self.assertEqual(["mobile"], mobile["scope_chain"])
        self.assertEqual([], mobile["specs"])

    def test_index_contains_scopes_and_spec_ownership(self) -> None:
        index = build_index(self.project)

        self.assertEqual(4, len(index["scopes"]))
        self.assertEqual(["frontend-checkout", "api"], index["specs"][0]["scope_ids"])
        self.assertTrue((self.project / ".agent" / "INDEX.json").is_file())
        self.assertTrue((self.project / ".agent" / "INDEX.md").is_file())
        self.assertTrue((self.project / ".agent" / "scopes" / "api" / "INDEX.json").is_file())

    def test_overlapping_unrelated_scopes_are_rejected(self) -> None:
        config_path = self.project / ".agent" / "config" / "scopes.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["scopes"].append(
            {"id": "other", "parent": None, "paths": ["apps/web/src"], "context": []}
        )
        config_path.write_text(json.dumps(config), encoding="utf-8")

        errors = validate_routing(self.project)

        self.assertTrue(any("Overlapping paths" in error for error in errors))

    def test_impact_includes_downstream_scopes_and_verification(self) -> None:
        impact = analyze_impact(self.project, ["apps/api/orders.py"])

        self.assertEqual(["api"], impact["direct_scopes"])
        self.assertEqual(["api", "mobile"], impact["impacted_scopes"])
        self.assertEqual(
            [{"scope": "mobile", "operation": "test", "command": "mobile-test"}],
            impact["verification"],
        )

    def test_index_drift_is_detected(self) -> None:
        build_index(self.project)
        self.assertIsNone(check_index(self.project))
        manifest = self.project / ".agent" / "specs" / "checkout" / "spec.json"
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        spec["title"] = "Changed checkout"
        manifest.write_text(json.dumps(spec), encoding="utf-8")

        self.assertEqual("Project index is stale; run build-index", check_index(self.project))

    def test_legacy_json_files_are_migrated(self) -> None:
        config = self.project / ".agent" / "config" / "scopes.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value.pop("schema_version")
        config.write_text(json.dumps(value), encoding="utf-8")

        changed = migrate(self.project)

        self.assertIn(".agent/config/scopes.json", changed)
        migrated = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(1, migrated["schema_version"])


class ScopeKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        config = self.project / ".agent" / "config"
        config.mkdir(parents=True)
        (config / "scopes.json").write_text(
            json.dumps({"schema_version": 1, "project": {"context": []}, "scopes": []}), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_scope_builds_business_knowledge_base_and_route_context(self) -> None:
        directory = create_scope(
            self.project, "orders", "Orders", "business", ["src/Features/Orders"], None
        )

        self.assertEqual(
            {"PROFILE.md", "STATE.md", "DECISIONS.md", "CHANGES.md"},
            {path.name for path in directory.iterdir()},
        )
        profile = (directory / "PROFILE.md").read_text(encoding="utf-8")
        state = (directory / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("Business rules and invariants", profile)
        self.assertIn("Active business variables", state)
        route = resolve_route(self.project, "src/Features/Orders/Domain/order.py")
        self.assertIn(".agent/scopes/orders/PROFILE.md", route["context"])
        self.assertIn(".agent/scopes/orders/CHANGES.md", route["context"])

    def test_record_change_preserves_classification_and_impact(self) -> None:
        create_scope(self.project, "orders", "Orders", "business", ["src/Orders"], None)

        path = record_scope_change(
            self.project,
            "orders",
            "Cancellation boundary changed",
            "Product",
            "replacement",
            ["API", "mobile", "tests"],
        )

        change_log = path.read_text(encoding="utf-8")
        self.assertIn("Classification: replacement", change_log)
        self.assertIn("Impact: API, mobile, tests", change_log)


class FindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        config = self.project / ".agent" / "config"
        config.mkdir(parents=True)
        (self.project / ".agent" / "specs").mkdir()
        (config / "scopes.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "project": {"context": []},
                    "scopes": [
                        {"id": "api", "parent": None, "paths": ["apps/api"], "context": []}
                    ],
                }
            ),
            encoding="utf-8",
        )
        create_spec(self.project, "orders", "Orders", "Product", ["api"])

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_bug_and_discovery_are_indexed_and_routed(self) -> None:
        bug = create_finding(
            self.project,
            "bug",
            "duplicate-order",
            "Duplicate order",
            "Support",
            "high",
            ["api"],
            ["orders"],
        )
        discovery = create_finding(
            self.project,
            "discovery",
            "provider-limit",
            "Provider rate limit",
            "Engineering",
            "medium",
            ["api"],
            [],
        )

        self.assertTrue((bug / "evidence.md").is_file())
        self.assertTrue((discovery / "details.md").is_file())
        self.assertEqual([], validate_findings(self.project))
        route = resolve_route(self.project, "apps/api/orders.py")
        self.assertEqual(["duplicate-order", "provider-limit"], route["findings"])
        index = build_index(self.project)
        self.assertEqual(2, len(index["findings"]))

        transition_finding(
            self.project, "bug", "duplicate-order", "Triaged", "Engineering", []
        )
        transition_finding(
            self.project,
            "bug",
            "duplicate-order",
            "Resolved",
            "Engineering",
            ["Regression test passed"],
        )
        resolved = json.loads((bug / "finding.json").read_text(encoding="utf-8"))
        self.assertEqual("Resolved", resolved["status"])


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        agent = self.project / ".agent"
        (agent / "config").mkdir(parents=True)
        (agent / "specs").mkdir()
        (agent / "ROUTER.md").write_text("router", encoding="utf-8")
        (agent / "PROJECT.md").write_text("- Purpose: TODO\n- Users: TODO\n", encoding="utf-8")
        (agent / "COMMANDS.md").write_text("| Build | TODO |\n", encoding="utf-8")
        (agent / "config" / "scopes.json").write_text(
            json.dumps({"schema_version": 1, "project": {"context": []}, "scopes": []}), encoding="utf-8"
        )
        (agent / "config" / "local.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "command_timeout_seconds": 30,
                    "max_output_characters": 2000,
                    "runs_directory": ".agent/runs",
                    "dashboard_path": ".agent/dashboard.html",
                }
            ),
            encoding="utf-8",
        )
        (agent / "config" / "architecture.json").write_text(
            json.dumps({"schema_version": 1, "modules": []}), encoding="utf-8"
        )
        build_index(self.project)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_unfilled_templates_warn_without_failing(self) -> None:
        report = doctor(self.project)

        self.assertTrue(report.passed)
        self.assertEqual([], report.errors)
        self.assertIn(".agent/COMMANDS.md: 1 unfilled placeholder(s)", report.warnings)
        self.assertIn(".agent/PROJECT.md: 2 unfilled placeholder(s)", report.warnings)
        self.assertTrue(
            any("declares no modules" in warning for warning in report.warnings)
        )


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / ".agent" / "config").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_entry_points_are_created_for_tools_that_ignore_agents_md(self) -> None:
        result = sync_entry_points(self.project)

        self.assertIn("CLAUDE.md", result["created"])
        self.assertIn(".github/copilot-instructions.md", result["created"])
        for relative in result["created"]:
            self.assertIn("AGENTS.md", (self.project / relative).read_text(encoding="utf-8"))
        cursor = self.project / ".cursor" / "rules" / "agent-workflow.mdc"
        self.assertTrue(cursor.read_text(encoding="utf-8").startswith("---"))
        self.assertEqual([], entry_point_warnings(self.project))

    def test_existing_entry_points_are_never_overwritten(self) -> None:
        (self.project / "CLAUDE.md").write_text("my own instructions", encoding="utf-8")

        result = sync_entry_points(self.project)

        self.assertIn("CLAUDE.md", result["left_alone"])
        self.assertNotIn("CLAUDE.md", result["created"])
        self.assertEqual("my own instructions", (self.project / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(
            ["CLAUDE.md exists but does not point at AGENTS.md"], entry_point_warnings(self.project)
        )

    def test_configured_entry_points_replace_the_defaults(self) -> None:
        (self.project / ".agent" / "config" / "workflow.json").write_text(
            json.dumps({"schema_version": 1, "entry_points": ["AGENT_NOTES.md"]}), encoding="utf-8"
        )

        result = sync_entry_points(self.project)

        self.assertEqual(["AGENT_NOTES.md"], result["created"])
        self.assertFalse((self.project / "CLAUDE.md").exists())

    def test_hook_is_installed_and_rebuilding_it_is_idempotent(self) -> None:
        subprocess.run(["git", "init"], cwd=self.project, capture_output=True, check=True)

        path = install_git_hooks(self.project)

        self.assertTrue(path.is_file())
        self.assertIn("build-index", path.read_text(encoding="utf-8"))
        self.assertEqual(path, install_git_hooks(self.project))

    def test_a_foreign_pre_commit_hook_is_not_replaced_without_force(self) -> None:
        subprocess.run(["git", "init"], cwd=self.project, capture_output=True, check=True)
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")

        with self.assertRaisesRegex(FileExistsError, "already exists"):
            install_git_hooks(self.project)
        self.assertIn("echo mine", hook.read_text(encoding="utf-8"))

        install_git_hooks(self.project, force=True)

        self.assertIn("build-index", hook.read_text(encoding="utf-8"))

    def test_hook_installation_requires_a_repository(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "Not a Git repository"):
            install_git_hooks(self.project)


class LocalRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        config = self.project / ".agent" / "config"
        config.mkdir(parents=True)
        (self.project / ".agent" / "specs").mkdir()
        (config / "scopes.json").write_text(
            json.dumps({"schema_version": 1, "project": {"context": []}, "scopes": []}),
            encoding="utf-8",
        )
        (config / "local.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "command_timeout_seconds": 30,
                    "max_output_characters": 2000,
                    "runs_directory": ".agent/runs",
                    "dashboard_path": ".agent/dashboard.html",
                }
            ),
            encoding="utf-8",
        )
        create_scope(
            self.project,
            "web",
            "Web",
            "application",
            ["apps/web"],
            None,
            [],
            [{"operation": "smoke", "command": "python -c \"print('verified')\""}],
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_local_verification_runs_configured_commands_and_saves_evidence(self) -> None:
        impact = analyze_impact(self.project, ["apps/web/page.ts"])

        report = run_verification(self.project, impact["verification"])

        self.assertTrue(report["passed"])
        self.assertIn("verified", report["results"][0]["stdout"])
        self.assertTrue((self.project / report["report_path"]).is_file())

    def test_dashboard_is_generated_for_local_viewing(self) -> None:
        build_index(self.project)

        path = build_dashboard(self.project)

        self.assertTrue(path.is_file())
        self.assertIn("Local workflow dashboard", path.read_text(encoding="utf-8"))

    def test_git_routing_includes_untracked_and_staged_files(self) -> None:
        subprocess.run(["git", "init"], cwd=self.project, capture_output=True, check=True)
        source = self.project / "apps" / "web"
        source.mkdir(parents=True)
        (source / "untracked.ts").write_text("", encoding="utf-8")
        (source / "staged.ts").write_text("", encoding="utf-8")
        subprocess.run(["git", "add", "apps/web/staged.ts"], cwd=self.project, check=True)

        impact = resolve_git_changes(self.project)

        self.assertIn("apps/web/staged.ts", impact["changed_paths"])
        self.assertIn("apps/web/untracked.ts", impact["changed_paths"])
        self.assertEqual(["web"], impact["direct_scopes"])


if __name__ == "__main__":
    unittest.main()
