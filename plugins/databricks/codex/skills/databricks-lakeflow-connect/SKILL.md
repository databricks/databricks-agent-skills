---
name: databricks-lakeflow-connect
description: "Lakeflow Connect managed ingestion into Unity Catalog from databases (SQL Server, PostgreSQL, MySQL, Oracle) by CDC or query-based. Use when creating, running or debugging these pipelines."
compatibility: Requires databricks CLI (>= v1.2.0)
metadata:
  version: "0.3.0"
parent: databricks-core
---

# Lakeflow Connect: databases

Managed ingestion pipelines from databases into Unity Catalog Delta tables (SaaS apps and Kafka / RabbitMQ topics: **databricks-lakeflow-connect-saas**).

**The docs pages win.** Release stage, prerequisites, grants, limits, error text and field names change between releases: read the source's pages below before you build, and the workspace's error before this skill. This skill holds the order of steps, the gates, and the traps the pages don't state.

## Is Lakeflow Connect the right tool?

| If the source is... | Use | Skill |
|---|---|---|
| A database with a managed connector | **Lakeflow Connect** | this skill |
| A SaaS app (Salesforce, Workday, ServiceNow, SharePoint, ...) or a Kafka / RabbitMQ topic | **Lakeflow Connect** | **databricks-lakeflow-connect-saas** |
| Files on cloud object storage | Auto Loader | **databricks-pipelines** |
| A source to query in place, no copy | [Lakehouse Federation](https://docs.databricks.com/query-federation/) | n/a |
| An app or device that **pushes** events | Zerobus | **databricks-zerobus-ingest** |

## Modes per source

Pages are `https://docs.databricks.com/ingestion/lakeflow-connect/<source>-<page>`. For a mode marked "-", look for its page first (`<source>-integrated-pipeline` for integrated CDC, `<source>-pipeline` for standard CDC): if it exists, follow it; if it isn't found, tell the user Lakeflow Connect's docs have no <mode> page for <source>; if the docs can't be opened, that they had none when this skill was written. Then offer the modes the row links.

| Source (`<source>`) | Integrated CDC | Standard CDC (gateway) | Query-based | Setup, limits, errors |
|---|---|---|---|---|
| SQL Server (`sql-server`) | [integrated-pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-integrated-pipeline) | [pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-pipeline) | yes | [source-setup](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-source-setup), [limits](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-limits), [troubleshoot](https://docs.databricks.com/ingestion/lakeflow-connect/sql-server-troubleshoot) |
| MySQL (`mysql`) | [integrated-pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-integrated-pipeline) | [pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-pipeline) | yes | [source-setup](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-source-setup), [limits](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-limits), [troubleshoot](https://docs.databricks.com/ingestion/lakeflow-connect/mysql-troubleshoot) |
| PostgreSQL (`postgresql`) | - | [pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/postgresql-pipeline) | yes | [source-setup](https://docs.databricks.com/ingestion/lakeflow-connect/postgresql-source-setup), [limits](https://docs.databricks.com/ingestion/lakeflow-connect/postgresql-limits), [troubleshoot](https://docs.databricks.com/ingestion/lakeflow-connect/postgresql-troubleshoot) |
| Oracle (`oracle`) | [integrated-pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-integrated-pipeline) | - | yes | [integrated-setup](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-integrated-setup), [limits](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-limits), [troubleshoot](https://docs.databricks.com/ingestion/lakeflow-connect/oracle-troubleshoot) |
| Teradata, MariaDB, any Federation foreign catalog | - | - | yes | [query-based overview](https://docs.databricks.com/ingestion/lakeflow-connect/query-based-overview), [limits](https://docs.databricks.com/ingestion/lakeflow-connect/query-based-limits) |

**Which mode:** CDC without a kind named: ask which (integrated, one pipeline; standard, a gateway that runs and bills continuously), unless the source has one. "Standard", "two-pipeline" or "gateway" → standard. Every change or low source load → CDC (hard deletes with query-based: its [limits](https://docs.databricks.com/ingestion/lakeflow-connect/query-based-limits) page); otherwise, or when CDC can't be turned on at the source → query-based. **A mode marked "-"** with no page found (or the docs not reachable): tell the user as in [Modes per source](#modes-per-source), offer the modes it has, and don't author the requested one, even to try it. Never switch to standard silently: its gateway runs and bills continuously.

## What marks each mode in the pipeline

Field names and stages: `databricks bundle schema` (`pipelines.IngestionPipelineDefinition`). An ingestion pipeline has `ingestion_definition`, never `libraries`; `CREATE TABLE ... FROM CONNECTION` is Federation, not ingestion.

| Mode | Pipelines | Marking fields |
|---|---|---|
| Integrated CDC | one | `connection_name` + `connector_type: CDC`; `data_staging_options` (catalog, schema); every field the source's page says a create request must include (Oracle and MySQL: `channel: PREVIEW`) |
| Standard CDC | gateway + ingestion | gateway: `gateway_definition` (`connection_name`, `gateway_storage_catalog`, `_schema`, `_name`); ingestion: `ingestion_gateway_id: ${resources.pipelines.<gateway>.id}`; `source_type` and the source's settings where its page's example has them (PostgreSQL: `source_type: POSTGRESQL`, `source_configurations[].catalog.postgres.slot_config`) |
| Query-based, connection | one | `connection_name`, no `connector_type`; per table `table_configuration.query_based_connector_config.cursor_columns` (a list), `primary_keys`, `scd_type` |
| Query-based, foreign catalog | one | `ingest_from_uc_foreign_catalog: true`, no `connection_name`; `source_catalog` = the foreign catalog; `primary_keys` required unless `APPEND_ONLY` |

Every object: `table` with `source_catalog` / `source_schema` / `source_table`, `destination_catalog` / `destination_schema` (`destination_table` only to rename), or `schema` for a whole source schema. Per source: [sources.md](references/sources.md#where-names-go).

## Compute

Before creating, find what each pipeline would run on with `serverless` unset: the mode's pipeline page, and pipelines of the same mode already in this workspace (`databricks pipelines list-pipelines`; `update.config.serverless` of their latest update in `databricks pipelines get-update <id> <update-id> -o json`: `true` serverless, `false` classic). Compare that with the compute the user asked for: set `serverless` (and a `clusters` block for classic, as the mode's page shows) only when they differ, otherwise leave it unset. After the first update, read the same field to confirm. If the page says a mode or one of its pipelines (a gateway, an ingestion pipeline) can't run on the compute asked for, say so and offer what the page allows.
Details and the two compute failures: [modes.md](references/modes.md#compute-failures).

## Before creating anything

Ask for every missing input in one message (source, connection, tables, destination catalog and schema, mode, compute, schedule), list what you'll create, and wait for one "yes"; then run the setup without asking again. Never create a stand-in source without the user's go-ahead. Check:
1. **Target catalog and grants:** as the mode's pipeline page lists.
2. **A UC `CONNECTION`** with the source credentials: password as `secret('<scope>', '<key>')` (CREATE CONNECTION: use the secret function for any credential). After a rotation, run `ALTER CONNECTION <name> OPTIONS (..., password secret('<scope>', '<key>'))` with the options from the `CREATE` (`DESCRIBE CONNECTION` lists only some), then test the connection with a read. Write a request body with a password to a file only you can read, never on a command line.
3. **Network** from the compute that reads the source (the integrated pipeline, the gateway, or the query-based pipeline, on the compute chosen above).
4. **Source setup** from the source's `source-setup` page, and its traps in [sources.md](references/sources.md). Changes to the customer's database (CDC on a table, a slot): give the SQL to the user or their DBA; ask first.
5. **Query-based:** the [pre-flight checks](references/modes.md#query-based) (key unique, cursor bumped on update, no NULL cursors). Report, and let the user skip them for a snapshot or test.
6. **Names:** ask. Demos and tests without names: one `<base>_<epoch>` for pipeline, schema, job and bundle (standard CDC: `<base>_gw_<epoch>` and `<base>_ap_<epoch>`; staging `<base>_<epoch>_staging`). `mode: development` prefixes names, so slot and schema names taken from them stop matching.

## Run, schedule, clean up

- `databricks bundle deploy`, then `databricks bundle run <key> --no-wait` (or `pipelines start-update <id>`), then `get-update` until `COMPLETED` or `FAILED`; integrated CDC updates run long by design ([smart closure](references/modes.md#integrated-cdc)).
- Schedule with a Jobs `pipeline_task`; whether the mode can also run continuously, the mode's pipeline page says.
- After the first load and every full refresh, compare source and destination row counts; a `COMPLETED` status or low lag isn't proof rows landed. Rows per table per run: [rows-per-run.md](references/rows-per-run.md).
- Before a full refresh, read what the mode's page says it does to the table and to change-feed readers; warn and ask first.
- Clean up only with the user's OK: list the pipelines, schemas and PostgreSQL slot you'd remove, and what deleting a pipeline does to its tables (its page). Give the slot SQL to the user or their DBA. Don't stop a gateway the user keeps.

## When something fails

Read the full message (CLI error, deploy output, `ERROR`/`WARN` events with `details`), then the source's troubleshoot page, then [troubleshooting.md](references/troubleshooting.md) and [sources.md](references/sources.md). Then decide: a setting to change (take the value the message names), a missing grant (report the privilege and who grants it), a feature not enabled ("Ingestion source '<SOURCE>' is not supported in your workspace": report it, offer the modes that work), or a source-side fix. Error names, messages and behaviors in this skill that no docs page lists were seen in test runs: match on the message too, and prefer the docs page where they differ. Fix that one thing and retry the same step; offer `bundle destroy` for what a failed deploy left.

## Reference files

| File | When |
|---|---|
| [modes.md](references/modes.md) | Integrated CDC, standard CDC, query-based: how each behaves, one example each, compute failures |
| [sources.md](references/sources.md) | SQL Server, PostgreSQL, MySQL, Oracle: names per source, prerequisite traps, errors from runs |
| [troubleshooting.md](references/troubleshooting.md) | Event log, cross-pipeline errors, table limits, runtime per update |
| [rows-per-run.md](references/rows-per-run.md) | Rows per table per run ([`scripts/rows_per_run.sql`](scripts/rows_per_run.sql)) |

## Related skills

**databricks-pipelines** (runtime, event log), **databricks-dabs** (bundles), **databricks-jobs** (`pipeline_task`), **databricks-unity-catalog** (catalogs, connections), **databricks-lakebase** (Lakebase projects and roles), **databricks-zerobus-ingest** (push).
