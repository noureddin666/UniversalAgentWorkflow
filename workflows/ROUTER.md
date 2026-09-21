# Task router

Load the core workflow, then select one primary workflow:

| Request | Workflow |
|---|---|
| First session in a repository whose facts are unfilled | `.agent/vendor/universal-agent-workflow/workflows/onboarding.md` |
| New or changed behavior | `.agent/vendor/universal-agent-workflow/workflows/feature.md` |
| Incorrect behavior or regression | `.agent/vendor/universal-agent-workflow/workflows/bugfix.md` |
| Investigation without requested changes | `.agent/vendor/universal-agent-workflow/workflows/diagnosis.md` |
| Structural improvement with preserved behavior | `.agent/vendor/universal-agent-workflow/workflows/refactor.md` |
| Review or audit | `.agent/vendor/universal-agent-workflow/workflows/review.md` |
| Durable fact, constraint, risk, or opportunity found during work | `.agent/vendor/universal-agent-workflow/workflows/discovery.md` |

Also load `.agent/vendor/universal-agent-workflow/core/REQUIREMENTS.md` when the request is ambiguous, evolving, cross-cutting, costly to reverse, or conflicts with an accepted requirement.

Use a technology profile only when it matches the detected repository stack. Project-local rules always win.
