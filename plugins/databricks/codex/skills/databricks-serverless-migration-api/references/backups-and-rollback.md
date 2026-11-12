# Backups and Rollback

Restoring a job overwrites its current definition and files. Obtain the user's approval for the restore. Pause its schedule, continuous mode, and file-arrival trigger wherever present, and keep them paused throughout restoration and verification.

Check for active runs of the original job and any working-copy job with `databricks jobs list-runs --job-id <job_id> --active-only -o json`. Pausing triggers does not stop active runs. Wait for them to finish or obtain approval to cancel them before replacing code. If a migration was cancelled during execution, follow the [cancellation guidance](../SKILL.md#cancellation) before restoring or deleting resources.

## Find the Backup

```bash
databricks workspace list /Workspace/Users/<user>/serverless-migration/backups/job-<job_id>/
```

Each subfolder is one backup, named by timestamp. A migration writes a new one each time it builds a working copy. Use the recorded pre-migration backup for this migration. If its path was not recorded, inspect the candidate `job.yaml` and `mapping.yaml` files to confirm the correct snapshot before restoring; do not select a backup by sorting folder names.

```
/Workspace/Users/<user>/serverless-migration/backups/job-<job_id>/<timestamp>/
├── job.yaml        # the job definition as it was before the migration
├── mapping.yaml    # backup file name → original workspace path
└── <token>-<name>  # a copy of each workspace notebook or file the job's tasks run
```

`mapping.yaml` has this shape:

```yaml
asset_type: job
asset_id: "<job_id>"
files:
  - backup: <token>-<name>
    original_path: /Workspace/Users/someone@company.com/etl/<name>
```

## Restore the Job Settings

1. Export the backed-up definition: `databricks workspace export <backup_folder>/job.yaml --format AUTO --file job.yaml`.
2. `job.yaml` holds the job as the Jobs API returned it. Its `settings` key is the full pre-migration job settings. Convert `settings` to JSON and preserve an unchanged copy for the final step.
3. In the settings used for restoration, set `schedule.pause_status`, `continuous.pause_status`, and `trigger.pause_status` to `PAUSED` wherever those objects exist. Keep the current job's triggers paused too. Resetting from the backup must not resume the job before its files are restored.
4. Replace the job's settings using that paused copy:

```bash
databricks jobs reset --json '{"job_id": <job_id>, "new_settings": <paused settings as JSON>}'
```

## Restore Notebooks and Files

For each entry in `mapping.yaml`, copy `<backup_folder>/<backup>` back over `original_path`:

1. `databricks workspace get-status <backup_folder>/<backup> -o json` gives `object_type` and, for notebooks, `language`.
2. Notebook:

   ```bash
   databricks workspace export <backup_folder>/<backup> --format SOURCE --file restore.src
   databricks workspace import <original_path> --file restore.src --format SOURCE --language <language> --overwrite
   ```

3. Workspace file:

   ```bash
   databricks workspace export <backup_folder>/<backup> --format AUTO --file restore.src
   databricks workspace import <original_path> --file restore.src --format AUTO --overwrite
   ```

Code that tasks load from a Git repository is not in the backup. Revert it in the repository.

## Verify

`databricks jobs get <job_id> -o json` should match `job.yaml`'s `settings` except for the temporary paused trigger states. Each restored path should match its backup (`databricks workspace export` both and diff).

After verification passes, restore the original trigger states by resetting the job with the unchanged backed-up settings. Verify the final job settings. If restoration or verification fails, leave the triggers paused and report what remains incomplete.

## Clean Up Leftovers

A migration can leave its working-copy job or copied files behind, including after `MIGRATION_COMPLETE`:

- **Working-copy job**: named `[Serverless Migration - <timestamp>] <job name>` and tagged `serverless_migration_source_job_id=<original job id>`. Its ID is in `migration_report.primary_asset` when the migration recorded one. Remove it with `databricks jobs delete <working_copy_job_id>`.
- **Copied notebooks and files**: under `/Workspace/Users/<user>/serverless-migration/scratchpad/`. The working-copy job's task paths point at them. Remove a copy folder with `databricks workspace delete <folder> --recursive`.

Delete leftovers only with the user's approval, after confirming that the job you are deleting is a working copy and not the original. Never delete the backups folder unless the user asks.
