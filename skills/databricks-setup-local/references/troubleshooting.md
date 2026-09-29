# `setup-local` troubleshooting

Start with `error.code` and `error.failurePhase`. For overloaded codes, use the observable condition below rather than assuming ownership.

## Fix locally

| Code | Action |
|---|---|
| Pre-pipeline auth error | Re-authenticate the user-selected profile; bundle workspace settings do not configure this command. |
| `E_USAGE` | Supply at most one target flag and include a task key with `--job-task`. |
| `E_NO_TARGET` | Ask for a target or use a bundle with `bundle.cluster_id`. |
| `E_RESOLVE` | Correct or disambiguate the target; check access with the selected profile. |
| `E_MANAGER_UNSUPPORTED` | Explain that only `uv` is supported. Ask before converting the project. |
| `E_NOT_WRITABLE` | Use a writable project copy or fix permissions. |
| `E_UV_MISSING` | Ask before installing `uv`; use an approved, trusted installation method. |
| `E_PYTHON_INSTALL` | Check whether `uv` can reach its configured Python source; retry transient failures. |
| `E_FETCH` with transport/cache error | Restore access to `databricks/environments` and retry. |
| `E_CANCELED` | Re-run only if the interruption was unintended. |
| `E_PROVISION` with network/pip-seed failure | Fix connectivity or retry. |
| `E_PROVISION_CONFLICT` with `W_USER_CONSTRAINT_CONFLICT` (`failurePhase: provision`), or `E_PROVISION`/`E_PROVISION_CONFLICT` with `W_DBCONNECT_PIN_DUPLICATED` | Reconcile the user's pins. The merge-detected conflict fails only on apply -- `--dry-run` returns `ok: true` and reports it in `warnings[]`, so read the warnings before applying. On CLI >= v1.17.0, an `E_PROVISION_CONFLICT` carrying no conflict warning at all is a transitive resolver conflict the merge cannot see: route it below, do not blame the user's pins. This failure has already rewritten `pyproject.toml` (`diskMutated: true`) and left a backup, so recover from `backupPath` rather than assuming the file is untouched. |
| `E_VALIDATE` naming standalone `pyspark` | Remove it from the Connect environment; use a separate environment for standalone Spark. |

## Determine defect ownership

Some failures require reproduction in an empty temporary project with the same profile and target. A real reproduction provisions files and dependencies, so explain this and obtain approval first.

| Condition after approved clean reproduction | Owner |
|---|---|
| `E_ENV_UNSUPPORTED` for a target expected to be supported | `databricks/environments` |
| `E_FETCH` identifies malformed published Python or constraints data | `databricks/environments` |
| `E_PROVISION` or `E_PROVISION_CONFLICT` cannot resolve published pins and no conflict warning exists (the warning-free `E_PROVISION_CONFLICT` needs CLI >= v1.17.0). Decide this from `error.message`, never the code alone -- the same code also covers a typo'd or nonexistent package and a `requires-python` mismatch, which are the user's to fix. Read uv's verbatim stderr and reproduce in a clean project first. | `databricks/environments` |
| `E_VALIDATE` reports a Python or Databricks Connect version mismatch | `databricks/environments` |
| Invalid/misshapen schema-version-1 JSON | `databricks/cli` |
| `E_MERGE` or `E_WRITE` after ruling out permissions, disk space, and filesystem races | `databricks/cli` |
| Other reproducible post-preflight command failure with no local cause | `databricks/cli` |

If the failure occurs only in the user's project, treat it as local unless the evidence identifies a CLI merge/write defect.

## Prepare a report

Prepare a draft containing:

- `error.code`, `error.failurePhase`, `compute.envKey`, `mode`, and `schemaVersion`;
- a redacted stderr tail, using `--debug` if more detail is needed;
- clean-reproduction steps and outcome.

Exclude tokens, workspace hosts, cluster names, usernames, and local paths. Show the draft to the user and obtain explicit approval before filing externally:

- Published environment defect: `https://github.com/databricks/environments/issues`
- CLI defect: `https://github.com/databricks/cli/issues`, with an `[environments setup-local]` title prefix
