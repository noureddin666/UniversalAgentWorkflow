<div align="center">

# Universal Agent Workflow

**A technology-neutral operating framework for coding agents.**

Install it into any repository and every agent — Codex, Claude Code, Copilot, Cursor, Gemini — works
the same way: it learns the project from evidence, routes each task to the right context, respects
your architectural boundaries, and proves its work with your own commands.

[![Version](https://img.shields.io/badge/version-2.8.0-2563eb)](VERSION)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776ab?logo=python&logoColor=white)](#requirements)
[![Dependencies](https://img.shields.io/badge/dependencies-none-16a34a)](#requirements)
[![License: MIT](https://img.shields.io/badge/license-MIT-f59e0b)](LICENSE)

[Quick start](#quick-start) · [User manual](MANUAL.md) · [الدليل العربي](GUIDE.ar.md) · [Command reference](#command-reference)

</div>

---

## Contents

- [Why it exists](#why-it-exists)
- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Supported agent tools](#supported-agent-tools)
- [Let an agent set it up](#let-an-agent-set-it-up)
- [Installation](#installation)
- [Project setup](#project-setup)
  - [Collect onboarding evidence](#1-collect-onboarding-evidence)
  - [Describe the project](#2-describe-the-project)
  - [Declare verified commands](#3-declare-verified-commands)
  - [Create a feature spec](#4-create-a-feature-spec)
  - [Customize routing](#5-customize-routing)
  - [Enforce architecture](#6-enforce-architecture)
  - [Define scopes](#7-define-scopes)
  - [Record bugs and discoveries](#8-record-bugs-and-discoveries)
  - [Split long specifications](#9-split-long-specifications)
- [Daily usage](#daily-usage)
- [Command reference](#command-reference)
- [Changing requirements and decisions](#changing-requirements-and-decisions)
- [Technology profiles](#technology-profiles)
- [Instruction precedence](#instruction-precedence)
- [Upgrading and maintenance](#upgrading-and-maintenance)
- [Limitations](#limitations)
- [Repository layout](#repository-layout)
- [Development](#development)
- [License](#license)

## Why it exists

A coding agent that opens a repository for the first time knows nothing about it. It guesses the build
command, reads far more context than it needs, crosses boundaries it cannot see, and forgets every
decision the moment the session ends.

Universal Agent Workflow gives the repository a small, durable memory that every agent reads the same
way. The framework is split by how fast each part changes:

| Layer | Contains | Changes |
|---|---|---|
| `core/` | Operating principles | Rarely |
| `workflows/` | Guidance per task type: feature, bug fix, diagnosis, refactor, review | Occasionally |
| `profiles/` | Optional technology guidance | Per stack |
| `.agent/` in your project | Facts, specs, decisions, architecture rules, commands | With the project |

New to the concepts? [MANUAL.md](MANUAL.md) explains them with diagrams and walks through one feature
end to end. This README is the installation guide and command reference.

## Features

- **One-command onboarding** — `setup` reads the repository and fills the project profile and command
  table from evidence, each value tied to the file it came from. It never invents a fact, never runs a
  command, and never overwrites what a person wrote.
- **Task routing** — resolves which scope owns a path and loads only the context that matters.
- **Architecture gates** — executable boundary checks that distinguish *no violations* from *nothing was checked*.
- **Feature specs** — parallel specs with lifecycle approvals and requirement traceability. No unowned
  assumption or unresolved decision reaches an accepted spec.
- **Change impact** — maps staged, unstaged, and untracked Git changes to scopes and their downstream consumers.
- **Bounded task chains** — one task per clean context for work that outgrows a session. A failing task
  advances nothing.
- **Section-level retrieval** — outline, search, and read one part of a long document instead of the whole file.
- **Durable decisions** — rationale that survives individual conversations and agent sessions.
- **Safe by default** — never overwrites an existing agent setup, pointer file, or Git hook.
- **Zero dependencies** — standard-library Python only.

## Requirements

- Python 3.9 or later (or PowerShell for the optional installer).
- An existing project directory with write access.
- Git, for change detection and the optional pre-commit hook.

The workflow never installs project dependencies and never modifies application source code.

## Quick start

Two commands — the first from **this** repository, the second from **your** project:

```shell
python scripts/install_workflow.py ../your-project
cd ../your-project
python .agent/workflow.py setup --ask
```

`setup` reads the repository and fills everything the evidence can prove, then `--ask` asks you the few
questions no file can answer — purpose, users, security constraints. Press Enter to skip any of them.
Drop `--ask` when an agent runs the setup.

| `setup` step | What happens | What never happens |
|---|---|---|
| `bootstrap` | Scans manifests, lockfiles, CI, READMEs, and layout into `.agent/ONBOARDING.md`, every suggestion with its evidence | No command is run |
| `adopt` | Writes evidence-backed facts into `PROJECT.md` and commands into `COMMANDS.md` | A value someone wrote is never replaced; convention-only guesses are never written |
| `local-init` | Builds `.agent/INDEX.json` and `.agent/dashboard.html` | No source code is touched |
| `sync-entrypoints` | Creates pointer files for tools that ignore `AGENTS.md` | Existing pointer files are left alone |
| `doctor` | Lists what is still `TODO` | Unfilled fields warn; they do not fail |

On a typical repository `setup` fills the source, test, and documentation paths, the frameworks,
databases and services, the deployment target, runtime versions, and every declared command — each
value followed by the file it came from:

```markdown
- System shape: Angular 18 (root), Express 4 (`backend/`) _(evidence: `package.json`, `backend/package.json`)_
- External systems: PostgreSQL, SMTP email _(evidence: `backend/package.json`)_
- Deployment environment: Netlify _(evidence: `netlify.toml`)_
```

**Then use it.** Open the project in your agent tool and ask for work in plain language:

```text
Allow customers to cancel an order before fulfillment begins.
```

> [!TIP]
> After installation, prefer the wrapper for your shell — it resolves whichever Python is installed.
>
> | Shell | Command |
> |---|---|
> | POSIX (`sh`, `bash`, `zsh`) | `./.agent/workflow.sh <command>` |
> | Windows | `.agent\workflow.cmd <command>` |
> | PowerShell | `pwsh -NoProfile -ExecutionPolicy Bypass -File .agent/workflow.ps1 <command>` |
>
> Any command may be run from a subdirectory. Use `python3` where that is the local command name.

## Supported agent tools

The entry point is `AGENTS.md` at the repository root. For tools that read their own file instead,
`sync-entrypoints` writes a short pointer back to `AGENTS.md`, so there is only ever one source of truth.

| Tool | Reads | Needs `sync-entrypoints` |
|---|---|---|
| OpenAI Codex | `AGENTS.md` | No |
| Claude Code | `CLAUDE.md` (recent versions also read `AGENTS.md`) | Recommended |
| GitHub Copilot | `.github/copilot-instructions.md` | Yes |
| Cursor | `.cursor/rules/*.mdc` | Yes |
| Gemini CLI | `GEMINI.md` | Yes |
| Anything else | `AGENTS.md`, or point it there yourself | — |

Add or remove targets with `entry_points` in `.agent/config/workflow.json`.

## Let an agent set it up

Instead of running the setup yourself, paste this into any agent with shell access:

```text
Set up the Universal Agent Workflow in this repository.

1. Install it:  python <path-to-this-repo>/scripts/install_workflow.py .
   Use python3 if that is the local command name.
2. Run setup through the wrapper for your shell
   (./.agent/workflow.sh setup on POSIX, .agent\workflow.cmd setup on Windows).
3. Run every command in .agent/COMMANDS.md once. Fix or remove any row that fails,
   and replace any remaining TODO row with a command you confirmed by running it.
4. For every field in .agent/PROJECT.md still marked TODO, find the answer in this
   repository and cite the file. Anything you cannot ground in a file stays the literal
   word "unknown". Do not infer the product purpose or its users from the code — ask me.
5. Correct any adopted value the code contradicts.
6. Declare a scope only where work would genuinely be routed differently, and an
   architecture module only for a boundary the code really has.
7. Do not modify application source code.
8. Finish with build-index, then doctor, and tell me what is still undescribed and what
   you need from me.
```

The agent stops at facts it cannot prove instead of inventing them, so expect questions back.
Answering them is the real work; everything else is mechanical.

## Installation

Clone or download this repository, then run one of the installers from its root:

```shell
python scripts/install_workflow.py ../your-project          # cross-platform
```

```powershell
./scripts/Install-Workflow.ps1 -ProjectPath ../your-project # PowerShell
```

Relative and absolute paths both work. Without a scripting runtime, copy `template/AGENTS.md` and
`template/.agent/` into the project, then copy `core/`, `workflows/`, `profiles/`, and `tooling/` into
`.agent/vendor/universal-agent-workflow/`.

> [!WARNING]
> Both installers refuse to replace an existing `AGENTS.md` or `.agent/`. The PowerShell installer
> exposes `-Force`, which may replace project-specific configuration. Back up first, and never use it
> to upgrade — use [`scripts/update_workflow.py`](#upgrading-and-maintenance) instead.

<details>
<summary><b>What gets installed</b></summary>

```text
your-project/
├── AGENTS.md                      entry point for every agent
├── .github/workflows/
│   └── agent-workflow.yml         CI: validation and architecture gates
└── .agent/
    ├── PROJECT.md                 purpose, users, paths, constraints
    ├── COMMANDS.md                verified build, test, and run commands
    ├── ROUTER.md                  which context to read for which area
    ├── DECISIONS.md               durable decision records
    ├── HANDOFF.md                 transient session state
    ├── LOCAL.md                   local workflow commands
    ├── config/
    │   ├── architecture.json      module boundaries
    │   ├── local.json
    │   ├── onboarding.json
    │   ├── scopes.json            scope ownership and verification
    │   └── workflow.json          entry points and budgets
    ├── specs/                     one folder per feature spec
    ├── scopes/                    one folder per scope
    ├── findings/
    │   ├── bugs/
    │   └── discoveries/
    ├── requirements/
    │   ├── CURRENT.md
    │   └── CHANGES.md
    ├── workflow.py                CLI entry point
    ├── workflow.sh | .cmd | .ps1  shell wrappers
    └── vendor/
        └── universal-agent-workflow/
```

</details>

Two optional steps wire the workflow into surrounding tooling. Neither runs automatically, and neither
overwrites a file you already have:

```shell
python .agent/workflow.py sync-entrypoints   # CLAUDE.md, GEMINI.md, Copilot, Cursor pointers
python .agent/workflow.py install-hooks      # pre-commit hook that keeps .agent/INDEX.json current
```

The hook refuses to replace a `pre-commit` hook it did not write.

## Project setup

`setup` performs steps 1–3 for you; this section explains them and how to take control. Scopes, specs, and architecture rules are optional levels you
add when the repository actually needs them — [MANUAL.md](MANUAL.md) explains when each one earns its cost.

### 1. Collect onboarding evidence

```shell
python .agent/workflow.py bootstrap
```

The scan reads manifests, lockfiles, package scripts, Makefile targets, solution files, CI workflows,
READMEs, and directory structure, then writes `.agent/ONBOARDING.md` — and nothing else.

Every suggestion carries its source file and a confidence label:

| Label | Meaning | Adopted automatically |
|---|---|---|
| `ci` | Appears in a CI pipeline | Yes |
| `declared` | Declared in a manifest | Yes |
| `documented` | Stated in the repository's own README | Yes |
| `observed` | Seen in the repository's files and directories | Yes |
| `derived` | Inferred from ecosystem convention only | No — waits for a person |

Change the adopted labels with `adopt_confidence` in `.agent/config/onboarding.json`. Nothing is labelled
verified, because bootstrap never runs a command. A repository with no code yet is
reported as `mode: greenfield`, with the inverted order of work explained. Regenerate with `--force`, or
read it as JSON with `--json`.

### 2. Describe the project

```shell
python .agent/workflow.py adopt
```

`adopt` writes every evidence-backed fact into a `PROJECT.md` field that is still `TODO`, followed by its
evidence, and never touches a value someone already wrote — run it again at any time. What remains is
what only a person knows: users, business capabilities, intended boundaries, and security constraints.
Answer them with `setup --ask`, by editing the file, or by handing the prompt at the end of
`ONBOARDING.md` to an agent. Keep unknown facts explicitly `unknown`.

### 3. Declare verified commands

The same `adopt` run fills `.agent/COMMANDS.md` from CI pipelines and manifests, and marks operations
nothing declares as `not declared` so agents do not go looking for them:

```markdown
| Operation | Command | Prerequisites | Evidence |
|---|---|---|---|
| Restore | `dotnet restore App.slnx` | `dotnet` installed | `App.slnx` |
| Build | `dotnet build App.slnx --no-restore` | Restore completed | `App.slnx` |
| Lint | not declared | — | no manifest, Makefile, or CI step declares one |
```

Commands inferred from convention alone stay `TODO` until someone confirms them. Run each row once
before trusting it — bootstrap reads commands, it never runs them.

### 4. Create a feature spec

Create an independent spec for each feature or material change:

```shell
python .agent/workflow.py create-spec customer-cancellation --title "Customer cancellation" --owner "Product"
```

Define the outcome, scope, acceptance evidence, assumptions, open decisions, and owner in its
`spec.json` and `spec.md`. Then regenerate the execution artifacts:

```shell
python .agent/workflow.py generate-plan customer-cancellation
python .agent/workflow.py generate-tasks customer-cancellation
```

Transition to `Accepted` only after an authorized stakeholder approves:

```shell
python .agent/workflow.py transition customer-cancellation Accepted --actor "Product Owner"
```

After implementation, link each requirement to its task, code, tests, and evidence. Unknown task ids and
missing paths are rejected:

```shell
python .agent/workflow.py link-requirement customer-cancellation REQ-001 \
  --task TASK-001 --code src/orders.py --test tests/test_orders.py --evidence "CI run 42"
python .agent/workflow.py transition customer-cancellation Implemented --actor "Engineering" --evidence "CI run 42"
```

### 5. Customize routing

Edit `.agent/ROUTER.md` when different areas need different context. Keep each route narrow — agents
should load the smallest set of references the task needs.

```markdown
| Scope | Read before working |
|---|---|
| Backend API | docs/backend.md |
| Web client | docs/frontend.md |
```

### 6. Enforce architecture

Edit `.agent/config/architecture.json`. Each module declares its path, recognized import prefixes, and
the modules it may depend on. Rules are project data, not folder conventions, so this fits layered,
feature-based, and monorepo layouts alike.

```json
{
  "schema_version": 1,
  "adapter_mode": "auto",
  "modules": [
    {
      "name": "orders-domain",
      "path": "src/Features/Orders/Domain",
      "import_prefixes": ["Features.Orders.Domain", "@features/orders/domain"],
      "may_depend_on": []
    },
    {
      "name": "orders-infrastructure",
      "path": "src/Features/Orders/Infrastructure",
      "import_prefixes": ["Features.Orders.Infrastructure", "@features/orders/infrastructure"],
      "may_depend_on": ["orders-domain"]
    }
  ]
}
```

- A fresh install ships `"modules": []`, and `check-architecture` says so instead of reporting green.
- A module whose path does not exist is an error, not a silent pass.
- Imports are parsed language-aware, so comments and docstrings are never mistaken for dependencies.
- Prefix rules cover Python, JavaScript/TypeScript, Dart, Go, Rust, Java/Kotlin, C/C++, C#, Ruby, and PHP.
  .NET project references and `package.json` workspaces are read by adapters when present; disable them
  with `"adapter_mode": "off"`.
- `node_modules`, `bin`, `obj`, `.venv`, and similar directories are skipped; override with `ignored_directories`.

Run the gates locally — the installed GitHub Actions workflow runs the same checks on every push and pull request:

```shell
python .agent/workflow.py validate
python .agent/workflow.py check-architecture
python .agent/workflow.py report --output workflow-report.json
```

### 7. Define scopes

Split a large codebase into application or business scopes instead of one global context file:

```shell
python .agent/workflow.py create-scope frontend --title "Web frontend" --kind application --path apps/web
python .agent/workflow.py create-scope api --title "Public API" --kind application --path apps/api --verify "tests=python -m pytest tests/api"
python .agent/workflow.py create-scope mobile --title "Mobile apps" --kind application --path apps/mobile --depends-on api --verify "tests=flutter test"
python .agent/workflow.py create-scope checkout --title "Checkout" --kind business --path apps/web/src/checkout --parent frontend
```

Each scope gets a profile, current state and assumptions, decisions, and change history. Nested scopes
inherit their parent's context. Resolve ownership and impact:

```shell
python .agent/workflow.py build-index
python .agent/workflow.py route apps/web/src/checkout/page.tsx
python .agent/workflow.py route-changes --base origin/main
python .agent/workflow.py impact apps/api/src/orders.py apps/mobile/lib/orders.dart
```

Validation rejects missing context, duplicate ownership, hierarchy cycles, and overlapping paths without a
parent/child relationship. Impact analysis expands changed scopes to their downstream consumers and
returns their verification commands. Record a material change with:

```shell
python .agent/workflow.py record-scope-change checkout --summary "Cancellation boundary changed" \
  --actor "Product" --classification replacement --impact API --impact mobile
```

### 8. Record bugs and discoveries

```shell
python .agent/workflow.py create-finding bug duplicate-order --title "Duplicate order" --reporter "Support" --severity high --scope api
python .agent/workflow.py create-finding discovery provider-limit --title "Provider rate limit" --reporter "Engineering" --severity medium --scope api
```

Findings keep details and evidence outside conversation history. Their lifecycle is `Open`, `Triaged`,
`Planned`, `Resolved`, or `Dismissed`; resolving or dismissing requires evidence.

### 9. Split long specifications

Keep one spec manifest while splitting large requirements into cohesive sets. Requirement ids stay unique
across the whole bundle:

```shell
python .agent/workflow.py add-requirement-set checkout-platform eligibility --title "Eligibility rules"
python .agent/workflow.py add-requirement-set checkout-platform payments --title "Payment rules"
```

## Daily usage

Ask for work in plain language. `AGENTS.md` instructs the agent to:

1. Resolve the paths it will touch and read only the matching context.
2. Select the task workflow and technology profiles.
3. Establish the outcome, constraints, and acceptance evidence.
4. Make the smallest coherent change, preserving unrelated work and existing boundaries.
5. Verify with the repository's declared commands.
6. Record durable decisions and report what was verified and what remains uncertain.

<details>
<summary><b>Example requests</b></summary>

| Task | Request |
|---|---|
| Feature | `Add Microsoft sign-in. One account per email is in scope. Preserve the existing sign-in flow.` |
| Bug fix | `Editing a customer address clears the postal code. Find the cause, fix it, and verify that creating a new address still works.` |
| Diagnosis | `Diagnose why the reports page is slow. Do not modify files. Report the cause, evidence, and viable fixes.` |
| Review | `Review the current payment changes for correctness, security, and data-integrity issues. Do not fix them yet.` |

</details>

### Task chains for long work

For work too large for one session, run it as a chain so each task gets a clean context:

```shell
python .agent/workflow.py run start <spec>         # seed the run from tasks.md
python .agent/workflow.py run next <spec>          # brief for exactly one task
python .agent/workflow.py run complete <spec> <task> --code src/x.py --test tests/test_x.py --evidence "..." --handoff "..."
python .agent/workflow.py run retry <spec> <task>  # unblock after fixing what broke
python .agent/workflow.py run replan <spec>        # adopt a rewritten tasks.md
python .agent/workflow.py run report <spec>        # what the chain actually cost
```

`complete` advances only when the declared files exist, actually changed since the task started, and the
owning scope's verification passes. A failing task writes no evidence and no handoff, and the chain halts
after `task_max_attempts`. Pass `--allow-no-change` for a task that legitimately edits nothing.

### Reading long documents

```shell
python .agent/workflow.py outline MANUAL.md                     # section ids and line counts
python .agent/workflow.py read MANUAL.md --section <section-id> # one section, plus the full table of contents
python .agent/workflow.py find "task handoff" --path docs/      # ranked section references
```

Nothing is indexed, so nothing goes stale. `find` is lexical and returns the narrowest matching section,
and every `read` includes the table of contents so a narrow read never hides what it skipped.

## Command reference

Run any command with `--help` for its full options. `validate`, `check-architecture`, and `doctor` accept
`--json`.

| Area | Command | Purpose |
|---|---|---|
| Setup | `setup [--ask]` | Scan, adopt, index, and link in one step; `--ask` prompts for the rest |
| | `bootstrap` | Scan the repository into evidence-backed suggestions |
| | `adopt` | Write evidence-backed facts and commands into fields still `TODO` |
| | `local-init` | Build the index and dashboard |
| | `sync-entrypoints` | Write pointer files for other agent tools |
| | `install-hooks` | Install the index-refreshing pre-commit hook |
| | `doctor` | Report what is missing, unfilled, or drifted |
| Routing | `route <path>` | Scope chain and context for a path (`--intent`, `--task`) |
| | `route-changes` | Scopes touched by current Git changes (`--base`) |
| | `impact <paths…>` | Downstream scopes and their verification plan |
| | `context-budget <path>` | Estimate the routed instruction footprint |
| | `build-index` · `check-index` | Rebuild or verify `.agent/INDEX.json` |
| Specs | `create-spec` · `sync-spec` | Create a spec or sync its metadata |
| | `generate-plan` · `generate-tasks` | Regenerate execution artifacts |
| | `transition` | Move a spec through its lifecycle |
| | `link-requirement` | Trace a requirement to task, code, tests, evidence |
| | `add-requirement-set` | Split a spec into requirement sets |
| Scopes | `create-scope` · `record-scope-change` | Declare scopes and record material changes |
| Findings | `create-finding` · `transition-finding` | Record and resolve bugs and discoveries |
| Gates | `validate` · `check-architecture` | Validate artifacts and enforce boundaries |
| | `local-check` | All gates plus impact; `--execute` runs scope verification |
| | `verify` · `report` | Run scope verification for paths or changes; write a JSON report |
| Execution | `run start\|next\|complete\|retry\|replan\|status\|report` | Bounded task chains |
| Session | `handoff` · `agent-budget` | Session handoff and agent fan-out limits |
| Documents | `outline` · `read` · `find` | Section-level document retrieval |
| Maintenance | `migrate` · `dashboard` | Upgrade artifact layout, regenerate the dashboard |

## Changing requirements and decisions

Conversation history is context, not the source of truth. When a stakeholder changes a requirement:

1. Classify it: `clarification`, `additive`, `replacement`, or `reversal`.
2. Update the owning `.agent/specs/<spec-id>/` artifacts.
3. Add an entry to `.agent/requirements/CHANGES.md`.
4. Identify affected behavior, data, APIs, tests, documentation, and decisions.
5. Revalidate the assumptions and acceptance evidence it touches.

```markdown
- Date: 2026-08-30
- Requested by: Product Owner
- Classification: replacement
- Previous requirement: Customers can cancel before shipping
- New requirement: Customers can cancel before fulfillment begins
- Reason: Orders being processed by the warehouse cannot be cancelled
- Impacted areas: order state machine, API, client application, tests, documentation
- Required verification: cancellation boundary tests for every order state
```

When reasonable interpretations would lead to materially different architecture, cost, security, data, or
user-visible behavior, the agent asks for a decision instead of choosing silently.

Use `.agent/DECISIONS.md` for decisions whose rationale should outlive the current task — a new component
boundary, a changed public contract, an external provider, a temporary architectural exception. Do not
record details the code already makes clear.

## Technology profiles

Shipped profiles: [.NET](profiles/dotnet.md), [JavaScript/TypeScript](profiles/javascript-typescript.md),
and [Python](profiles/python.md). A project may use several, and project rules always override them.

To add one, create a focused Markdown file in `profiles/` containing only guidance that changes agent
decisions — package-manager detection, meaningful verification, non-obvious operational constraints.
Do not repeat the core workflow.

## Instruction precedence

When instructions conflict:

1. The user's current explicit request.
2. Safety and authorization boundaries.
3. Project-specific instructions and accepted requirements.
4. Matching technology profiles.
5. Universal workflow defaults.

A higher-priority instruction never implicitly authorizes destructive operations, production changes,
or external communication.

## Upgrading and maintenance

Update the vendored framework while keeping every project-owned scope, spec, finding, decision, and
configuration:

```shell
python scripts/update_workflow.py ../your-project --migrate
```

The previous bundle is moved to `.agent/backups/` first and restored if the replacement fails. To upgrade
an older artifact layout in place:

```shell
python .agent/workflow.py migrate
python .agent/workflow.py build-index
python .agent/workflow.py doctor
```

Generated plans and tasks carry requirement digests, so `doctor` detects drift; resolve it with
`sync-spec`, `generate-plan`, and `generate-tasks`.

## Limitations

- `bootstrap` classifies commands by name and location. It cannot know a script does what it is called,
  and `adopt` writes declared commands without running them — run each once before relying on it.
- Facts are read from manifests and layout, not from running code. Framework and service detection covers
  common packages; anything else stays `TODO`.
- Architecture rules match declared import prefixes. They do not resolve aliases from `tsconfig.json`,
  bundler configs, or build-time path mapping.
- `local-check --execute` runs the commands in `.agent/config/scopes.json` through the shell, unsandboxed,
  limited only by `command_timeout_seconds`. Treat that file as trusted input and review changes to it.
- `run complete` proves the declared files changed, not that the change was right. It does not replace
  reviewing the diff.
- Change detection needs Git; outside a repository only scope verification runs.
- `run report` measures what a chain cost, but cannot compare it with the single long session you did not run.
- `requirements/CURRENT.md` is a migration fallback for installations that predate feature specs.

## Repository layout

```text
universal-agent-workflow/
├── README.md              installation and reference
├── MANUAL.md              concepts, diagrams, end-to-end walkthrough
├── GUIDE.ar.md            Arabic practical guide
├── core/                  durable operating principles
├── workflows/             guidance per task type
├── profiles/              optional technology guidance
├── template/              files installed into a project
├── tooling/               the workflow CLI, one package per feature
│   ├── workflow.py
│   ├── workflow_config.py
│   └── workflow_features/
├── scripts/               installers and updater
└── tests/
```

## Development

The CLI is standard-library Python with no dependencies. From the repository root:

```shell
python -m unittest discover -s tests -p "test_*.py"   # run the test suite
python -m tooling.workflow --help                     # run the CLI from source
```

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Released under the [MIT License](LICENSE).
