---
name: databricks-serverless-migration-api
description: "Migrate Databricks jobs to serverless through the Compute Migrations API and CLI, then track, review, and approve each migration. Use for automated job migrations managed by this service, scripts that start and track migrations, requests to inspect, revise, approve, or cancel migrations, and finding migration backups. For direct code or notebook edits and compatibility analysis, use databricks-serverless-migration."
compatibility: Requires databricks CLI (>= v1.24.0) with the compute-migrations command group
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Serverless Migration API

**FIRST**: Use the parent `databricks-core` skill for CLI installation, authentication, and profile selection.

Use the Compute Migrations API through the Databricks CLI to migrate a job to serverless. The service analyzes the job, backs it up, builds a serverless working copy, and optionally runs it in the background. Your part is to track the migration, review the working copy, present the changes to the user, and carry out their decision. Applying the changes to the original job requires the user's explicit approval.

## When to Use This Skill

Use it when the user asks you to:

- migrate one job or many jobs to serverless,
- write a script that starts and tracks migrations,
- check on, approve, reject, or cancel migrations already in progress, or
- find the backup a migration took of a job.

Use `databricks-serverless-migration` for direct code edits, notebooks, pipelines, JAR tasks, or a job this service cannot migrate. For job definitions maintained in source control, read [Jobs managed from source](#jobs-managed-from-source).

See the [migration guide](https://docs.databricks.com/en/compute/serverless/migration#migrate-with-the-migration-agent) for supported workloads and limits. A successful `create` starts the migration; it does not establish that the workload is compatible. Incompatibilities can be discovered during planning or working-copy creation.

## Migrate One Job

1. Check the [prerequisites](#prerequisites) once per workspace.
2. Confirm the job and whether to set `auto_approve` or `run_validation` (see [Settings chosen at creation](#settings-chosen-at-creation)).
3. Start the migration with `create`, and record its migration ID and `request_id`.
4. [Track progress](#tracking-progress) until it reaches a review gate or a terminal state.
5. At each review gate, [review the working copy](#reviewing-a-working-copy), present your findings to the user, and approve or reject as the user decides.
6. After `MIGRATION_COMPLETE`, [verify the original job](#after-completion) and report the result and the backup folder.

For a list of jobs, use [Bulk migration](references/bulk-migration.md) to repeat this workflow and track each job's decisions.

## Prerequisites

1. **CLI v1.24.0 or newer**: check `databricks --version` and `databricks compute-migrations --help`. The command group and the verbs below must be available. If a command is missing, upgrade using `databricks-core`.
2. **Compute Agent preview** enabled in the workspace. A workspace admin enables it under **Previews**. Without it, every call fails with `PERMISSION_DENIED` ("Migration APIs are not enabled for this workspace").
3. **CAN_MANAGE** on each job you migrate.

The CLI help is generated from the API and is authoritative for command names, arguments, and flags. Run `databricks compute-migrations <command> --help` before first use of each command. Pass request bodies with `--json` and read responses with `-o json`.

## Lifecycle

```
Prepare working copy
  → TRANSLATION_READY (skipped when auto_approve=true)
  → Optional validation run (run_validation=true)
  → MIGRATION_REVIEW (execution approval required)
  → Apply changes → MIGRATION_COMPLETE
```

1. **Planning.** The service reads the job, its notebooks and files, and its cluster configuration, and works out the serverless changes: compute, dependencies, Spark configs, and code changes. The working copy is the first thing you review.
2. **Backup and working copy.** The service saves a backup of the job and its workspace files (see [Backups](#backups)), then creates a working copy: a new job named `[Serverless Migration - <timestamp>] <job name>`, tagged `serverless_migration_source_job_id=<original job id>`, running copies of the job's notebooks and files. The original job is not modified until you approve execution.
3. **Gate 1, `TRANSLATION_READY`.** Skipped when `auto_approve=true`. Otherwise, review the working copy. Approve to continue, or reject with a reason to request changes.
4. **Validation run** (only with `run_validation`). Databricks runs the working-copy job once. The outcome is recorded in `validation_report`. A failed run does not stop the migration: it moves to `MIGRATION_REVIEW` with `passed: false`.
5. **Gate 2, `MIGRATION_REVIEW`.** Final approval to update the original job. Approving execution starts applying the working copy's settings and file contents to the original job, keeping its job ID, schedule, and permissions.
6. **Complete.** Verify the original job (see [After completion](#after-completion)).

Use either rejection command to **request changes**, with a specific `rejection_reason`. The same migration returns to planning and revises its working copy. Read `migration_report` again and review the current copy before approving it. Revisions are limited, and repeated rejections eventually fail the migration. When the user wants to stop the migration, use `cancel-migration` (see [Cancellation](#cancellation)).

## Settings Chosen at Creation

`auto_approve` and `run_validation` are fixed when the migration is created and cannot be changed. Both default to `false`. Set either one only when the user asks for it.

| Field | Effect | Risk |
|-------|--------|------|
| `auto_approve` | Skips gate 1 (`TRANSLATION_READY`). Gate 2 still waits for a decision. | With `run_validation`, the working copy runs before the user reviews it. |
| `run_validation` | Runs the working-copy job once before gate 2. | The run is real: see below. |

**A validation run is not sandboxed.** The working copy runs in the same workspace against the same tables, volumes, checkpoints, and external systems as the original job, with the agent's changes applied. If the job is not idempotent, or has side effects, the validation run produces them. Examples: overwriting or appending to production tables, merges, sending emails or notifications, calling external APIs, triggering downstream jobs, or advancing streaming offsets and checkpoints. Enable `run_validation` only after the user confirms that one extra run of this job, right now, is safe, for example because the job is idempotent or writes only to test outputs. Never turn it on across a batch of jobs without that confirmation for each job.

## Commands

| Operation | Command | Notes |
|-----------|---------|-------|
| Start | `create --json '<migration>' --request-id <uuid>` | `asset_type` is `JOB`; `asset_uri` is `jobs/<job_id>`. |
| Read one | `get <migration_id>` | Current state, reports, `etag`. |
| Read many | `list` | Returns a JSON array with `-o json` and paginates automatically. Filter the returned `state` values locally. Eventually consistent: confirm with `get` before acting. |
| Gate 1 | `approve-migration-translation <migration_id>` / `reject-migration-translation <migration_id> <rejection_reason>` | Reject takes the reason as a positional argument or as `rejection_reason` in `--json`. Approve accepts optional `--additional-feedback`. |
| Gate 2 | `approve-migration-execution <migration_id>` / `reject-migration-execution <migration_id> <rejection_reason>` | Same arguments and flags as gate 1. |
| Stop | `cancel-migration <migration_id>` | Any non-terminal state. Optional `cancellation_reason`. Does not undo applied changes; see [Cancellation](#cancellation). |
| Remove record | `delete <migration_id>` | Hides the record and frees the job for a new migration. Rolls nothing back and cleans nothing up. Use `cancel-migration` to stop an in-flight migration. |

All commands are under `databricks compute-migrations`. Start a migration:

```bash
databricks compute-migrations create -o json --request-id "<uuid>" --json '{
  "asset_type": "JOB",
  "asset_uri": "jobs/<job_id>",
  "auto_approve": false,
  "run_validation": false
}'
```

Generate a fresh `request_id` per job and reuse it when retrying that job's `create` after a timeout or network error. The server returns the existing migration instead of creating a duplicate.

Pass the `etag` from your latest `get` on every approve, reject, and cancel, so the call fails rather than acting on a state you have not seen:

```bash
databricks compute-migrations reject-migration-translation <migration_id> -o json --json '{
  "etag": "<etag>",
  "rejection_reason": "Keep the existing output table names; task ingest writes to a different table in the working copy."
}'
```

| Error | Meaning | Action |
|-------|---------|--------|
| `ALREADY_EXISTS` | The job has a migration in progress, or one that already migrated it. | Find and confirm the existing migration as described below. |
| `INVALID_PARAMETER_VALUE` | Bad request, or the job cannot be migrated. | Read the message; do not retry unchanged. |
| `PERMISSION_DENIED` | No CAN_MANAGE on the job, or the preview is not enabled. | Report to the user. |
| `FAILED_PRECONDITION` | Gate call made in the wrong state. | `get`, then act on the current state. |
| `ABORTED` | The `etag` is stale. | `get`, re-check the state, retry with the new `etag`. |

After `ALREADY_EXISTS`, take the migration ID from the error and confirm its `asset_uri` and state with `get`. If the existing migration is `MIGRATION_COMPLETE`, report the job as already migrated. Do not delete the record and create another migration unless the user explicitly requests it.

## Tracking Progress

Migrations take minutes to hours: planning and building the working copy usually take several minutes, and a validation run takes as long as the job. Use your harness's monitoring capabilities to track progress. `get` returns the current migration state; for many migrations, use `list` and confirm each one with `get` before acting.

| State | What to do |
|-------|------------|
| `PLANNING_PENDING`, `PLANNING_RUNNING`, `REVISION_PENDING` | Planning is in progress. |
| `TRANSLATION_PENDING`, `TRANSLATION_CREATING` | Working-copy creation is in progress. |
| `VALIDATION_SCHEDULING`, `VALIDATION_RUNNING` | Validation is in progress. |
| `MIGRATION_PENDING`, `MIGRATION_RUNNING`, `MIGRATION_OBSERVATION` | Migration is in progress. |
| `TRANSLATION_READY` | Review the working copy, present it to the user, then approve or reject gate 1. |
| `MIGRATION_REVIEW` | Review the working copy and `validation_report`, present them, then approve or reject gate 2. |
| `MIGRATION_COMPLETE` | Verify the original job. |
| `NOT_SUPPORTED` | The job cannot be migrated automatically. Report the reason from `state_history`, and offer `databricks-serverless-migration` for a manual migration. |
| `FAILED` | Report the reason from `state_history`. If the migration failed during `MIGRATION_RUNNING`, check whether the original job was partly changed (see [Backups](#backups)). |
| `CANCELLED` | Report the cancellation and check for applied changes or active validation runs as described in [Cancellation](#cancellation). |
| Any other state | Read the migration again with `get`. If the state is still unrecognized, report it and stop automatic progress handling; do not assume it is in progress. |

`state_history` lists every state entered, with `transition_time`, the reviewer's `user_comment`, and the system's `internal_comment` (for example, the reason for a failure).

## Cancellation

Cancellation does not undo changes already applied to the original job or files, or side effects of validation runs. An operation already in progress may finish after the migration reports `CANCELLED`; that state alone does not confirm that all work has stopped.

If execution was approved, or `state_history` includes `MIGRATION_PENDING` or `MIGRATION_RUNNING`, inspect the original job and files against the saved review record and backup. Report which changes are present and anything you cannot verify. Check active working-copy runs separately with `databricks jobs list-runs --job-id <working_copy_job_id> --active-only -o json`. Retain the recovery artifacts if the result is unverified or work may still be active.

## Reviewing a Working Copy

The API returns links to the working copy, not a diff, so build the comparison yourself:

1. `get` the migration. `migration_report.primary_asset.id` is the working-copy job's ID.
2. Compare job settings: `databricks jobs get <original_job_id> -o json` against `databricks jobs get <working_copy_job_id> -o json`. Expect classic compute (`job_clusters`, `new_cluster`, `existing_cluster_id`) to be replaced by serverless settings (`environments` and `environment_key`), libraries to move into environment dependencies, unsupported Spark configs and init scripts to be removed, and possibly a performance mode to be set. The job name prefix, the `serverless_migration_source_job_id` tag, and task paths pointing at the copied notebooks are expected differences.
3. Compare code. The working-copy job's task settings name the notebooks and files it runs. Match its tasks to the original job's by `task_key`, and take each task's path (`notebook_task.notebook_path` or `spark_python_task.python_file`) from both jobs. For `for_each_task`, inspect its inner `task` too. Export each to a separate local file with `databricks workspace export <path> --format SOURCE --file <local_file>` and diff them. Also inspect utility notebooks invoked by the task notebooks for changes, such as through `%run` or `dbutils.notebook.run`.
4. If a validation run happened, report `validation_report.passed`, `run_status`, and `run_url`. For a failed run, inspect it with `databricks jobs get-run <run_id> -o json`. Take the run ID from `run_url`.
5. Summarize the changes per task, including which tasks will migrate and which will stay on classic. Flag anything beyond a compatibility fix: changed business logic, different output tables or paths, removed steps, or dropped dependencies.
6. Before approving execution, save the reviewed job settings and exported code, including utility notebooks, in a local folder for this migration ID. Include the original task paths, the working-copy-to-original path mapping, and the tasks approved for migration or intentionally kept on classic. This review record is needed after the working copy is deleted. Refresh it after any revision and review.
7. Get the user's decision. A rejection reason should name the task and the specific change to make.

Rules while a migration is in progress:

- Approve gate 2 only with explicit user approval covering that job ID. A single decision may approve an explicitly identified set of jobs; the approval must cover the reviewed changes for each job.
- Do not edit the original job. Approving execution replaces its settings and files with the working copy's, discarding later edits.
- Do not edit the working copy to change the outcome. Reject with a reason instead.

## After Completion

When the API reports `MIGRATION_COMPLETE`, verify the original job before reporting success:

- Read `databricks jobs get <job_id> -o json` and compare it with the saved review record. Tasks approved for migration must have the reviewed serverless settings; tasks intentionally left on classic must retain their reviewed configuration. Account for the original job name and task paths, and removal of the working-copy tag.
- Export the original task notebooks and files, including those used by nested tasks, along with the reviewed utility notebooks. Compare them with the saved reviewed code.

If approved changes are missing or differ from the review record, report the mismatch and offer to restore from the backup. Before retrying, restore any job settings or files changed by this migration from the pre-migration backup, with the user's approval. Then `delete` the migration (which frees the job) and create a new one. If the review record is unavailable, explain which parts of the result you could verify and which remain unverified.

The working-copy job or its copied files may remain after a successful migration. Report any leftovers and offer [cleanup](references/backups-and-rollback.md#clean-up-leftovers).

Report the migration ID, final state, original job, what changed, tasks left on classic, and the backup folder.

## Backups

Before building the working copy, the service writes a backup to the workspace home of the identity that created the migration.

Files that tasks load from a Git repository are not copied; they stay in the repository. A new timestamped backup folder is written each time the service builds a working copy. Migrations never delete backups. Give the user the backup folder for every migration that reached `TRANSLATION_READY` or later.

There is no rollback command. For the backup location and file layout, restore instructions, and working-copy cleanup, follow [Backups and rollback](references/backups-and-rollback.md).

## Bulk Migration

For multiple jobs, follow [Bulk migration](references/bulk-migration.md). It applies the single-job workflow to each migration, with separate tracking, settings, review records, and approval decisions.

## Jobs Managed from Source

A migration changes the job in the workspace. If the job's definition comes from source, the next deploy reverts the migration. This covers jobs deployed from a Declarative Automation Bundle (`settings.deployment.kind` is `BUNDLE`) and jobs managed by Terraform or CI. For these jobs, tell the user before creating a migration. Either migrate the source (`databricks-serverless-migration`, `databricks-dabs`), or use the reviewed working copy as the reference for changes to make in the source.

## Documentation

- Serverless migration guide, including the migration agent: https://docs.databricks.com/en/compute/serverless/migration
- Serverless compute limitations: https://docs.databricks.com/en/compute/serverless/limitations
- Serverless jobs: https://docs.databricks.com/en/jobs/run-serverless-jobs
