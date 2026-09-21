from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tooling.workflow_features.documents import document_outline, find_sections, read_section


DOCUMENT = """# Plan

Intro line.

## Assumptions

The billing provider throttles at 10 rps.

## Phase 1

Set up the queue.

### Rollback

Drain and stop.

## Phase 2

Wire the retry path.

```python
# Phase 3 is not a heading, it is code
```

## Phase 2

A duplicate heading.
"""


class DocumentSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary_directory.name)
        (self.project / ".agent" / "config").mkdir(parents=True)
        (self.project / ".agent" / "config" / "workflow.json").write_text(
            json.dumps({"schema_version": 1, "document_whole_file_lines": 5}), encoding="utf-8"
        )
        (self.project / "plan.md").write_text(DOCUMENT, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_section_ids_follow_the_heading_nesting(self) -> None:
        result = document_outline(self.project, "plan.md")

        self.assertEqual(
            ["plan", "plan/assumptions", "plan/phase-1", "plan/phase-1/rollback", "plan/phase-2", "plan/phase-2-2"],
            [section["id"] for section in result["sections"]],
        )

    def test_headings_inside_code_fences_are_not_sections(self) -> None:
        identifiers = [section["id"] for section in document_outline(self.project, "plan.md")["sections"]]

        self.assertNotIn("plan/phase-3-is-not-a-heading-it-is-code", identifiers)

    def test_a_short_file_says_to_read_it_whole(self) -> None:
        (self.project / "tiny.md").write_text("# Tiny\n\nOne line.\n", encoding="utf-8")

        self.assertTrue(document_outline(self.project, "tiny.md")["read_whole_file"])
        self.assertFalse(document_outline(self.project, "plan.md")["read_whole_file"])

    def test_reading_a_section_returns_only_that_section(self) -> None:
        result = read_section(self.project, "plan.md", "plan/phase-1")

        self.assertIn("Set up the queue.", result["content"])
        self.assertNotIn("Wire the retry path.", result["content"])
        self.assertIn("Drain and stop.", result["content"])

    def test_every_section_answer_carries_the_whole_table_of_contents(self) -> None:
        result = read_section(self.project, "plan.md", "plan/phase-1")

        self.assertIn(
            "plan/assumptions", [entry["id"] for entry in result["table_of_contents"]]
        )

    def test_an_unknown_section_lists_the_known_ones(self) -> None:
        with self.assertRaisesRegex(ValueError, "plan/assumptions"):
            read_section(self.project, "plan.md", "plan/phase-9")

    def test_a_path_outside_the_project_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "escapes the project"):
            read_section(self.project, "../outside.md", "plan")

    def test_search_ranks_a_title_match_above_a_body_match(self) -> None:
        result = find_sections(self.project, "rollback", ["plan.md"], 10)

        self.assertEqual("plan/phase-1/rollback", result["matches"][0]["id"])
        self.assertTrue(all("plan" != match["id"] for match in result["matches"]))

    def test_a_section_matching_more_terms_outranks_one_matching_fewer(self) -> None:
        result = find_sections(self.project, "rollback drain queue", ["plan.md"], 10)

        self.assertEqual("plan/phase-1/rollback", result["matches"][0]["id"])
        self.assertEqual(["rollback", "drain"], result["matches"][0]["matched_terms"])

    def test_a_query_matching_nothing_returns_nothing(self) -> None:
        self.assertEqual(0, find_sections(self.project, "nonexistentword", ["plan.md"], 10)["total"])

    def test_search_drops_a_parent_when_a_child_answers_better(self) -> None:
        result = find_sections(self.project, "queue", ["plan.md"], 10)

        self.assertEqual(["plan/phase-1"], [match["id"] for match in result["matches"]])

    def test_search_returns_an_addressable_reference_not_a_file(self) -> None:
        match = find_sections(self.project, "throttles", ["plan.md"], 10)["matches"][0]

        self.assertEqual("plan.md", match["path"])
        self.assertEqual("plan/assumptions", match["id"])
        self.assertIn("10 rps", match["excerpt"])

    def test_search_walks_a_directory(self) -> None:
        nested = self.project / "docs"
        nested.mkdir()
        (nested / "other.md").write_text("# Other\n\nThe queue is drained nightly.\n", encoding="utf-8")

        result = find_sections(self.project, "drained", ["."], 10)

        self.assertEqual(["docs/other.md"], [match["path"] for match in result["matches"]])

    def test_search_needs_a_word(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one word"):
            find_sections(self.project, "   ", ["plan.md"], 10)


if __name__ == "__main__":
    unittest.main()
