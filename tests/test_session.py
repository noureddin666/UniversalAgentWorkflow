from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tooling.workflow_features.session import agent_budget, clear_handoff, context_budget, read_handoff, validate_handoff


class SessionWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        agent = self.project / ".agent"
        (agent / "config").mkdir(parents=True)
        (agent / "vendor" / "universal-agent-workflow" / "workflows").mkdir(parents=True)
        (agent / "vendor" / "universal-agent-workflow" / "core").mkdir()
        (agent / "PROJECT.md").write_text("project context", encoding="utf-8")
        (agent / "ROUTER.md").write_text("project router", encoding="utf-8")
        (agent / "vendor" / "universal-agent-workflow" / "core" / "WORKFLOW.md").write_text(
            "core workflow", encoding="utf-8"
        )
        (agent / "vendor" / "universal-agent-workflow" / "workflows" / "feature.md").write_text(
            "feature workflow", encoding="utf-8"
        )
        (self.project / "AGENTS.md").write_text("entry point", encoding="utf-8")
        (agent / "config" / "scopes.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "project": {"context": [".agent/PROJECT.md"]},
                    "scopes": [],
                }
            ),
            encoding="utf-8",
        )
        (agent / "config" / "workflow.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "context_warning_tokens": 10,
                    "context_max_tokens": 100,
                    "context_characters_per_token": 4,
                    "handoff_max_lines": 8,
                    "handoff_max_characters": 200,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_context_budget_includes_only_active_handoff(self) -> None:
        (self.project / ".agent" / "HANDOFF.md").write_text(
            "# Handoff\n\nStatus: active\nNext: continue implementation\n", encoding="utf-8"
        )

        budget = context_budget(self.project, "src/example.py", "feature")

        self.assertEqual("warning", budget["status"])
        self.assertEqual(
            [
                "AGENTS.md",
                ".agent/ROUTER.md",
                ".agent/vendor/universal-agent-workflow/core/WORKFLOW.md",
                ".agent/PROJECT.md",
                ".agent/vendor/universal-agent-workflow/workflows/feature.md",
                ".agent/HANDOFF.md",
            ],
            [item["path"] for item in budget["files"]],
        )

    def test_active_handoff_requires_next_field(self) -> None:
        (self.project / ".agent" / "HANDOFF.md").write_text(
            "# Handoff\n\nStatus: active\n", encoding="utf-8"
        )

        self.assertEqual(["Active handoff must contain a Next field"], validate_handoff(self.project))

    def test_clear_handoff_replaces_session_state(self) -> None:
        (self.project / ".agent" / "HANDOFF.md").write_text(
            "# Handoff\n\nStatus: active\nNext: continue\n", encoding="utf-8"
        )

        clear_handoff(self.project)

        handoff = read_handoff(self.project)
        self.assertEqual("empty", handoff["status"])
        self.assertFalse(handoff["active"])
        self.assertEqual([], validate_handoff(self.project))

    def test_agent_budget_rejects_excessive_fan_out(self) -> None:
        budget = agent_budget(self.project, agents=129, concurrency=122, high_effort=7)

        self.assertEqual("over-limit", budget["status"])
        self.assertEqual(3, len(budget["violations"]))


if __name__ == "__main__":
    unittest.main()
