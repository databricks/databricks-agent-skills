---
name: databricks-setup-local
description: "Previews, provisions, or diagnoses a uv-managed local Python .venv with `databricks environments setup-local`. Use when the user wants to set up or fix one for Databricks Connect, cluster or serverless compute, `--job-task`, or a bundle target, or when setup-local fails."
compatibility: Requires databricks CLI (>= v1.12.0) and uv
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Setup-Local

**REQUIRED FIRST:** Use `databricks-core` for CLI, authentication, and profile selection. Never use a default profile. For an existing environment, use `databricks-execution-compute`.

## Workflow

### 1. Check CLI and authentication

```bash
databricks version                         # must be >= v1.12.0
databricks auth describe --profile <PROFILE>
```

Prefer the latest stable CLI; no online lookup is required. Compare the full semantic version: v0.299.1 is older than v1.12.0. If missing or older, or `setup-local` is absent from help, reports `unknown command`, or rejects a documented flag, stop. Use `databricks-core` to upgrade with approval and verify; never recreate `setup-local` manually.

Use the selected profile for every workspace command. Do not convert another package manager without approval.

### 2. Confirm the project directory

Confirm the root containing (or intended to contain) `pyproject.toml`, `.venv`, and `uv.lock`; ask if multiple roots are plausible. Use it for preview and apply. It must be greenfield or `uv`-managed, but need not be writable for preview.

### 3. Select one target

Choose exactly one branch:

- **Cluster:** use `--cluster-id <ID>` or `--cluster-name <NAME>`. If unknown, list clusters with the selected profile and ask; see [examples](references/examples.md).
- **Serverless:** use `--serverless-version <N>`. No version-list command exists; ask if unspecified.
- **Job task:** use `--job-task <JOB_ID>.<TASK_KEY>`. If the task is unknown, run `databricks jobs get <JOB_ID> --profile <PROFILE> --output json`, present task keys, and ask.
- **Bundle:** a project with `databricks.yml`. Use `databricks-dabs` to inspect its root and selected target. Omit compute flags only when that target resolves supported classic or serverless compute; otherwise ask. Add `--target <BUNDLE_TARGET>` for a named target.

Never combine compute flags. If no branch resolves, ask the user.

### 4. Preview

Dry-run first; it writes and installs nothing:

```bash
databricks environments setup-local --profile <PROFILE> <TARGET_ARGS> --dry-run --output json
```

For bundles, `<TARGET_ARGS>` is empty or `--target <BUNDLE_TARGET>`. Default to normal mode. Use `--constraints-only` only when the user explicitly does not want this command managing `databricks-connect`. See [JSON output](references/json-output.md) and [examples](references/examples.md).

### 5. Obtain approval and apply

Before apply, verify the directory is writable and run `uv --version`. Ask before installing `uv`; never silently set `DATABRICKS_LOCALENV_AUTO_INSTALL_UV=1` or run a remote installer.

Show the target, versions, warnings, `plan.diff`, and directory. Explain that apply may:

- back up and rewrite `pyproject.toml`;
- install Python and dependencies;
- update `.venv` and `uv.lock`.

For `--serverless-version N` in a bundle, also disclose the post-apply job YAML synchronization described below so approval covers both mutations.

Apply only after the user requested provisioning or approves that plan for the named directory. Preserve the directory, profile, target, and mode.

If the directory, profile, target, mode, or project files change after preview, rerun `--dry-run`, show the new plan, and obtain approval again. Treat its resolved Python, `databricks-connect`, and managed constraints as authoritative; do not substitute guessed versions. Reconcile user-owned dependency conflicts separately, with approval.

### 6. Handle the result

- `ok: true`: for `--serverless-version N` in a bundle, update every existing job `environments[].spec.environment_version` in its YAML sources to `"N"`, then validate the bundle. Report if none exist; do not invent one. Skip this for cluster and job-task targets. Report target, versions, warnings, and `venvPath`; prefer `uv run <cmd>` or derive the platform-specific interpreter from `venvPath`.
- `ok: false`: use [troubleshooting](references/troubleshooting.md). Ask before diagnostic runs that mutate files and before filing an external issue.
- No JSON: inspect stderr for a pre-pipeline CLI, authentication, directory, or cache error.
