# `setup-local` Troubleshooting & Failure Routing

On `ok: false`, read `error.code` and `error.failurePhase` (see [json-output.md](json-output.md)). Every failure is one of three kinds:

1. **User-fixable** — a local, config, or network problem. Fix it (or tell the user how) and re-run. **Do not** file a bug.
2. **Published-constraints/pins defect** — the environment's published Python/dependency pins are wrong or unresolvable. Report to **`databricks/environments`**.
3. **CLI defect** — the command itself misbehaved (bad merge, bad output, unexpected crash after preflight). Report to **`databricks/cli`** with an `[environments setup-local]` title prefix.

Only kinds 2 and 3 are worth a report, and only *after* preflight — a preflight failure is almost always something the user can fix.

## User-fixable — fix, do not report

| Code | Phase | Cause | Action |
|------|-------|-------|--------|
| `E_AUTH` | *(pre-pipeline, stderr — no JSON)* | Not authenticated to a workspace. | Run `databricks auth login` / set a profile. Auth for this command comes from **profile/env only**, not from a bundle. See `databricks-core`. |
| `E_USAGE` | preflight / resolve | Conflicting target flags, or `--job-task <job-id>` with no task key. | Pass exactly one target flag; add the task key (`<job-id>.<task-key>`) — the message lists available keys. |
| `E_NO_TARGET` | resolve | No target from any flag or bundle. | Pass `--cluster-id` / `--cluster-name` / `--serverless-version` / `--job-task`, or run inside a bundle with `bundle.cluster_id`. |
| `E_RESOLVE` | resolve | Cluster name unknown or **ambiguous**, job/cluster read failed, invalid serverless version. | Disambiguate (use `--cluster-id`), fix the name/version, or check workspace access. Ask the user which cluster if unsure. |
| `E_MANAGER_UNSUPPORTED` | preflight | The project uses a package manager other than `uv`. | Only `uv` is supported. Follow the command's guidance; convert the project to `uv` if appropriate. |
| `E_NOT_WRITABLE` | preflight | Project directory is not writable. | Fix permissions or run from a writable copy of the project. |
| `E_UV_MISSING` | preflight | `uv` not found and auto-install failed. | Install `uv` (e.g. `curl -LsSf https://astral.sh/uv/install.sh \| sh`) or add it to PATH, then re-run. |
| `E_PYTHON_INSTALL` | provision | `uv python install` failed for the required minor. | Usually transient/network or a locked-down sandbox. Retry; check `uv` can reach the Python download source. |
| `E_FETCH` | fetch | Constraint repo unreachable and no usable cache. | Network/proxy issue. Check connectivity to `databricks/environments`; retry once online. Report **only** if the network is fine and it still fails (then it may be a defect — see below). |
| `E_CANCELED` | any | The run was interrupted (SIGINT/SIGTERM). | Not a failure of the command. Re-run if the interrupt was unintended. |

## Report to `databricks/environments`

Published constraints/pins for the resolved compute are wrong, missing, or unresolvable — not something the user can fix locally.

| Code | Phase | Cause |
|------|-------|-------|
| `E_ENV_UNSUPPORTED` | fetch | No published environment key exists for the resolved runtime (e.g. a DBR the constraints repo doesn't cover yet). |
| `E_PROVISION` | provision | `uv sync` failed to resolve — the published pins conflict with each other. |
| `E_VALIDATE` | validate | After provisioning, the venv's Python or `databricks-connect` version doesn't match the target the env claimed. |

**Where:** file an issue at `https://github.com/databricks/environments/issues`.

## Report to `databricks/cli`

The command itself failed in a way that isn't the user's fault and isn't a published-pins issue.

| Code / symptom | Phase | Cause |
|----------------|-------|-------|
| `E_MERGE` | merge | Merging the managed regions into the existing `pyproject.toml` failed. |
| `E_WRITE` | merge | Writing a fresh (greenfield) `pyproject.toml` failed. |
| JSON parse / wiring error | — | Output wasn't valid JSON, or fields were missing/misshaped against `schemaVersion: 1`. |
| Any uncategorized failure after preflight | any | An unexpected error not covered above. |

**Where:** file an issue at `https://github.com/databricks/cli/issues` with an **`[environments setup-local]`** title prefix.

## What to include in a report (and what not to)

Include, from the JSON result:

- `error.code` and `error.failurePhase`
- `compute.envKey` (and `mode`, `schemaVersion`)
- the CLI **stderr tail** (re-run with `--debug` for a fuller trace)

**Never** include personally-identifying or environment-specific data in a pre-filled report body: no local file paths, usernames, workspace hosts, cluster names, or tokens. Redact the stderr tail if it contains any of these.
