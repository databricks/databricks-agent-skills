# Common Issues

Symptom-to-fix table for pipeline failures. Read this when a pipeline errors
and the message is not self-explanatory.

## Common Issues

Error → cause/fix mappings agents hit constantly. For DAB-bundle vs CLI-iteration deploy issues, see the workflow-specific reference files.

| Error / symptom | Cause / fix |
|-----------------|-------------|
| Rejection of `CREATE OR REPLACE STREAMING TABLE` / `MATERIALIZED VIEW` | `CREATE OR REPLACE` is standard SQL, NOT SDP. Use `CREATE OR REFRESH STREAMING TABLE` / `CREATE OR REFRESH MATERIALIZED VIEW`. |
| CLI errors on `databricks fs ls /Volumes/...` | The `dbfs:` prefix is required even for UC Volume paths: `databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>`. |
| `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` at first write | A `CLUSTER BY` column is BOOLEAN / ARRAY / MAP / STRUCT / BINARY. SDP doesn't pre-validate — verify with `DESCRIBE` before submitting. Cluster keys must be numeric / string / date / timestamp. Full type rules in performance#cluster-key-data-types. |
| `Cannot create streaming table from batch query` | In a streaming-table query you wrote `FROM read_files(...)` (batch). Use `FROM STREAM read_files(...)` so Auto Loader kicks in. |
| `Column not found` at ingest time | `schemaHints` don't match the actual file schema. `DESCRIBE` a sample file and align the hints. |
| Streaming reads fail with parser error | Use `FROM STREAM read_files(...)` for file ingestion and `FROM stream(table)` (or `FROM STREAM table_name` — legacy DLT, prefer function form) for table-to-table streams. Don't mix. |
| Pipeline stuck `INITIALIZING` for serverless | Normal — first run takes a few minutes for cold start. Don't kill it. |
| Materialized View doesn't incrementally refresh | Automatic incremental refresh for aggregations requires **serverless** + Delta row tracking on the source (`delta.enableRowTracking = true`). Without both, falls back to full recompute. Mention the serverless requirement when the user asks about incremental refresh. |
| SCD2 query returns nothing / "column not found" on `START_AT` | Lakeflow uses `__START_AT` / `__END_AT` (double underscore). Current rows: `WHERE __END_AT IS NULL`. |
| `error.exceptions[0].message` missing from your events output | Your `jq` is reading `.message` (which is just "Update X is FAILED"). Read `error.exceptions[0].message` for the real cause — see 2-rapid-iteration-with-cli#step-4-start-an-update-and-poll-that-update. |
