# Requirements under change

Treat each accepted `.agent/specs/<spec-id>/spec.json` and its human-readable `.agent/specs/<id>/spec.md` as a durable source of truth. Conversation context may explain a requirement but does not silently replace it. `.agent/requirements/CURRENT.md` remains a migration fallback only.

## Requirement states

- `Proposed`: understood enough to discuss, not authorized for implementation.
- `Accepted`: current implementation target.
- `Implemented`: acceptance evidence exists.
- `Superseded`: replaced, retained only for traceability.
- `Blocked`: missing a decision or authority that materially changes the result.

## Change protocol

When a new request conflicts with accepted requirements:

1. Name the conflict in plain language.
2. Identify affected behavior, data, APIs, tests, documentation, delivery, and prior decisions.
3. Classify the change as clarification, additive, replacement, or reversal.
4. Update the owning feature spec before relying on the new interpretation.
5. Record displaced requirements in `.agent/requirements/CHANGES.md`; do not erase history.
6. Revalidate assumptions and acceptance criteria touched by the change.

## Traceability

Every requirement has a stable `REQ-NNN` identifier. Plans and tasks reference it, and `traceability.json` links it to implementation paths, tests, and verification evidence. An implemented spec without complete traceability fails validation.

Large specs may distribute requirements across cohesive files declared by `requirement_files`. IDs and lifecycle remain spec-wide; splitting storage must not split ownership, acceptance, or traceability.

## Scope knowledge

Each material business or application scope owns its purpose, vocabulary, rules, variables, data, contracts, decisions, and change history. Nested scopes inherit context from their project and parent scopes. Bugs and durable discoveries link back to the scopes and specs they affect.

Do not demand ceremony for wording changes that have no implementation effect.

## Uncertainty

Record only assumptions that could change scope, architecture, security, data, compatibility, cost, or user-visible behavior. Each assumption needs an owner or validation method and a consequence if false.

Stop for clarification only when reasonable alternatives lead to materially different outcomes. Otherwise choose a reversible default and disclose it.
