from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tooling.workflow_features.execution import (
    complete_task,
    next_task,
    replan,
    report,
    retry_task,
    run_status,
    start_run,
)
from tooling.workflow_features.scopes import create_scope
from tooling.workflow_features.specs import create_spec


PASSING = "python -c \"raise SystemExit(0)\""
FAILING = "python -c \"raise SystemExit(1)\""


class TaskRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        agent = self.project / ".agent"
        (agent / "specs").mkdir(parents=True)
        (agent / "config").mkdir(parents=True)
        (agent / "config" / "scopes.json").write_text(
            json.dumps({"schema_version": 1, "project": {"context": []}, "scopes": []}),
            encoding="utf-8",
        )
        (agent / "config" / "local.json").write_text(
            json.dumps(
                {
                    "command_timeout_seconds": 60,
                    "max_output_characters": 2000,
                    "runs_directory": "runs",
                    "dashboard_path": "dashboard.html",
                }
            ),
            encoding="utf-8",
        )
        (self.project / "src").mkdir()
        (self.project / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")

        self._git("init")
        self._git("add", "-A")
        self._git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")

    def _git(self, *arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=self.project, capture_output=True, check=False)

    def edit(self, name: str) -> str:
        relative = f"src/{name}"
        path = self.project / relative
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        path.write_text(existing + "changed = True" + chr(10), encoding="utf-8")
        return relative

    def finish(self, task_id: str, handoff: str | None = None) -> dict:
        changed = self.edit(f"{task_id.lower().replace('-', '_')}.py")
        return complete_task(
            self.project, "demo", task_id, ["pytest"], handoff, [changed], [], False
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def prepare(self, command: str = PASSING, tasks: int = 2) -> Path:
        create_scope(
            self.project,
            "core",
            "Core",
            "application",
            ["src"],
            None,
            verification=[{"operation": "tests", "command": command}],
        )
        directory = create_spec(self.project, "demo", "Demo", "Owner", ["core"])
        lines = [f"- [ ] TASK-{index:03d} `REQ-001` Task {index}" for index in range(1, tasks + 1)]
        (directory / "tasks.md").write_text("# Tasks\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
        start_run(self.project, "demo", force=False)
        return directory

    def test_brief_is_bounded_to_one_task(self) -> None:
        self.prepare()

        brief = next_task(self.project, "demo")

        self.assertEqual("TASK-001", brief["task"]["id"])
        self.assertEqual(1, brief["attempt"])
        self.assertEqual([{"scope": "core", "operation": "tests", "command": PASSING}], brief["verification"])

    def test_failed_verification_never_reaches_the_next_task(self) -> None:
        self.prepare(command=FAILING)
        next_task(self.project, "demo")

        result = self.finish("TASK-001", "carry me forward")

        self.assertFalse(result["passed"])
        self.assertIsNone(result.get("handoff"))
        self.assertFalse((self.project / ".agent" / "HANDOFF.md").exists())
        self.assertEqual("active", run_status(self.project, "demo")["tasks"][0]["state"])

    def test_exhausted_attempts_block_and_halt_the_chain(self) -> None:
        self.prepare(command=FAILING)
        next_task(self.project, "demo")
        for _ in range(3):
            self.finish("TASK-001")

        halted = next_task(self.project, "demo")

        self.assertTrue(halted["halted"])
        self.assertEqual(["TASK-001"], halted["blocked"])
        self.assertIsNone(halted["task"])

    def test_retry_resets_a_blocked_task(self) -> None:
        directory = self.prepare(command=FAILING)
        next_task(self.project, "demo")
        for _ in range(3):
            self.finish("TASK-001")
        self._set_verification(directory, PASSING)

        brief = retry_task(self.project, "demo", "TASK-001")

        self.assertEqual("TASK-001", brief["task"]["id"])
        self.assertEqual(1, brief["attempt"])

    def test_passing_task_carries_a_handoff_to_the_next_one(self) -> None:
        self.prepare()
        next_task(self.project, "demo")

        result = self.finish("TASK-001", "TASK-001 done")

        self.assertTrue(result["passed"])
        self.assertEqual(".agent/HANDOFF.md", result["handoff"])
        self.assertIn("TASK-001 done", next_task(self.project, "demo")["handoff"])

    def test_last_task_writes_no_handoff(self) -> None:
        self.prepare(tasks=1)
        next_task(self.project, "demo")

        result = self.finish("TASK-001", "nothing left")

        self.assertIsNone(result["handoff"])
        self.assertTrue(next_task(self.project, "demo")["done"])

    def test_a_changed_plan_must_be_adopted_before_work_continues(self) -> None:
        directory = self.prepare()
        (directory / "tasks.md").write_text(
            "# Tasks\n\n- [ ] TASK-001 `REQ-001` Task 1\n- [ ] TASK-009 `REQ-001` New\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "run replan"):
            next_task(self.project, "demo")

    def test_replan_keeps_finished_work_and_adopts_the_rest(self) -> None:
        directory = self.prepare()
        next_task(self.project, "demo")
        self.finish("TASK-001")
        (directory / "tasks.md").write_text(
            "# Tasks\n\n- [ ] TASK-001 `REQ-001` Task 1\n- [ ] TASK-009 `REQ-001` New\n", encoding="utf-8"
        )

        report = replan(self.project, "demo")

        self.assertEqual(2, report["revision"])
        self.assertEqual({"pending": 1, "active": 0, "done": 1, "blocked": 0}, report["counts"])
        self.assertEqual(["TASK-001", "TASK-009"], [task["id"] for task in report["tasks"]])

    def test_replan_refuses_to_drop_finished_work(self) -> None:
        directory = self.prepare()
        next_task(self.project, "demo")
        self.finish("TASK-001")
        (directory / "tasks.md").write_text(
            "# Tasks\n\n- [ ] TASK-002 `REQ-001` Task 2\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "no longer declares finished tasks"):
            replan(self.project, "demo")

    def test_completing_an_inactive_task_is_rejected(self) -> None:
        self.prepare()

        with self.assertRaisesRegex(ValueError, "not active"):
            complete_task(self.project, "demo", "TASK-001", [], None, ["src/app.py"], [], False)

    def test_a_task_that_changed_nothing_cannot_advance(self) -> None:
        self.prepare()
        next_task(self.project, "demo")

        with self.assertRaisesRegex(ValueError, "unchanged since it started"):
            complete_task(
                self.project, "demo", "TASK-001", ["pytest"], None, ["src/app.py"], [], False
            )

        self.assertEqual("active", run_status(self.project, "demo")["tasks"][0]["state"])

    def test_completing_without_declaring_what_changed_is_rejected(self) -> None:
        self.prepare()
        next_task(self.project, "demo")

        with self.assertRaisesRegex(ValueError, "needs --code"):
            complete_task(self.project, "demo", "TASK-001", ["pytest"], None, [], [], False)

    def test_a_declared_file_that_does_not_exist_is_rejected(self) -> None:
        self.prepare()
        next_task(self.project, "demo")

        with self.assertRaisesRegex(ValueError, "do not exist"):
            complete_task(
                self.project, "demo", "TASK-001", ["pytest"], None, ["src/absent.py"], [], False
            )

    def test_a_genuinely_no_op_task_needs_an_explicit_escape(self) -> None:
        self.prepare()
        next_task(self.project, "demo")

        result = complete_task(self.project, "demo", "TASK-001", ["reviewed"], None, [], [], True)

        self.assertTrue(result["passed"])

    def test_editing_an_already_dirty_file_still_counts_as_progress(self) -> None:
        self.prepare()
        self.edit("app.py")
        next_task(self.project, "demo")
        self.edit("app.py")

        result = complete_task(
            self.project, "demo", "TASK-001", ["pytest"], None, ["src/app.py"], [], False
        )

        self.assertTrue(result["passed"])

    def test_a_completed_task_writes_its_own_traceability_link(self) -> None:
        directory = self.prepare()
        next_task(self.project, "demo")
        code = self.edit("feature.py")
        test = self.edit("feature_test.py")

        result = complete_task(
            self.project, "demo", "TASK-001", ["pytest"], None, [code], [test], False
        )

        self.assertEqual("REQ-001", result["traceability"])
        trace = json.loads((directory / "traceability.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [{"requirement_id": "REQ-001", "task_ids": ["TASK-001"], "code_paths": [code],
              "test_paths": [test], "evidence": ["pytest"]}],
            [{key: link[key] for key in ("requirement_id", "task_ids", "code_paths", "test_paths", "evidence")}
             for link in trace["links"]],
        )

    def test_report_separates_clean_runs_from_retried_ones(self) -> None:
        directory = self.prepare(command=FAILING, tasks=2)
        next_task(self.project, "demo")
        self.finish("TASK-001")
        self._set_verification(directory, PASSING)
        self.finish("TASK-001")
        next_task(self.project, "demo")
        self.finish("TASK-002")

        summary = report(self.project, "demo")

        self.assertEqual(1, summary["failed_attempts"])
        self.assertEqual(0.5, summary["retry_cost"])
        self.assertEqual(0.5, summary["first_pass_rate"])
        self.assertEqual(0, summary["replans"])

    def test_report_counts_replans(self) -> None:
        directory = self.prepare()
        next_task(self.project, "demo")
        self.finish("TASK-001")
        (directory / "tasks.md").write_text(
            "# Tasks" + chr(10) * 2 + "- [ ] TASK-001 `REQ-001` Task 1" + chr(10)
            + "- [ ] TASK-009 `REQ-001` New" + chr(10),
            encoding="utf-8",
        )
        replan(self.project, "demo")

        self.assertEqual(1, report(self.project, "demo")["replans"])

    def _set_verification(self, directory: Path, command: str) -> None:
        path = self.project / ".agent" / "config" / "scopes.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["scopes"][0]["verification"] = [{"operation": "tests", "command": command}]
        path.write_text(json.dumps(config), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
