# Local workflow

Initialize generated indexes and the dashboard:

```shell
workflow local-init
```

Inspect all current Git changes and affected scopes:

```shell
workflow route-changes
```

Run local quality checks without executing project commands:

```shell
workflow local-check
```

Execute the verification commands owned by affected scopes:

```shell
workflow local-check --execute
```

Verification output is stored under `.agent/runs/`. Open `.agent/dashboard.html` directly in a browser after running `dashboard` or `local-init`.
