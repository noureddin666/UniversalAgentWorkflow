# Project router

Always read:

- The context returned by `workflow route <changed-path> --intent <intent>` (AGENTS.md names the wrapper and the valid intents).
- Applicable entries under `.agent/specs/` returned by the same command.

Then use the task router in `.agent/vendor/universal-agent-workflow/workflows/ROUTER.md`.

Use `.agent/requirements/CURRENT.md` only as the legacy target when no feature spec applies.

For work spanning multiple paths, resolve every path and use the union of context and specs. Do not load unrelated scope documentation.

Run `context-budget <changed-path> --intent <intent>` before adding references not returned by the route.

Add project-specific path routing here as the repository develops. Keep each route limited to the smallest references required for the task.
