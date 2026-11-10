# Modes: integrated CDC, standard CDC, query-based

What each mode does that its docs pages don't make obvious, with one bundle example each. Pages and marking fields: [SKILL.md](../SKILL.md#modes-per-source). Source specifics: [sources.md](sources.md).

## Integrated CDC

One pipeline reads the change log inside each update; no gateway. The workspace's error wins: if it rejects `connector_type: CDC`, integrated CDC isn't enabled there; offer standard CDC where the source has it.

Bundle: copy the example on the source's integrated pipeline page (`<source>-integrated-pipeline`), with the names per source from [sources.md](sources.md#where-names-go). If you set `data_staging_options`, create its schema first: the pipeline creates a volume there.

- **Staging:** without `data_staging_options` the volume lands in the destination schema as `__databricks_ingestion_gateway_staging_data-<pipeline-id>`.
- **Smart closure** ([page](https://docs.databricks.com/ingestion/lakeflow-connect/smart-closure)): read the page for how an update's runtime is bounded and whether those bounds can be set; don't quote durations from memory. A long update with nothing to apply can be normal: read its events before treating it as stuck. Don't block: start with `--no-wait` and poll `get-update`.
- **Schema change:** the running update ends `CANCELED` (`CDC_APPLIER_SCHEMA_CHANGED_DURING_STREAMING`) and the pipeline starts one with cause `SCHEMA_CHANGE`: not a failure. After a failure it often starts `RETRY_ON_FAILURE`; while either runs, `start-update` is refused ("An active update ... already exists"): `list-updates --max-results 3` and wait. With `PIPELINE_NON_RETRYABLE_ANALYSIS_CLIENT_ERROR` no retry follows: one table stopped the update; fix or full refresh that table, then start the next update.
- **Full refresh:** "After the snapshot completes, Databricks automatically performs the full refresh in a single update" ([full refresh](https://docs.databricks.com/ingestion/lakeflow-connect/full-refresh)); compare counts after that update. Change-feed readers from before it fail (`DELTA_CHANGE_DATA_FEED_INCOMPATIBLE_DATA_SCHEMA`).
- **Check the mapping before creating:** two sources to one destination fail the first update (`CDC_MULTIPLE_SOURCE_TABLES_MAPPED_TO_SAME_DESTINATION_TABLE`); destinations equal once `.` becomes `_` (`bronze_raw.orders`, `bronze.raw_orders`) fail every update (`FLOW_DEFINED_IN_MULTIPLE_DATASETS`).
- **After create:** the pipeline page says which fields can change. A second pipeline can't write tables another pipeline already manages.
- **Schedule** at the interval the smart closure page recommends. What a trigger does while an update still runs: read the smart closure page and the source's integrated pipeline page; if they differ (queued, or skipped), tell the user.
- **Keys:** a table without a primary key uses a unique key, else all columns except large objects, so identical rows collapse.

## Standard CDC

A gateway stages changes in a UC volume; an ingestion pipeline applies them.

Bundle: copy the gateway and ingestion pipeline examples on the source's pipeline page (`<source>-pipeline`).

Add `source_type` and the slot config where the page's example has them (PostgreSQL: [sources.md](sources.md#postgresql)).

- **Compute:** "Although the ingestion pipeline runs on serverless compute, the ingestion gateway must run on classic compute" ([SQL Server limits](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-limits)); "Gateways require classic compute and can't be deployed in a workspace that doesn't support classic compute" ([FAQ](https://docs.databricks.com/ingestion/lakeflow-connect/faq)).
- **Leave a kept gateway running:** "Do not manually stop the gateway", or changes past the source's log retention are lost. When a test is done, delete both pipelines.
- **Staging retention:** the source's pipeline page says how long staged changes are kept; an ingestion pipeline further behind than that needs a full refresh.
- **Two event logs:** an ingestion symptom often starts in the gateway's. An ingestion update can be `COMPLETED` before the gateway's `SNAPSHOT_COMPLETED` for each table: count rows after that.
- **Gateway compute errors:** "The Gateway pipeline does not allow spark config" (remove `spark.databricks.cluster.profile`, `spark.master`); `PENDING` at "Finding instances" (ask an admin for a node type with capacity); "You are not authorized to create instance pools" (ask an admin).

## Query-based

One pipeline queries each table each run for rows past the cursor's high-water mark; no change log.

Bundle: copy the example on the [query-based pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/query-based-pipeline) page; from a foreign catalog, the page's `ingest_from_uc_foreign_catalog` form. Soft deletes: `deletion_condition`, as the page shows.

- **`cursor_columns` (a list), not `cursor_column`:** the singular, as the query-based reference page spells it, is an unknown field: the CLI only warns, and the pipeline is created with no cursor, so every run is a full load. Check that `databricks bundle validate` reports no unknown field and that `databricks pipelines get <id>` shows `query_based_connector_config.cursor_columns`.
- **Cursor:** one column, bumped on every insert and update, never going back. An insert-only cursor (an auto-increment ID, Postgres `DEFAULT now()` without a `BEFORE UPDATE` trigger) misses updates with no error. "Rows with a NULL cursor column are not ingested" ([query-based limits](https://docs.databricks.com/ingestion/lakeflow-connect/query-based-limits)). No cursor: a full load each run.
- **What a run sees:** the latest state of each changed row; several changes between runs land once (SCD2 shows fewer versions). Hard deletes are invisible unless the hard-delete option is set; a soft-delete flag must bump the cursor.
- **Pre-flight, before creating:** check each declared key is unique and has no NULLs (`count(*)` vs `count(DISTINCT <key>)`, in one query for all tables), and that each cursor column has an index. A table with no key: read the query-based page for how it is keyed and which SCD types it allows. Don't ask the user to change their database.
- **Postgres `uuid` primary key:** an update that fails on `min(uuid)` needs an integer key (keep the uuid `UNIQUE`).
- **Network:** the pipeline's compute must reach the source (on serverless: serverless egress allowed, or Private Link through an NCC).

## Compute failures

Two failures, at different times; tell them apart before flipping `serverless`:
- **Compute not allowed,** at create, in seconds: "You must use serverless compute in this workspace" (a gateway there: use integrated CDC or query-based), or a classic cluster you can't create.
- **Compute starts but can't reach the source:** `Extractor FAILED` with `INGESTION_GATEWAY_UNREACHABLE_HOST_OR_PORT_FAILURE`. A wrong host or port gives the same error: run a `remote_query` on the same connection from serverless first. If that works and the update ran classic, the source's firewall likely allows the serverless ranges but not the workspace's classic egress IP.

Classic waits longer in `WAITING_FOR_RESOURCES`. `databricks clusters list-zones` listing zones means the workspace has classic.
