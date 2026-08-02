# Testing Strategy — Two-Branch Migration

How to test a migrated workload before it ships. Read this before running the first test on a migrated notebook or job.

### Step 3: Test — Two-Branch Strategy

Use separate branches for testing and production to keep test-only workarounds out of the code that ships. The test branch is a safe sandbox for experimentation; the production branch contains only changes that production actually needs.

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

**Test branch** (`serverless-test-{job_name}-{timestamp}`): Temporary, no PR needed.
1. Create a branch from your current working branch
2. Set up test data: create sampled copies of upstream tables in a test catalog using job lineage (see test data setup below)
3. Parameterize the catalog so the notebook works with both test and production data (see catalog parameterization pattern below)
4. Apply all compatibility fixes discovered in Step 2
5. Create a serverless test job and run it
6. If it fails, get the error output, debug, fix, and retry
7. Document which changes are **test workarounds** vs. **real compatibility fixes**

**Production branch** (`serverless-prod-{job_name}`): PR required, created from master.
1. Create a new branch from master (NOT from the test branch)
2. Apply ONLY the real compatibility fixes — no test workarounds
3. Apply job config changes (see job config transformation below)
4. Commit and create a PR

### Test Data Setup

When the job reads from production tables, do not point the test job at production data. Instead, create sampled copies of upstream tables in a dedicated test catalog and run the test job against those.

The recommended pattern:
1. Resolve the job's upstream tables from its lineage (or from a static scan of the notebook)
2. For each upstream table, run `CREATE TABLE IF NOT EXISTS <test_catalog>.<schema>.<table> AS SELECT * FROM <prod_catalog>.<schema>.<table> LIMIT N` (typical N: 10–1000 rows)
3. Keep the schema names identical to production — only the catalog changes
4. Make the operation idempotent: skip tables that already exist, so the setup step is safe to re-run
5. Require a running SQL warehouse and `CREATE TABLE` permission on the test catalog

With schema names preserved, the same notebook code runs in both environments — only the `catalog` widget value changes.

### Decision Tree: Should This Change Go to Production?

| Change type | Production? | Reason |
|-------------|-------------|--------|
| Remove incompatible Spark configs | **Yes** | Serverless compatibility fix |
| Update library versions | **Yes** | Serverless compatibility fix |
| Replace DBFS paths with UC Volumes | **Yes** | Serverless compatibility fix |
| Remove init scripts, add Environments | **Yes** | Serverless compatibility fix |
| Fix hardcoded cluster settings | **Yes** | Serverless compatibility fix |
| Catalog override to test catalog | **No** | Test workaround only |
| Empty DataFrame handling for missing test data | **No** | Test workaround only |
| Date range limiting for faster tests | **No** | Test workaround only |

**Simple test**: Would production fail without this change on serverless? If yes → include. If no → test branch only.

### A/B Comparison

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
