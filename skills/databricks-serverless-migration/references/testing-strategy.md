# Testing Strategy

Detail for Step 3 (Test) and the deliverables in [SKILL.md](../SKILL.md#step-3-test--two-branch-strategy).

## Two-branch comparison

| Aspect               | Test branch                                    | Production branch                  |
|----------------------|------------------------------------------------|------------------------------------|
| Name pattern         | `serverless-test-{job_name}-{timestamp}`        | `serverless-prod-{job_name}`       |
| Base branch          | Any working branch                              | Must be master                     |
| Purpose              | Verify serverless compatibility                 | Deploy to production               |
| Test-only workarounds | Yes (catalog overrides, sampled data, date limits) | **No**                         |
| Compatibility fixes  | Yes (discover them here)                        | Yes (apply the validated ones)     |
| Job config changes   | Yes (for the test job)                          | Yes (for the prod job)             |
| Catalog              | Test catalog                                    | Production catalog                 |
| PR required          | No                                              | Yes                                |
| Merged to master     | No                                              | Yes                                |

## Test Data Setup

When the job reads from production tables, do not point the test job at production data. Instead, create sampled copies of upstream tables in a dedicated test catalog and run the test job against those.

The recommended pattern:
1. Resolve the job's upstream tables from its lineage (or from a static scan of the notebook)
2. For each upstream table, run `CREATE TABLE IF NOT EXISTS <test_catalog>.<schema>.<table> AS SELECT * FROM <prod_catalog>.<schema>.<table> LIMIT N` (typical N: 10–1000 rows)
3. Keep the schema names identical to production — only the catalog changes
4. Make the operation idempotent: skip tables that already exist, so the setup step is safe to re-run
5. Require a running SQL warehouse and `CREATE TABLE` permission on the test catalog

With schema names preserved, the same notebook code runs in both environments — only the `catalog` widget value changes.

## A/B Comparison

After both branches are ready, compare outputs:

```python
# Compare outputs between classic and serverless runs
classic_df = spark.read.table("main.output.classic_results")
serverless_df = spark.read.table("main.output.serverless_results")

assert classic_df.count() == serverless_df.count(), "Row count mismatch"
assert classic_df.schema == serverless_df.schema, "Schema mismatch"
diff = classic_df.exceptAll(serverless_df)
assert diff.count() == 0, f"Found {diff.count()} differing rows"
```

**Temporary bridge configs**: If the serverless run fails, you may temporarily set supported Spark configs (like `spark.sql.shuffle.partitions`) to bridge gaps. Mark these as temporary — remove once the workload stabilizes.

## Migration Deliverables

At the end of a successful migration run, surface these artifacts so the user can verify the work and inspect the results:

| Deliverable | What it is | Why it matters |
|-------------|------------|----------------|
| Test branch name/URL | The `serverless-test-{job_name}-{timestamp}` branch with all compatibility fixes and test workarounds | Lets the user see what changed during experimentation, including test-only adjustments |
| Production branch name/URL | The `serverless-prod-{job_name}` branch containing only the validated compatibility fixes | This is what ships — the user reviews and merges the PR from here |
| Test job ID and run URL | The serverless test job that validated the migration | Proves the notebook runs successfully on serverless against sampled data |
| Classic vs serverless comparison | A/B result summary (row counts, schema check, row-level diff) | Confidence that serverless output matches classic output |
| Serverless environment spec | The `environments` JSON block (client version + pinned dependencies) | Ready to paste into the production job config |
| Change summary | List of what went to production vs test-only (with reasons) | Audit trail for the PR reviewer |

If any deliverable is missing, the migration is incomplete — do not mark it as done.
