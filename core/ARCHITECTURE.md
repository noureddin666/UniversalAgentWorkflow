# Architecture guardrails

- Organize primary ownership around business capabilities when the system has a business domain.
- Keep each code unit focused on one coherent responsibility.
- Communicate across feature boundaries through explicit contracts.
- Keep infrastructure replaceable and domain rules independent of provider details.
- Put code in shared areas only when ownership is genuinely cross-cutting.
- Add an abstraction only when it improves a real boundary, testability, replaceability, or maintenance cost.
- Follow the repository's established architecture unless the task explicitly includes changing it.
- Refactor incrementally and protect observable behavior when risk is meaningful.

Architecture rules describe outcomes, not mandatory folder names. A small script, a mobile app, a data pipeline, and a modular backend need different shapes.

Boundary enforcement is technology-neutral. Source import-prefix checks cover configured modules across supported text-based languages; optional adapters add native knowledge for ecosystems such as .NET project references and package.json workspaces. A repository never needs to adopt an ecosystem-specific adapter that it does not use.
