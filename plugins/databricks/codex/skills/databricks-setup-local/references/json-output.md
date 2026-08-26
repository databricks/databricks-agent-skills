# `setup-local` JSON Output Contract

Run `databricks environments setup-local ... --output json`. On both success and failure, a single JSON object is written to **stdout** and the process exits 0 (success) or non-zero (failure). Parse this object — do not scrape the human-readable text.

**Exception:** an authentication / pre-pipeline failure is reported as a normal CLI error on **stderr** *before* any JSON object exists (see the parent `SKILL.md` preflight). If stdout has no JSON, read stderr; that path is not represented below.

## Top-level fields

| Field | Type | Meaning |
|-------|------|---------|
| `schemaVersion` | int | Contract version (currently `1`). Bumped only on a breaking shape change. |
| `command` | string | Always `"environments setup-local"`. |
| `ok` | bool | `true` iff the run succeeded. Branch on this first. |
| `mode` | string | `"default"` or `"constraints-only"`. |
| `dryRun` | bool | `true` for `--dry-run` (nothing written). |
| `compute` | object | Resolved target (below). Present once resolve succeeds. |
| `resolved` | object | Resolved environment definition (below). Present once fetch succeeds. |
| `greenfield` | bool | `true` when no prior `pyproject.toml` existed (a fresh one was rendered). |
| `plan` | object | `--dry-run` only: `wouldWrite`, `wouldBackup`, `wouldInstallPython`, `diff`. |
| `venvPath` | string | Provisioned virtualenv, **relative to the project root** (`.venv`). Set only on a successful **non-dry-run** — a `--dry-run` returns before the validate phase, so it is absent there. |
| `phases` | array | Every phase with a status (below). Always the full canonical list. |
| `warnings` | array | Non-fatal advisories (below). Always present (`[]` when none). |
| `error` | object\|null | Failure detail (below). `null` on success. |
| `backupPath` | string | Path of the `pyproject.toml` backup written this run, if any. |
| `durationMs` | int | Pipeline wall time in milliseconds. |

### `compute`

| Field | Meaning |
|-------|---------|
| `source` | Which precedence source resolved the target: `"cluster"`, `"serverless"`, `"job"`, or `"bundle"`. |
| `clusterId` | Cluster ID (cluster/bundle-cluster targets). |
| `serverlessVersion` | Normalized serverless version, e.g. `"v5"` (serverless/bundle-serverless targets). |
| `envKey` | The environment key the constraints were fetched for (e.g. `dbr/...` or `serverless/...`). Include this in bug reports. |

### `resolved`

| Field | Meaning |
|-------|---------|
| `pythonVersion` | The Python minor the env pins (e.g. `"3.12"`). |
| `dbconnectVersion` | Installed `databricks-connect` version. Present in default mode; **omitted** in constraints-only mode. |
| `artifactSource` | `"network"` (fetched fresh) or `"cache"` (offline fallback from a prior fetch). |

## Phases

Fixed order; the `phases` array reports each with a `status` of `"ok"`, `"error"`, or `"pending"`. On failure, phases before the failing one are `ok`, the failing one is `error`, and the rest stay `pending`.

| Phase | Does |
|-------|------|
| `preflight` | Flag validation, manager detection, writability, `uv` availability. |
| `resolve` | Compute target → environment key. |
| `fetch` | Download the constraint artifact for that env key (or use cache). |
| `merge` | Compute the merged `pyproject.toml` (backup + write on a real run). |
| `provision` | Ensure Python, run `uv sync`, seed pip. |
| `validate` | Assert the venv's Python (and `databricks-connect` major, default mode) match the target. |

Under `--dry-run` the `preflight` phase does less than the table's row implies: it validates flags and detects the manager but **skips** the writability and `uv`-availability checks (a dry run writes nothing and installs nothing). The `merge` phase computes the plan without writing, and `provision`/`validate` are reported `ok` without touching disk.

`error.failurePhase` names the phase that failed and always matches the `error`-status entry in `phases`.

## Warning codes (`warnings[].code`)

All emitted from the `merge` phase, where the environment's pins can conflict with what the project already declares. Non-fatal, but several need a manual follow-up — surface them to the user. `warnings[].message` is human text (not part of the stable contract); key off `code`.

| Code | Meaning / action |
|------|------------------|
| `W_REQUIRES_PYTHON_OVERRIDDEN` | The project's `requires-python` differed from the env pin and was replaced by the managed value. Informational. |
| `W_DBCONNECT_PIN_OVERRIDDEN` | A `databricks-connect` pin in the managed dev group was replaced by the managed value. Informational. |
| `W_DBCONNECT_CONSOLIDATED` | A conflicting `databricks-connect` pin declared elsewhere was removed so the project resolves. Informational. |
| `W_DBCONNECT_PIN_DUPLICATED` | A `databricks-connect` pin the merge could neither rewrite nor remove now coexists with the managed pin. If their ranges are disjoint, **uv cannot resolve** — needs a manual fix. |
| `W_USER_CONSTRAINT_CONFLICT` | A user dependency pins a package to a range provably disjoint from the env's constraints. **uv will fail to resolve** — needs a manual fix. |
| `W_STALE_ENVIRONMENT_VERSION` | Cluster target, but the file still carries a serverless `[tool.databricks.environment].environment_version` from an earlier run. It now describes a target the project is no longer set up for. |
| `W_STANDALONE_PYSPARK_CONFLICT` | A standalone `pyspark` is declared alongside `databricks-connect`; they share the `pyspark` namespace and overwrite each other. Remove the standalone `pyspark`. |

## Reading a result

```bash
res=$(databricks environments setup-local --serverless-version 5 --output json)
ok=$(jq -r '.ok' <<<"$res")
if [ "$ok" = "true" ]; then
  jq -r '"target=\(.compute.envKey) python=\(.resolved.pythonVersion) venv=\(.venvPath)"' <<<"$res"
  jq -r '.warnings[] | "warning \(.code): \(.message)"' <<<"$res"   # surface follow-ups
else
  jq -r '"FAILED \(.error.code) at \(.error.failurePhase): \(.error.message)"' <<<"$res"
  # → follow references/troubleshooting.md to fix or route the failure
fi
```

Error-code handling and repository routing: see [troubleshooting.md](troubleshooting.md).
