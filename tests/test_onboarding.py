from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tooling.workflow import main
from tooling.workflow_features.onboarding import bootstrap
from tooling.workflow_features.onboarding.model import FROM_CI, FROM_CONVENTION, FROM_MANIFEST


class OnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / ".agent" / "config").mkdir(parents=True)
        (self.project / ".agent" / "PROJECT.md").write_text("- Purpose: TODO\n", encoding="utf-8")
        (self.project / ".agent" / "COMMANDS.md").write_text("| Build | TODO |\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def node_monorepo(self) -> None:
        self.write("package.json", json.dumps({"name": "shop", "private": True}))
        self.write("pnpm-lock.yaml", "lockfileVersion: 6.0\n")
        self.write(
            "apps/web/package.json",
            json.dumps({"name": "@shop/web", "scripts": {"build": "next build", "test": "vitest"}}),
        )
        self.write("apps/web/src/index.ts", "export const value = 1\n")
        self.write("packages/ui/package.json", json.dumps({"name": "@shop/ui", "scripts": {"build": "tsup"}}))
        self.write("packages/ui/index.ts", "export const button = 1\n")

    def commands_for(self, report, operation: str) -> list[str]:
        return [item.command for item in report.commands if item.operation == operation]

    def test_bootstrap_writes_only_its_own_document(self) -> None:
        self.node_monorepo()

        report = bootstrap(self.project)

        self.assertEqual(".agent/ONBOARDING.md", report.document)
        self.assertTrue((self.project / ".agent" / "ONBOARDING.md").is_file())
        self.assertIn("TODO", (self.project / ".agent" / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertIn("TODO", (self.project / ".agent" / "COMMANDS.md").read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".agent" / "config" / "architecture.json").exists())
        self.assertFalse((self.project / ".agent" / "config" / "scopes.json").exists())

    def test_detects_package_manager_and_declared_scripts(self) -> None:
        self.node_monorepo()

        report = bootstrap(self.project)

        node = next(item for item in report.ecosystems if item.name == "node")
        self.assertEqual("pnpm", node.package_manager)
        self.assertEqual(["javascript-typescript"], report.profiles)
        self.assertIn("cd apps/web && pnpm run build", self.commands_for(report, "Build"))
        self.assertIn("cd apps/web && pnpm run test", self.commands_for(report, "Unit tests"))

    def test_a_command_proven_by_ci_outranks_the_same_command_derived(self) -> None:
        self.node_monorepo()
        self.write(
            ".github/workflows/ci.yml",
            "jobs:\n  ci:\n    steps:\n      - uses: actions/checkout@v4\n"
            "      - run: pnpm install --frozen-lockfile\n      - run: pnpm run test\n",
        )

        report = bootstrap(self.project)

        restore = next(
            item for item in report.commands if item.command == "pnpm install --frozen-lockfile"
        )
        self.assertEqual(FROM_CI, restore.confidence)
        self.assertEqual(".github/workflows/ci.yml", restore.evidence)

    def test_a_restore_command_is_recognised_even_without_a_keyword(self) -> None:
        self.node_monorepo()
        self.write(
            ".github/workflows/ci.yml",
            "jobs:\n  ci:\n    steps:\n      - run: npm ci\n",
        )

        report = bootstrap(self.project)

        restore = next(item for item in report.commands if item.command == "npm ci")
        self.assertEqual(FROM_CI, restore.confidence)

    def test_the_workflows_own_ci_commands_are_not_suggested(self) -> None:
        self.node_monorepo()
        self.write(
            ".github/workflows/agent-workflow.yml",
            "jobs:\n  gates:\n    steps:\n      - run: python .agent/workflow.py build-index\n",
        )

        report = bootstrap(self.project)

        self.assertNotIn("python .agent/workflow.py build-index", self.commands_for(report, "Build"))

    def test_dependencies_are_never_mistaken_for_project_structure(self) -> None:
        self.node_monorepo()
        self.write("node_modules/left-pad/package.json", json.dumps({"name": "left-pad"}))

        report = bootstrap(self.project)

        self.assertNotIn("left-pad", [scope.title for scope in report.scopes])
        self.assertEqual(["apps-web", "packages-ui"], sorted(scope.scope_id for scope in report.scopes))

    def test_suggested_modules_never_assume_an_allowed_direction(self) -> None:
        self.node_monorepo()

        report = bootstrap(self.project)

        rules = [module.as_rule() for module in report.modules]
        self.assertEqual([[], []], [rule["may_depend_on"] for rule in rules])
        self.assertEqual([["@shop/web"], ["@shop/ui"]], [rule["import_prefixes"] for rule in rules])

    def test_dotnet_projects_use_the_declared_root_namespace(self) -> None:
        self.write("src/App.slnx", "<Solution />")
        self.write(
            "src/Api/Api.csproj",
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
            "<RootNamespace>Shop.Api</RootNamespace></PropertyGroup></Project>",
        )
        self.write("src/Api/Program.cs", "namespace Shop.Api;\n")

        report = bootstrap(self.project)

        module = next(item for item in report.modules if item.path == "src/Api")
        self.assertEqual(("Shop.Api",), module.import_prefixes)
        self.assertIn("dotnet build src/App.slnx --no-restore", self.commands_for(report, "Build"))
        self.assertTrue(all(item.confidence == FROM_MANIFEST for item in report.commands))

    def test_python_tooling_is_read_from_manifests(self) -> None:
        self.write("pyproject.toml", '[project]\nname = "shop"\ndependencies = ["pytest", "ruff"]\n')
        self.write("uv.lock", "version = 1\n")
        self.write("app/__init__.py", "")

        report = bootstrap(self.project)

        restore = next(item for item in report.commands if item.operation == "Restore")
        self.assertEqual("uv sync", restore.command)
        self.assertEqual(FROM_MANIFEST, restore.confidence)
        self.assertIn("python -m pytest", self.commands_for(report, "Unit tests"))
        self.assertIn("python -m ruff check .", self.commands_for(report, "Lint"))

    def test_an_empty_repository_is_reported_as_greenfield(self) -> None:
        report = bootstrap(self.project)

        self.assertEqual("greenfield", report.mode)
        self.assertEqual([], report.scopes)
        self.assertEqual([], report.modules)
        document = (self.project / ".agent" / "ONBOARDING.md").read_text(encoding="utf-8")
        self.assertIn("the first feature", document)
        self.assertIn("create-spec", document)

    def test_existing_agent_instructions_are_reported_rather_than_replaced(self) -> None:
        self.node_monorepo()
        self.write("CLAUDE.md", "House rules\n")

        report = bootstrap(self.project)

        self.assertEqual(["CLAUDE.md"], report.entry_points)
        self.assertEqual("House rules\n", (self.project / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_regeneration_requires_an_explicit_force(self) -> None:
        self.node_monorepo()
        bootstrap(self.project)
        (self.project / ".agent" / "ONBOARDING.md").write_text("annotated\n", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            bootstrap(self.project)

        bootstrap(self.project, force=True)
        self.assertNotIn("annotated", (self.project / ".agent" / "ONBOARDING.md").read_text(encoding="utf-8"))

    def test_bootstrap_refuses_a_project_without_an_installation(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(FileNotFoundError):
                bootstrap(Path(other))

    def test_command_line_reports_machine_readable_suggestions(self) -> None:
        self.node_monorepo()

        self.assertEqual(0, main(["--project", str(self.project), "bootstrap", "--json"]))
        self.assertEqual(2, main(["--project", str(self.project), "bootstrap"]))
        self.assertEqual(0, main(["--project", str(self.project), "bootstrap", "--force"]))


if __name__ == "__main__":
    unittest.main()
