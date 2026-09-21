# Agent entry point

## Running the workflow

Use the wrapper for your shell; it resolves an available interpreter:

- POSIX shells: `./.agent/workflow.sh <command>`
- Windows: `.agent\workflow.cmd <command>` — the `.ps1` wrapper needs
  `pwsh -NoProfile -ExecutionPolicy Bypass -File .agent/workflow.ps1` under a restricted execution policy.

Commands below are written as `workflow <command>`; substitute the wrapper for your shell. Any command
may be run from a subdirectory. Valid `--intent` values are `feature`, `bugfix`, `diagnosis`,
`refactor`, `review`, and `discovery`.

## Start

0. If missing project facts block the requested task, run `workflow setup` and
   confirm only the facts needed now. Placeholders elsewhere do not block work.
1. Read `.agent/ROUTER.md` and resolve changed paths through `workflow route`.
2. Read only project and scope references returned by the router.
3. Use `.agent/COMMANDS.md` for verification; do not invent commands when declared ones exist.
4. Load an applicable feature spec when the requested behavior is governed by one. `.agent/specs/README.md`
   has the spec lifecycle states and the traceability shape; do not infer either from the tooling source.
5. Use `.agent/requirements/CURRENT.md` only for projects not yet migrated to feature specs.
6. Preserve unrelated changes and respect protected paths.
7. Read `.agent/HANDOFF.md` only when its status is `active`; write it only for unfinished work.
8. Use `context-budget` when a route looks broad. Warnings are advisory; split an over-limit route or explain why it must remain whole.

## Long documents

Do not read a long document whole to reach one part of it:

```
workflow outline <path>                    # section ids, titles, line counts
workflow read <path> --section <id>        # that section only, plus the full table of contents
workflow read <path>                       # no --section: the outline, so you can pick one
workflow find "<words>" [--path <path>]    # ranked section references across the docs
```

`find` is lexical and returns the narrowest section that matched, never a whole file. Every `read`
returns the document's table of contents alongside the section, so check it before concluding the
answer is not there. `outline` says `read_whole_file` when the document is short enough that two
round trips cost more than reading it.

## Long tasks

Work that does not fit one session runs as a task chain instead of one long context:

```
workflow run start <spec-id>          # seed the run from tasks.md
workflow run next <spec-id>           # brief for exactly one task — start a fresh session on it
workflow run complete <spec-id> <task-id> --code <file> --test <file> --evidence "..." --handoff "..."
```

Name what you changed with `--code` and `--test`. Those files must exist and must differ from where
they stood when the task started, so claiming a task you did not do is rejected; pass
`--allow-no-change` only when the task genuinely edits nothing. The scope verification runs next.
**A failing task advances nothing** — no evidence, no handoff, no next task — and the chain halts
once a task exhausts its attempts. Fix it, then `workflow run retry <spec-id> <task-id>`. On success
the traceability link is written for you, so do not call `link-requirement` again for that task.

Rewrite the remaining plan in `tasks.md` whenever what you learned invalidates it, then
`workflow run replan <spec-id>`. Finished tasks keep their evidence; a stale plan blocks `next`
until adopted. Deciding the whole plan up front and never revising it is the failure mode this
guards against.

Keep the handoff to what the next task needs. It is a handoff, not a summary of the session.

## Precedence

1. The user's current explicit request.
2. Safety and authorization boundaries.
3. Project-specific instructions and accepted requirements.
4. Detected technology profiles.
5. Universal workflow defaults.

Protected paths prevent incidental edits. When the user's explicit request includes one, proceed without
asking for duplicate approval and verify in proportion to its blast radius.

If instructions conflict, follow the higher-precedence source and record a material requirement change instead of silently combining incompatible directions.
