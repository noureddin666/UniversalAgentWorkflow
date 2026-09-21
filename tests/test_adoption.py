from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tooling.workflow import main
from tooling.workflow_features.onboarding import adopt, answer_field, bootstrap, unanswered_fields
from tooling.workflow_features.onboarding.model import FROM_DOCUMENTATION, FROM_LAYOUT, FROM_MANIFEST


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = PACKAGE_ROOT / "template" / ".agent"


class AdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        agent = self.project / ".agent"
        (agent / "config").mkdir(parents=True)
        for name in ("PROJECT.md", "COMMANDS.md", "config/scopes.json"):
            shutil.copy2(TEMPLATE / name, agent / name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read(self, relative: str) -> str:
        return (self.project / relative).read_text(encoding="utf-8")

    def web_application(self) -> None:
        self.write(
            "package.json",
            json.dumps(
                {
                    "name": "@acme/shop",
                    "description": "Online shop for handmade furniture.",
                    "scripts": {"build": "ng build", "test": "ng test"},
                    "dependencies": {"@angular/core": "^18.2.0"},
                    "engines": {"node": ">=20"},
                }
            ),
        )
        self.write("package-lock.json", "{}")
        self.write(
            "api/package.json",
            json.dumps({"name": "api", "scripts": {"start": "node server.js"}, "dependencies": {"express": "^4.19.2", "pg": "^8"}}),
        )
        for name in ("server.js", "orders.js", "customers.js"):
            self.write(f"api/{name}", "module.exports = {}\n")
        for name in ("main.ts", "app.ts", "cart.ts"):
            self.write(f"src/{name}", "export const value = 1\n")
        self.write("src/cart.spec.ts", "describe('cart', () => {})\n")
        self.write("netlify.toml", "[build]\n")
        self.write("README.md", "# Shop\n\nThis project was generated with Angular CLI.\n")

    def facts(self) -> dict[str, object]:
        return {item.field: item for item in bootstrap(self.project, force=True).facts}

    def test_facts_come_from_manifests_layout_and_documentation(self) -> None:
        self.web_application()

        facts = self.facts()

        self.assertEqual("Online shop for handmade furniture.", facts["Purpose"].value)
        self.assertEqual(FROM_MANIFEST, facts["Purpose"].confidence)
        self.assertEqual("Angular 18 (root), Express 4 (`api/`)", facts["System shape"].value)
        self.assertEqual("`api/`, `src/`", facts["Main source paths"].value)
        self.assertEqual(FROM_LAYOUT, facts["Main source paths"].confidence)
        self.assertEqual("`src/**/*.spec.ts`", facts["Test paths"].value)
        self.assertEqual("Netlify", facts["Deployment environment"].value)
        self.assertEqual("PostgreSQL", facts["External systems"].value)
        self.assertEqual("Node.js >=20", facts["Compatibility"].value)

    def test_readme_boilerplate_is_never_taken_as_the_purpose(self) -> None:
        self.web_application()
        self.write("package.json", json.dumps({"name": "shop"}))

        self.assertNotIn("Purpose", self.facts())

        self.write("README.md", "# Shop\n\n[![CI](badge.svg)](ci)\n\nSells *handmade* furniture\nonline.\n\n## Setup\n")
        purpose = self.facts()["Purpose"]
        self.assertEqual("Sells handmade furniture online.", purpose.value)
        self.assertEqual(FROM_DOCUMENTATION, purpose.confidence)

    def test_adopt_fills_placeholders_and_never_replaces_a_written_value(self) -> None:
        self.web_application()
        project = self.read(".agent/PROJECT.md").replace("- Test paths: TODO", "- Test paths: e2e/ only")
        self.write(".agent/PROJECT.md", project)

        result = adopt(self.project)

        text = self.read(".agent/PROJECT.md")
        self.assertIn("- Purpose: Online shop for handmade furniture. _(evidence: `package.json` description)_", text)
        self.assertIn("- Test paths: e2e/ only\n", text)
        self.assertIn("- Primary users: TODO", text)
        self.assertIn("\n\n## Constraints\n", text)
        self.assertNotIn("Test paths", result.facts)
        self.assertIn("PROJECT.md: Primary users", result.remaining)
        self.assertEqual("shop", json.loads(self.read(".agent/config/scopes.json"))["project"]["id"])

        before = self.read(".agent/PROJECT.md"), self.read(".agent/COMMANDS.md")
        again = adopt(self.project)
        self.assertEqual(before, (self.read(".agent/PROJECT.md"), self.read(".agent/COMMANDS.md")))
        self.assertEqual([], again.facts + again.commands)

    def test_adopt_writes_declared_commands_with_their_evidence(self) -> None:
        self.web_application()

        adopt(self.project)

        commands = self.read(".agent/COMMANDS.md")
        self.assertIn("| Build | `npm run build` | Restore completed | `package.json scripts.build` |", commands)
        self.assertIn("| Run locally | `cd api && npm run start` | `api` restored | `api/package.json scripts.start` |", commands)
        self.assertIn("| Lint | not declared | — | no manifest, Makefile, or CI step declares one |", commands)

    def test_convention_only_commands_wait_for_a_person(self) -> None:
        self.write("go.mod", "module example.com/tool\n\ngo 1.22\n")
        for name in ("main.go", "cli.go", "run.go"):
            self.write(f"cmd/{name}", "package main\n")

        result = adopt(self.project)

        commands = self.read(".agent/COMMANDS.md")
        self.assertIn("| Build | TODO | TODO | TODO |", commands)
        self.assertIn("COMMANDS.md: Build (only convention-derived candidates; see ONBOARDING.md)", result.remaining)
        self.assertIn("Go 1.22", self.read(".agent/PROJECT.md"))

    def test_a_greenfield_repository_keeps_its_command_table(self) -> None:
        result = adopt(self.project)

        self.assertIn("| Build | TODO | TODO | TODO |", self.read(".agent/COMMANDS.md"))
        self.assertIn("COMMANDS.md: fill after the first successful build", result.remaining)

    def test_an_older_three_column_table_is_filled_in_place(self) -> None:
        self.web_application()
        self.write(".agent/COMMANDS.md", "| Operation | Command | Prerequisites |\n|---|---|---|\n| Build | TODO | TODO |\n| Lint | TODO | TODO |\n")

        adopt(self.project)

        commands = self.read(".agent/COMMANDS.md")
        self.assertIn("| Build | `npm run build` | Restore completed |\n", commands)
        self.assertIn("| Lint | not declared | no manifest, Makefile, or CI step declares one |", commands)

    def dotnet_web_application(self) -> None:
        self.write("Shop.slnx", "<Solution />")
        self.write("Shop/Shop.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net9.0</TargetFramework></PropertyGroup></Project>')
        for name in ("Program.cs", "Orders.cs", "Customers.cs"):
            self.write(f"Shop/{name}", "namespace Shop;\n")
        self.write("Shop/Data/Migrations/Initial.cs", "namespace Shop;\n")
        self.write("Deploy-IIS.ps1", "Write-Host deploy\n")

    def test_a_dotnet_web_app_without_tests_runs_but_claims_no_test_command(self) -> None:
        self.dotnet_web_application()

        report = bootstrap(self.project, force=True)
        facts = {item.field: item.value for item in report.facts}

        commands = {(item.operation, item.command) for item in report.commands}
        self.assertIn(("Run locally", "dotnet run --project Shop/Shop.csproj"), commands)
        self.assertFalse(any(operation == "Unit tests" for operation, _ in commands))
        self.assertEqual("none found", facts["Test paths"])
        self.assertEqual("none found", facts["Documentation paths"])
        self.assertEqual("IIS", facts["Deployment environment"])
        self.assertIn("`Shop/Data/Migrations` (database migrations)", facts["Protected paths requiring approval"])
        self.assertIn("`Deploy-IIS.ps1` (deployment script)", facts["Protected paths requiring approval"])

    def test_a_dotnet_test_project_enables_the_test_command(self) -> None:
        self.dotnet_web_application()
        self.write("Shop.Tests/Shop.Tests.csproj", '<Project Sdk="Microsoft.NET.Sdk"></Project>')

        commands = {(item.operation, item.command) for item in bootstrap(self.project, force=True).commands}

        self.assertIn(("Unit tests", "dotnet test Shop.slnx --no-build"), commands)

    def test_answers_only_ever_replace_a_placeholder(self) -> None:
        self.assertIn("Primary users", unanswered_fields(self.project))

        self.assertTrue(answer_field(self.project, "Primary users", "Store staff"))
        self.assertFalse(answer_field(self.project, "Primary users", "Someone else"))

        self.assertIn("- Primary users: Store staff\n", self.read(".agent/PROJECT.md"))
        self.assertNotIn("Primary users", unanswered_fields(self.project))


class SetupCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / "package.json").write_text(
            json.dumps({"name": "shop", "description": "A shop.", "scripts": {"build": "tsc"}}), encoding="utf-8"
        )
        installer = PACKAGE_ROOT / "scripts" / "install_workflow.py"
        subprocess.run([sys.executable, str(installer), str(self.project)], check=True, capture_output=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_setup_goes_from_installation_to_a_described_project(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(["--project", str(self.project), "setup"]))

        agent = self.project / ".agent"
        self.assertTrue((agent / "ONBOARDING.md").is_file())
        self.assertTrue((agent / "INDEX.json").is_file())
        self.assertTrue((agent / "dashboard.html").is_file())
        self.assertTrue((self.project / "CLAUDE.md").is_file())
        self.assertIn("- Purpose: A shop.", (agent / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertIn("`npm run build`", (agent / "COMMANDS.md").read_text(encoding="utf-8"))

    def test_setup_ask_records_answers_and_skips_blank_ones(self) -> None:
        answers = {"Primary users: ": "Store staff", "Business capabilities: ": "unknown"}
        with redirect_stdout(io.StringIO()), mock.patch("builtins.input", lambda prompt: answers.get(prompt, "")):
            self.assertEqual(0, main(["--project", str(self.project), "setup", "--ask"]))

        project = (self.project / ".agent" / "PROJECT.md").read_text(encoding="utf-8")
        self.assertIn("- Primary users: Store staff\n", project)
        self.assertIn("- Business capabilities: unknown\n", project)
        self.assertIn("- Security and privacy: TODO", project)

    def test_setup_ask_finishes_the_setup_when_input_ends_early(self) -> None:
        def closed(_: str) -> str:
            raise EOFError

        with redirect_stdout(io.StringIO()), mock.patch("builtins.input", closed):
            self.assertEqual(0, main(["--project", str(self.project), "setup", "--ask"]))

        self.assertTrue((self.project / ".agent" / "dashboard.html").is_file())
        self.assertTrue((self.project / "CLAUDE.md").is_file())


if __name__ == "__main__":
    unittest.main()
