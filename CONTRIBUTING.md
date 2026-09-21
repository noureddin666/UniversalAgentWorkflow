# Contributing

Thanks for helping improve Universal Agent Workflow. Issues and pull requests are welcome.

## Getting started

The CLI is standard-library Python 3.9+ with no dependencies, so there is nothing to install.

```shell
python -m unittest discover -s tests -p "test_*.py"   # run the test suite
python -m tooling.workflow --help                     # run the CLI from source
```

To try a change end to end, install into a throwaway copy of a real repository:

```shell
python scripts/install_workflow.py ../some-project-copy
cd ../some-project-copy
python .agent/workflow.py bootstrap
python .agent/workflow.py doctor
```

## Guidelines

- **One feature, one package.** Each capability lives in its own package under
  `tooling/workflow_features/`. Features talk to each other through the names their `__init__.py`
  exports, never through another feature's internals.
- **No new dependencies.** The tool is copied into every project it is installed in; the standard
  library is the whole runtime.
- **No invented facts.** Anything that describes a user's project must come from evidence in that
  project. When the evidence is missing, say `unknown`.
- **Never overwrite user files.** Installers, pointer files, and hooks refuse to replace what they did
  not write.
- **Keep Python 3.9 compatible.** CI runs the suite on 3.9 and on the latest release.
- **Comments explain why, not what.** Prefer no comment over one that restates the code.
- **Tests with every change.** Add or update a test in `tests/` for any behavior you change.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make a focused change and add tests.
3. Run the suite and make sure it passes.
4. Update `README.md`, `MANUAL.md`, or `GUIDE.ar.md` when user-facing behavior changes.
5. Open a pull request that explains what changed and why.

## Releasing

Bump `VERSION` and the version badge in `README.md` together.
