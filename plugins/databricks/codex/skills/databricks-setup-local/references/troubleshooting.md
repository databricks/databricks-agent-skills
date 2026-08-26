# `setup-local` Troubleshooting & Failure Routing

On `ok: false`, read `error.code` and `error.failurePhase` (see [json-output.md](json-output.md)). Every failure is one of three kinds:

1. **User-fixable** — a local, config, or network problem. Fix it (or tell the user how) and re-run. **Do not** file a bug.
2. **Published-constraints/pins defect** — the environment's published Python/dependency pins are wrong or unresolvable. Report to **`databricks/environments`**.
3. **CLI defect** — the command itself misbehaved (bad merge, bad output, unexpected crash after preflight). Report to **`databricks/cli`** with an `[environments setup-local]` title prefix.

Only kinds 2 and 3 are worth a report, and only *after* preflight — a preflight failure is almost always something the user can fix.

**Several post-preflight codes are not 1:1 with a kind.** `E_PROVISION`, `E_VALIDATE`, `E_MERGE`, and `E_WRITE` each cover both a reportable defect *and* a user-fixable / local cause. For these, decide from `error.message`, not the code alone — the specifics are called out per code below.

## User-fixable — fix, do not report

| Code | Phase | Cause | Action |
|------|-------|-------|--------|
| `E_AUTH` | *(pre-pipeline, stderr — no JSON)* | Not authenticated to a workspace. | Run `databricks auth login` / set a profile. Auth for this command comes from **profile/env only**, not from a bundle. See `databricks-core`. |
| `E_USAGE` | preflight / resolve | Conflicting target flags, or `--job-task <job-id>` with no task key. | Pass exactly one target flag; add the task key (`<job-id>.<task-key>`) — the message lists available keys. |
| `E_NO_TARGET` | resolve | No target from any flag or bundle. | Pass `--cluster-id` / `--cluster-name` / `--serverless-version` / `--job-task`, or run inside a bundle with `bundle.cluster_id`. |
| `E_RESOLVE` | resolve | Cluster name unknown or **ambiguous**, job/cluster read failed, invalid serverless version. | Disambiguate (use `--cluster-id`), fix the name/version, or check workspace access. Ask the user which cluster if unsure. |
| `E_MANAGER_UNSUPPORTED` | preflight | The project uses a package manager other than `uv`. | Only `uv` is supported. Follow the command's guidance; convert the project to `uv` if appropriate. |
| `E_NOT_WRITABLE` | preflight | Project directory is not writable. | Fix permissions or run from a writable copy of the project. |
| `E_UV_MISSING` | preflight | `uv` not found — and, in a non-interactive session, not auto-installed (the install needs `DATABRICKS_LOCALENV_AUTO_INSTALL_UV=1` or an interactive yes), or an attempted install failed. | Install `uv` (e.g. `curl -LsSf https://astral.sh/uv/install.sh \| sh`) or add it to PATH; or re-run with `DATABRICKS_LOCALENV_AUTO_INSTALL_UV=1` to let the command install it. |
| `E_PYTHON_INSTALL` | provision | `uv python install` failed for the required minor. | Usually transient/network or a locked-down sandbox. Retry; check `uv` can reach the Python download source. |
| `E_FETCH` | fetch | The message points at a **transport problem** — repo unreachable, no usable cache, an HTTP error (**network/proxy**). | Check connectivity to `databricks/environments`; retry once online. *(If instead the message points at a **malformed published artifact** — can't parse the python version, or invalid/unparsable constraints TOML/schema — that is not a network issue: report to `databricks/environments`, see below.)* |
| `E_CANCELED` | any | The run was interrupted (SIGINT/SIGTERM). | Not a failure of the command. Re-run if the interrupt was unintended. |

## Report to `databricks/environments`

Published constraints/pins for the resolved compute are wrong, missing, or unresolvable — not something the user can fix locally.

**These are heuristics, not proofs.** The CLI folds several causes into each code, and warning detection only flags *provably* recognized conflicts — so the absence of a warning does not by itself prove the fault is in the published pins. Before filing against `databricks/environments`, **reproduce in a clean, isolated project** (an empty directory with no pre-existing `pyproject.toml`, the same target). If it still fails there, the published environment is at fault; if it only fails in the user's project, the cause is local (route per the `databricks/cli` section, or fix locally).

| Code | Phase | Report when… (else it is user-fixable — see above) |
|------|-------|-----------------------------------------------------|
| `E_ENV_UNSUPPORTED` | fetch | Always reportable: no published environment key exists for the resolved runtime (e.g. a DBR the constraints repo doesn't cover yet). |
| `E_FETCH` | fetch | Only when the message points at a **malformed published artifact** — can't parse the python version, or invalid/unparsable constraints TOML/schema. (The transport variant — unreachable repo, no cache, HTTP error — is a network issue, user-fixable, see above.) |
| `E_PROVISION` | provision | The message shows `uv sync` **failing to resolve** (a dependency conflict / "no solution found") **and** `warnings[]` shows no user-caused conflict. *Not* reportable when: `warnings[]` contains `W_USER_CONSTRAINT_CONFLICT` or `W_DBCONNECT_PIN_DUPLICATED` (the user's own pins are the conflict — user-fixable); or the message shows a network/download failure or a pip-seeding (post-provision) error (transient/local — retry). |
| `E_VALIDATE` | validate | The message shows the installed **Python or `databricks-connect` version doesn't match** the target the env claimed, **and it reproduces in a clean project** (validate compares the installed `.venv` against already-resolved values, so a mismatch can also stem from provisioning, the merge, or the user's own project — if it does not reproduce clean, route to `databricks/cli` instead). *Not* reportable when the message names a standalone-`pyspark` collision (the user declared `pyspark` alongside `databricks-connect`) — that is user-fixable: remove the standalone `pyspark` (see `W_STANDALONE_PYSPARK_CONFLICT`), keep a local Spark in a separate venv. |

**Where:** file an issue at `https://github.com/databricks/environments/issues`.

## Report to `databricks/cli`

The command failed after preflight in a way that is neither a published-pins issue nor an obvious local problem.

| Code / symptom | Phase | Report when… |
|----------------|-------|--------------|
| `E_MERGE` | merge | Merging the managed regions into the existing `pyproject.toml` failed. **First rule out local causes** — permissions changed mid-run, disk full, a filesystem race, or a failed backup can all surface here. Report only when the filesystem is healthy; then it points to a merge-logic bug. |
| `E_WRITE` | merge | Writing a fresh (greenfield) `pyproject.toml` failed. Apply the same local-cause check as `E_MERGE` (permissions, disk, race) before reporting. |
| JSON parse / wiring error | — | Output wasn't valid JSON, or fields were missing/misshaped against `schemaVersion: 1`. Always reportable. |
| Any uncategorized failure after preflight | any | An unexpected error not covered above, with no plausible local cause. |

**Where:** file an issue at `https://github.com/databricks/cli/issues` with an **`[environments setup-local]`** title prefix.

## What to include in a report (and what not to)

Include, from the JSON result:

- `error.code` and `error.failurePhase`
- `compute.envKey` (and `mode`, `schemaVersion`)
- the CLI **stderr tail** (re-run with `--debug` for a fuller trace)

**Never** include personally-identifying or environment-specific data in a pre-filled report body: no local file paths, usernames, workspace hosts, cluster names, or tokens. Redact the stderr tail if it contains any of these.
