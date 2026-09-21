# Core workflow

## Operating loop

1. Resolve affected paths through project and nested scope routing, then load only the returned context, specs, bugs, and discoveries.
2. Establish the requested outcome, constraints, and acceptance evidence.
3. Inspect the smallest useful part of the codebase and preserve unrelated work.
4. Identify the business capability that owns the change.
5. Surface assumptions that could materially alter the result.
6. Implement the smallest coherent change within existing boundaries.
7. Verify with the repository's declared commands and relevant acceptance criteria.
8. Review the diff for scope drift, hidden configuration, coupling, and stale documentation.
9. Record only requirement or architecture decisions whose rationale is not already evident in code.
10. Record only durable business changes, bugs, or discoveries that future work would otherwise miss.
11. Rebuild indexes and report the outcome, verification, and any remaining uncertainty.

## Invariants

- User intent outranks the workflow; the workflow clarifies intent but does not expand it.
- Repository facts outrank generic profiles.
- Do not overwrite unrelated user changes.
- Do not introduce secrets or environment-specific values into source code.
- Prefer feature ownership, high cohesion, and explicit boundaries.
- Avoid god units, dumping-ground shared code, and speculative abstractions.
- Match verification effort to risk and state what was not verified.
- Require explicit authority for destructive or externally consequential actions.

## Adaptive depth

Use the lightest process that controls the actual risk:

- Small and reversible: confirm outcome, edit, run focused verification.
- Cross-cutting or behavior-changing: add an impact note and verify affected boundaries.
- Ambiguous or costly to reverse: resolve the decision before implementation.
- Safety, money, privacy, production data, or public API impact: require explicit acceptance criteria and rollback thinking.
