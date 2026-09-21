# Feature specs

Each feature owns one directory named with a stable kebab-case id:

```text
specs/<spec-id>/
├── spec.json
├── spec.md
├── plan.md
├── tasks.md
└── traceability.json
```

Large specs may split requirements by business area:

```text
specs/<spec-id>/requirements/
├── eligibility.json
├── pricing.json
├── fulfillment.json
└── notifications.json
```

The manifest lists these files in `requirement_files`. Validation, planning, task generation, and traceability aggregate every file while enforcing globally unique requirement IDs.

Create these files with `workflow create-spec <spec-id> --title "..." --owner "..."`.
Do not edit generated lifecycle approvals to imitate stakeholder authorization; use the transition command.
Build `traceability.json` with `link-requirement`, which verifies task ids and file paths before writing.

Before a spec can be `Accepted` it must state `scope.in` and `scope.out`, every entry in `assumptions` needs an
owner or validation method plus a consequence if false, and every entry in `open_decisions` needs a resolution.

## Lifecycle

The only states are `Proposed`, `Accepted`, `Implemented`, `Superseded`, and `Blocked`. A new spec starts
`Proposed`. Allowed transitions:

| From | To |
|---|---|
| `Proposed` | `Accepted`, `Blocked`, `Superseded` |
| `Accepted` | `Implemented`, `Blocked`, `Superseded` |
| `Blocked` | `Proposed`, `Accepted`, `Superseded` |
| `Implemented` | `Superseded` |
| `Superseded` | — |

There is no `Planned`, `Implementing`, or `Verified` state; planning and implementation happen inside
`Accepted`. Reaching `Implemented` therefore takes two transitions, never one.

## Traceability shape

`traceability.json` holds `links`, and a link counts as complete only when every field below resolves:

```json
{
  "links": [
    {
      "requirement_id": "R1",
      "task_ids": ["T1"],
      "code_paths": ["src/app.py"],
      "test_paths": ["tests/test_app.py"]
    }
  ]
}
```

`task_ids` must appear in `tasks.md`; `code_paths` and `test_paths` are repo-root-relative and must exist.
Write links with `workflow link-requirement`, which checks all three before saving.

## Running the tasks

`run.json` holds execution state next to `tasks.md`: per-task `state`
(`pending`/`active`/`done`/`blocked`), attempt count, and the evidence recorded on success. `tasks.md`
stays the readable plan; `run.json` is never edited by hand. A digest links the two, so editing the
plan mid-run forces an explicit `run replan` rather than silently shifting what is being executed.
