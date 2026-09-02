# `setup-local` JSON output

Use `--output json` and branch on `ok`. Successful runs exit zero; pipeline failures emit one JSON object to stdout and exit nonzero. Pre-pipeline failures may emit only stderr.

## Result fields

| Field | When present | Meaning |
|---|---|---|
| `schemaVersion` | Always | Contract version, currently `1`. |
| `command` | Always | `"environments setup-local"`. |
| `ok` | Always | Whether the pipeline succeeded. |
| `mode` | Always | `"default"` or `"constraints-only"`. |
| `dryRun` | Always | Whether the run was preview-only. |
| `compute` | After target resolution | `source`, optional `clusterId`/`serverlessVersion`, and report-safe `envKey`. |
| `resolved` | After constraint fetch | `pythonVersion`, optional `dbconnectVersion`, and `artifactSource` (`network` or `cache`). |
| `greenfield` | Always | Whether no `pyproject.toml` existed once merge planning ran; otherwise `false`. |
| `plan` | Dry-run | `wouldWrite`, optional `wouldBackup`/`wouldInstallPython`, and `diff`. |
| `venvPath` | Successful real run | Provisioned environment path, normally `.venv`. |
| `phases` | Always | `preflight`, `resolve`, `fetch`, `merge`, `provision`, and `validate`, each `ok`, `error`, or `pending`. |
| `warnings` | Always | Stable warning codes plus human-readable messages. |
| `error` | Always | `null` on success; otherwise `code`, `failurePhase`, `message`, and whether `diskMutated`. |
| `backupPath` | When a backup was written | Backup of the previous `pyproject.toml`. |
| `durationMs` | Always | Pipeline duration. |

Dry-run skips writability and `uv` availability checks, does not populate the cache, and does not provision or validate. Its latter phases can therefore report `ok` without executing those operations.

## Warning actions

Always surface warnings. These require user action:

| Code | Action |
|---|---|
| `W_DBCONNECT_PIN_DUPLICATED` | Remove or reconcile the duplicate pin if its range conflicts. |
| `W_USER_CONSTRAINT_CONFLICT` | Reconcile the user dependency with the compute constraint. |
| `W_STALE_ENVIRONMENT_VERSION` | Review the stale serverless version after switching to a cluster target. |
| `W_STANDALONE_PYSPARK_CONFLICT` | Keep standalone `pyspark` in a separate environment from `databricks-connect`. |

`W_REQUIRES_PYTHON_OVERRIDDEN`, `W_DBCONNECT_PIN_OVERRIDDEN`, and `W_DBCONNECT_CONSOLIDATED` describe changes already planned or applied; report them for visibility.

## Parse safely

Capture stdout and stderr separately; do not pipe the command directly into `jq`. If stdout contains valid JSON, parse it and branch on `ok` even when the command exited nonzero. If stdout is empty or invalid JSON, surface stderr as a pre-pipeline failure instead of producing a secondary parse error.

Do not key decisions on `error.message` unless [troubleshooting](troubleshooting.md) explicitly requires distinguishing multiple causes behind one error code.
