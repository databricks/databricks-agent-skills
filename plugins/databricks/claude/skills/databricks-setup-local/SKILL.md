---
name: databricks-setup-local
description: "Provision a local Python environment matched to a Databricks cluster or serverless version with `databricks environments setup-local`. Use when you need to run or debug PySpark (Databricks Connect) code locally, or want a local .venv whose Python and dependency pins match a compute target."
compatibility: Requires databricks CLI (>= v1.12.0) and uv
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Setup-Local

Provision a local Python environment that matches a Databricks compute target, so code you run on your machine behaves the way it does on Databricks. The `databricks environments setup-local` command installs the matching Python version and (by default) a compatible `databricks-connect`, pins your dependencies to versions known to work with that compute, and creates or updates a `uv`-managed `.venv` plus `pyproject.toml` in the current directory.

**FIRST**: Use the parent [`databricks-core`](../databricks-core/SKILL.md) skill for CLI install and authentication basics. This skill assumes an authenticated CLI.

## When to Use This Skill

- **Primary — run/debug Spark locally.** You want to run or debug **PySpark code on your machine** against a Databricks cluster or serverless. Default mode installs a `databricks-connect` matched to that compute, giving your local Python a remote Spark session that behaves like it does on Databricks (no notebook needed). This is how you *provision* the environment that [`databricks-execution-compute`](../databricks-execution-compute/SKILL.md) then *runs* code in (Databricks Connect is its top execution mode).
- **Also — a runtime-matched env without Connect.** You want a local `.venv` whose **Python version and dependency constraints match** a given compute, but you do *not* want `databricks-connect` added (e.g. running non-Spark project code, or you manage `databricks-connect` yourself). Use `--constraints-only`.

Do **not** use this skill to run code on Databricks compute (use `databricks-execution-compute`), or to create/resize clusters and warehouses (also `databricks-execution-compute`).

## Reference Documentation

- **[JSON output contract](references/json-output.md)** — every field of `--output json`, the six phases, warning codes, and how to read a result programmatically.
- **[Troubleshooting & failure routing](references/troubleshooting.md)** — each error code, whether it is user-fixable or a defect to report, and which repository to route a report to.

## Workflow

Always run with `--output json` when driving this from an agent, and parse the result object — never scrape the human text. See [references/json-output.md](references/json-output.md).

### 1. Preflight (mirror the extension's checks)

Fail fast on the things the command cannot fix for the user:

1. **CLI version** — `databricks version` must be **>= v1.12.0** (the release where `setup-local` became visible and its constraint source was pinned to the public `databricks/environments` repo). Older CLIs either lack the command or point at a private source.
2. **Authentication** — `databricks auth describe` must resolve a workspace. Auth failures surface here as a **normal CLI error on stderr before any JSON is produced** (the command's own workspace-client preflight, not a pipeline phase), so they are *not* in the JSON contract — check for them up front. This command resolves auth from your **profile/env only**; a bundle's `workspace.host`/`profile` do **not** feed it.
3. **`uv`** — the command auto-installs `uv` if missing, but if that install can fail in your sandbox (no network, locked-down PATH), confirm `uv --version` first. A missing/failed `uv` surfaces as `E_UV_MISSING`.
4. **Project directory** — run from the project root; it must be `uv`-managed (or greenfield) and writable. A non-`uv` manager is a clean no-op exit (`E_MANAGER_UNSUPPORTED`); a read-only dir is `E_NOT_WRITABLE`.

### 2. Choose the compute target

Exactly one target flag (they are mutually exclusive → `E_USAGE`). Resolution precedence is `--cluster-id` → `--cluster-name` → `--serverless-version` → `--job-task` → bundle `bundle.cluster_id`.

| Flag | Use when | Notes |
|------|----------|-------|
| `--serverless-version <N>` | Matching a serverless version | e.g. `--serverless-version 5` |
| `--cluster-id <id>` | You know the cluster ID | Runtime read from the Clusters API |
| `--cluster-name <name>` | You know the cluster by name | Resolved to an ID; an unknown or **ambiguous** name → `E_RESOLVE` |
| `--job-task <job-id>.<task-key>` | Matching a job task's compute | Task key is **required**; a bare `<job-id>` lists available task keys (`E_USAGE`) |
| *(none)* | A bundle with `bundle.cluster_id` is present | Falls back to the bundle's cluster; otherwise `E_NO_TARGET` |

**Discover targets** with `databricks clusters list -o json | jq '.[] | {cluster_id, cluster_name, state, spark_version}'`. **When the target is ambiguous or unknown, ask the user** rather than guessing — do not pick a cluster on their behalf.

### 3. Run

```bash
# Preview only — computes the plan, writes nothing (safe first step).
databricks environments setup-local --serverless-version 5 --dry-run --output json

# Full setup — matched Python + databricks-connect, writes .venv + pyproject.toml.
databricks environments setup-local --serverless-version 5 --output json

# Constraints-only — matched Python + dependency pins, NO databricks-connect.
databricks environments setup-local --cluster-name my-cluster --constraints-only --output json
```

Prefer `--dry-run` first when a `pyproject.toml` already exists: the result's `plan.diff` shows exactly what would change, and `plan.wouldBackup` names the backup that a real run would write. The command backs up an existing `pyproject.toml` to `pyproject.toml.bak` (then timestamped `.bak` files) before overwriting; a no-op re-run writes nothing.

### 4. Read the result

Parse stdout as JSON and branch on `ok`:

- **`ok: true`** — report `compute` (target), `resolved.pythonVersion` / `resolved.dbconnectVersion`, and surface any `warnings[]` to the user (they are non-fatal but often need a manual follow-up — e.g. a duplicated `databricks-connect` pin uv cannot resolve). On a real (non-dry-run) success, `venvPath` is the provisioned env (relative to the project root, `.venv`); a `--dry-run` success omits it.
- **`ok: false`** — read `error.code` and `error.failurePhase`, then follow [references/troubleshooting.md](references/troubleshooting.md): fix user-fixable causes, or route genuine post-preflight defects to the right repository.
- **No JSON on stdout** — read **stderr**. This is the pre-pipeline path: most often authentication, but also other pre-pipeline errors (e.g. the CLI can't determine the working or cache directory). Act on what stderr reports rather than assuming auth; it is not a `setup-local` pipeline defect.

### 5. Adopt the `.venv`

For every subsequent Python command in this project, use the provisioned interpreter instead of the system Python:

- **macOS / Linux:** `source .venv/bin/activate`, or invoke `.venv/bin/python` / `uv run <cmd>` directly.
- **Windows:** `.venv\Scripts\activate`, or `.venv\Scripts\python.exe`.

Then run the user's Spark code as documented in [`databricks-execution-compute`](../databricks-execution-compute/SKILL.md) (Databricks Connect mode).

## Failure Routing (summary)

Full mapping in [references/troubleshooting.md](references/troubleshooting.md). In short:

- **User-fixable (fix, do not report):** `E_AUTH` (stderr), `E_USAGE`, `E_NO_TARGET`, `E_RESOLVE`, `E_MANAGER_UNSUPPORTED`, `E_NOT_WRITABLE`, `E_UV_MISSING`, `E_PYTHON_INSTALL`, `E_FETCH` (unreachable/no-cache), `E_CANCELED`; plus the user-caused variants of `E_PROVISION` (network/pip-seed, or a `W_USER_CONSTRAINT_CONFLICT`/`W_DBCONNECT_PIN_DUPLICATED` conflict) and `E_VALIDATE` (standalone-`pyspark` collision).
- **Report a published-constraints/pins defect → [`databricks/environments`](https://github.com/databricks/environments/issues):** `E_ENV_UNSUPPORTED`; `E_FETCH` (malformed-constraints message); `E_PROVISION` (published-pins resolution conflict); `E_VALIDATE` (version mismatch). **Decide these last three from `error.message` / `warnings[]`, not the code alone** — see the reference.
- **Report a CLI defect → [`databricks/cli`](https://github.com/databricks/cli/issues) with an `[environments setup-local]` title prefix:** `E_MERGE`, `E_WRITE` (after ruling out local FS causes), JSON parse/wiring errors, and any uncategorized post-preflight failure.

When reporting, include `error.code`, `error.failurePhase`, `compute.envKey`, and the CLI stderr tail — **never** local paths, usernames, cluster names, or tokens.

## Related Skills

- **[databricks-execution-compute](../databricks-execution-compute/SKILL.md)** — run code on Databricks (Databricks Connect, serverless jobs, interactive clusters); the natural next step after provisioning a matched env.
- **[databricks-core](../databricks-core/SKILL.md)** — CLI install, authentication, data exploration.
- **[databricks-dabs](../databricks-dabs/SKILL.md)** — Asset Bundles; the source of the `bundle.cluster_id` fallback target.
