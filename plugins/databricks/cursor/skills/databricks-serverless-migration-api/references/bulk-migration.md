# Bulk Migration

Apply the [single-job workflow](../SKILL.md#migrate-one-job) to each job. Each migration has its own working copy, settings, review record, and approval decisions.

1. **Agree on the jobs.** Use job IDs to identify the requested set. To find candidates, use `databricks jobs list --expand-tasks -o json` and inspect classic compute references. Check `databricks compute-migrations list -o json` for existing migrations before creating another.
2. **Start small.** Migrate three to five representative jobs end to end, review the results with the user, then continue in batches.
3. **Track each migration.** Keep a local manifest mapping job ID to migration ID, `request_id`, current state, backup folder, and the saved review record. Reuse a job's `request_id` when retrying its create request.
4. **Choose settings per job.** Keep `auto_approve` and `run_validation` false unless the user opts in. Skipping the first review and running a working copy are separate decisions. Before enabling validation, confirm that an extra run is safe for that job; apply the [validation guidance](../SKILL.md#settings-chosen-at-creation).
5. **Review and approve explicitly.** Present the proposed changes for each job. A user can approve one job or an explicitly identified set together. Before approving execution, save each job's reviewed settings and code, confirm the approval covers that job, and use its current `etag`.
6. **Handle outcomes independently.** A failed create or a `NOT_SUPPORTED` migration should not stop the rest of the agreed batch. Record the reason and continue. Follow the single-job cancellation, completion-verification, and recovery guidance for each migration.

Report each job's migration state, verification result, tasks intentionally left on classic, and backup folder. List jobs still awaiting a decision separately from completed or unsuccessful migrations.
