from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = PACKAGE_ROOT / "scripts" / "install_workflow.py"
UPDATER = PACKAGE_ROOT / "scripts" / "update_workflow.py"


def run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def install(self) -> subprocess.CompletedProcess[str]:
        return run(INSTALLER, str(self.project))

    def test_install_creates_entry_point_project_files_and_vendor_bundle(self) -> None:
        result = self.install()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.project / "AGENTS.md").is_file())
        self.assertTrue((self.project / ".agent" / "PROJECT.md").is_file())
        self.assertTrue((self.project / ".agent" / "workflow.py").is_file())
        vendor = self.project / ".agent" / "vendor" / "universal-agent-workflow"
        for expected in ("core", "workflows", "profiles", "tooling"):
            self.assertTrue((vendor / expected).is_dir(), expected)
        self.assertTrue((vendor / "VERSION").is_file())
        self.assertTrue((vendor / "LICENSE").is_file())
        self.assertTrue((vendor / "MANUAL.md").is_file())
        self.assertTrue((vendor / "GUIDE.ar.md").is_file())
        self.assertTrue((self.project / ".github" / "workflows" / "agent-workflow.yml").is_file())

    def test_install_never_copies_bytecode(self) -> None:
        self.install()

        vendor = self.project / ".agent" / "vendor" / "universal-agent-workflow"
        self.assertEqual([], list(vendor.rglob("__pycache__")))
        self.assertEqual([], list(vendor.rglob("*.pyc")))

    def test_install_refuses_an_existing_agents_file(self) -> None:
        (self.project / "AGENTS.md").write_text("mine", encoding="utf-8")

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("AGENTS.md", result.stderr)
        self.assertEqual("mine", (self.project / "AGENTS.md").read_text(encoding="utf-8"))

    def test_install_refuses_an_existing_agent_directory(self) -> None:
        (self.project / ".agent").mkdir()

        result = self.install()

        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_install_keeps_an_existing_ci_workflow(self) -> None:
        workflows = self.project / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "agent-workflow.yml").write_text("mine", encoding="utf-8")

        self.install()

        self.assertEqual("mine", (workflows / "agent-workflow.yml").read_text(encoding="utf-8"))

    def agent_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.project / ".agent" / "workflow.py"), *arguments],
            cwd=self.project,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_documented_quick_start_passes_on_a_fresh_install(self) -> None:
        self.install()

        self.assertEqual(0, self.agent_cli("local-init").returncode)
        for gate in ("validate", "check-architecture", "check-index"):
            self.assertEqual(0, self.agent_cli(gate).returncode, gate)
        health = self.agent_cli("doctor", "--json")

        self.assertEqual(0, health.returncode, health.stderr)
        self.assertTrue(json.loads(health.stdout)["passed"])

    def test_bootstrap_runs_through_the_installed_cli(self) -> None:
        (self.project / "package.json").write_text(
            json.dumps({"name": "shop", "scripts": {"build": "tsup"}}), encoding="utf-8"
        )
        self.install()

        result = self.agent_cli("bootstrap", "--json")

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("existing-code", report["mode"])
        self.assertTrue((self.project / ".agent" / "ONBOARDING.md").is_file())
        self.assertIn("TODO", (self.project / ".agent" / "PROJECT.md").read_text(encoding="utf-8"))

    def test_doctor_reports_a_missing_index_before_local_init(self) -> None:
        self.install()

        health = self.agent_cli("doctor", "--json")

        self.assertEqual(1, health.returncode)
        self.assertIn("Project index is missing; run build-index", json.loads(health.stdout)["errors"])


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        run(INSTALLER, str(self.project))
        self.agent = self.project / ".agent"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_update_replaces_the_vendor_bundle_and_keeps_project_files(self) -> None:
        (self.agent / "PROJECT.md").write_text("my project facts", encoding="utf-8")
        (self.agent / "DECISIONS.md").write_text("my decisions", encoding="utf-8")
        vendor = self.agent / "vendor" / "universal-agent-workflow"
        (vendor / "core" / "WORKFLOW.md").write_text("stale", encoding="utf-8")

        result = run(UPDATER, str(self.project))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual("stale", (vendor / "core" / "WORKFLOW.md").read_text(encoding="utf-8"))
        self.assertEqual("my project facts", (self.agent / "PROJECT.md").read_text(encoding="utf-8"))
        self.assertEqual("my decisions", (self.agent / "DECISIONS.md").read_text(encoding="utf-8"))

    def test_update_backs_up_the_previous_bundle(self) -> None:
        result = run(UPDATER, str(self.project))

        backups = list((self.agent / "backups").iterdir())
        self.assertEqual(1, len(backups), result.stdout)
        self.assertTrue((backups[0] / "core" / "WORKFLOW.md").is_file())

    def test_update_refuses_a_project_without_an_installed_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            result = run(UPDATER, other)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("vendor bundle not found", result.stderr)

    def test_migrate_tops_up_an_older_gitignore_without_losing_entries(self) -> None:
        (self.agent / ".gitignore").write_text("/runs/\n/dashboard.html\n/my-own-entry\n", encoding="utf-8")

        run(UPDATER, str(self.project), "--migrate")

        lines = (self.agent / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/my-own-entry", lines)
        for required in ("/runs/", "/backups/", "/dashboard.html", "__pycache__/", "*.pyc"):
            self.assertIn(required, lines)

    def test_migrate_raises_artifact_schema_version(self) -> None:
        config = self.agent / "config" / "scopes.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value.pop("schema_version")
        config.write_text(json.dumps(value), encoding="utf-8")

        result = run(UPDATER, str(self.project), "--migrate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, json.loads(config.read_text(encoding="utf-8"))["schema_version"])


if __name__ == "__main__":
    unittest.main()
