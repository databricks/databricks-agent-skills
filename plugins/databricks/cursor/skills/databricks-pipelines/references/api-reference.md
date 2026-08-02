# API Reference

Signatures and options for the `pyspark.pipelines` API surface. Read this
when you need the exact decorator, argument, or option for a dataset, flow,
sink, CDC, data-quality, read, or table-feature call.

### Dataset Definition APIs

| Feature                    | Description                                                      | Python                            | SQL                                         | Skill (Py)                                              | Skill (SQL)                                       |
| -------------------------- | ---------------------------------------------------------------- | --------------------------------- | ------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| Streaming Table            | Continuous incremental processing, exactly-once, append-only.    | `@dp.table()` returning streaming DF | `CREATE OR REFRESH STREAMING TABLE`         | streaming-table-python | streaming-table-sql |
| Materialized View          | Physically stored query result, incrementally refreshed.         | `@dp.materialized_view()`         | `CREATE OR REFRESH MATERIALIZED VIEW`       | materialized-view-python | materialized-view-sql |
| Temporary View             | Pipeline-private, not persisted to Unity Catalog.                | `@dp.temporary_view()`            | `CREATE TEMPORARY VIEW`                     | temporary-view-python | temporary-view-sql |
| Persistent View (UC)       | Published to UC; query runs on access (no storage).              | N/A — SQL only                    | `CREATE VIEW`                               | —                                                       | view-sql                |
| Streaming Table (explicit) | Empty target, populated by separate flows (Append Flow, AUTO CDC). | `dp.create_streaming_table()`     | `CREATE OR REFRESH STREAMING TABLE` (no AS) | streaming-table-python | streaming-table-sql |

### Flow and Sink APIs

| Feature                      | Description                                                      | Python                       | SQL                                    | Skill (Py)                                                  | Skill (SQL)                                       |
| ---------------------------- | ---------------------------------------------------------------- | ---------------------------- | -------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| Append Flow                  | Fan-in: multiple sources → one streaming table. Use instead of UNION. | `@dp.append_flow()`     | `CREATE FLOW ... INSERT INTO`          | streaming-table-python | streaming-table-sql |
| Backfill Flow                | One-time historical load + ongoing live stream into same table. | `@dp.append_flow(once=True)` | `CREATE FLOW ... INSERT INTO ... ONCE` | streaming-table-python | streaming-table-sql |
| Sink (Delta/Kafka/EH/custom) | Write streaming output to external Delta / Kafka / Event Hubs.   | `dp.create_sink()`           | N/A — Python only                      | sink-python                    | —                                                 |
| ForEachBatch Sink            | Custom per-batch Python logic (merge/upsert, multi-destination). Public Preview. | `@dp.foreach_batch_sink()` | N/A — Python only         | foreach-batch-sink-python | —                                       |
| RTM update flow              | Real-Time Mode: route a flow to a sink with sub-second latency. Public Preview. | `@dp.update_flow(target=...)` | N/A — Python only          | real-time-mode              | —                                                 |

### CDC APIs

| Feature                      | Description                                                          | Python                                      | SQL                             | Skill (Py)                                | Skill (SQL)                          |
| ---------------------------- | -------------------------------------------------------------------- | ------------------------------------------- | ------------------------------- | ----------------------------------------- | ------------------------------------ |
| Auto CDC (streaming source)  | SCD Type 1 (overwrite) or Type 2 (history) from a CDC feed.          | `dp.create_auto_cdc_flow()`                 | `AUTO CDC INTO ... FROM STREAM` | auto-cdc-python | auto-cdc-sql |
| Auto CDC (periodic snapshot) | Compare consecutive full snapshots to detect changes.                | `dp.create_auto_cdc_from_snapshot_flow()`   | N/A — Python only               | auto-cdc-python | —                                    |

For querying SCD Type 2 history tables (`__START_AT` / `__END_AT`, point-in-time, joining facts with historical dimensions), see scd-2-querying.

### Data Quality APIs

| Feature            | Description                                | Python                       | SQL                                                    | Skill (Py)                                            | Skill (SQL)                                     |
| ------------------ | ------------------------------------------ | ---------------------------- | ------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------------- |
| Expect (warn)      | Log violations, keep all rows.             | `@dp.expect()`               | `CONSTRAINT ... EXPECT (...)`                          | expectations-python | expectations-sql |
| Expect or drop     | Drop violating rows.                       | `@dp.expect_or_drop()`       | `CONSTRAINT ... EXPECT (...) ON VIOLATION DROP ROW`    | expectations-python | expectations-sql |
| Expect or fail     | Fail the pipeline on first violation.      | `@dp.expect_or_fail()`       | `CONSTRAINT ... EXPECT (...) ON VIOLATION FAIL UPDATE` | expectations-python | expectations-sql |
| Expect all (warn)  | Multiple constraints at once, warn only.   | `@dp.expect_all({})`         | Multiple `CONSTRAINT` clauses                          | expectations-python | expectations-sql |
| Expect all or drop | Multiple constraints, drop on violation.   | `@dp.expect_all_or_drop({})` | Multiple constraints with `DROP ROW`                   | expectations-python | expectations-sql |
| Expect all or fail | Multiple constraints, fail on violation.   | `@dp.expect_all_or_fail({})` | Multiple constraints with `FAIL UPDATE`                | expectations-python | expectations-sql |

### Reading Data APIs

| Feature                           | Description                                            | Python                                         | SQL                                              | Skill (Py)                                              | Skill (SQL)                                       |
| --------------------------------- | ------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------- |
| Batch read (pipeline dataset)     | Read a sibling table as a static DataFrame.            | `spark.read.table("name")`                     | `SELECT ... FROM name`                           | —                                                       | —                                                 |
| Streaming read (pipeline dataset) | Read a sibling table as a streaming DataFrame.         | `spark.readStream.table("name")`               | `SELECT ... FROM STREAM(name)`                   | —                                                       | —                                                 |
| Auto Loader (cloud files)         | Incrementally ingest new files from cloud storage.     | `spark.readStream.format("cloudFiles")`        | `STREAM read_files(...)`                         | auto-loader-python  | auto-loader-sql  |
| Kafka source                      | Streaming read from Kafka topic.                       | `spark.readStream.format("kafka")`             | `STREAM read_kafka(...)`                         | kafka                            | kafka                      |
| Kinesis source                    | Streaming read from AWS Kinesis.                       | `spark.readStream.format("kinesis")`           | `STREAM read_kinesis(...)`                       | —                                                       | —                                                 |
| Pub/Sub source                    | Streaming read from GCP Pub/Sub.                       | `spark.readStream.format("pubsub")`            | `STREAM read_pubsub(...)`                        | —                                                       | —                                                 |
| Pulsar source                     | Streaming read from Apache Pulsar.                     | `spark.readStream.format("pulsar")`            | `STREAM read_pulsar(...)`                        | —                                                       | —                                                 |
| Event Hubs source                 | Streaming read from Azure Event Hubs (Kafka protocol). | `spark.readStream.format("kafka")` + EH config | `STREAM read_kafka(...)` + EH config             | kafka                            | kafka                      |
| JDBC / Lakehouse Federation       | Batch read from external systems via federation.       | `spark.read.format("postgresql")` etc.         | Direct table ref via federation catalog          | —                                                       | —                                                 |
| Custom data source                | User-defined Python data source.                       | `spark.read[Stream].format("custom")`          | N/A — Python only                                | —                                                       | —                                                 |
| Static file read (batch)          | One-shot load of files (no incremental tracking).      | `spark.read.format("json"\|"csv"\|...).load()` | `read_files(...)` (no STREAM)                    | —                                                       | —                                                 |
| Skip upstream change commits      | Ignore CDC commits on the upstream table.              | `.option("skipChangeCommits", "true")`         | `read_stream("name", skipChangeCommits => true)` | streaming-table-python | streaming-table-sql |

### Table/Schema Feature APIs

| Feature                      | Description                                                   | Python                                                | SQL                                     | Skill (Py)                                              | Skill (SQL)                                       |
| ---------------------------- | ------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| Liquid clustering            | Adaptive multi-column data layout; replaces PARTITION + Z-ORDER. Prefer Auto clustering when possible | `cluster_by=[...]`                                 | `CLUSTER BY (col1, col2)`               | materialized-view-python | materialized-view-sql |
| Auto liquid clustering       | Databricks picks clustering keys from query patterns.         | `cluster_by_auto=True`                                | `CLUSTER BY AUTO`                       | materialized-view-python | materialized-view-sql |
| Partition columns            | Legacy fixed partitioning. Prefer Liquid Clustering.          | `partition_cols=[...]`                                | `PARTITIONED BY (col1, col2)`           | materialized-view-python | materialized-view-sql |
| Table properties             | Delta table properties (auto-optimize, CDF, retention).       | `table_properties={...}`                              | `TBLPROPERTIES (...)`                   | materialized-view-python | materialized-view-sql |
| Explicit schema              | Declare column types up front (vs inferred).                  | `schema="col1 TYPE, ..."`                             | `(col1 TYPE, ...) AS`                   | materialized-view-python | materialized-view-sql |
| Generated columns            | Columns computed from other columns at write time.            | `schema="..., col TYPE GENERATED ALWAYS AS (expr)"`   | `col TYPE GENERATED ALWAYS AS (expr)`   | materialized-view-python | materialized-view-sql |
| Row filter (Public Preview)  | UC fine-grained access: filter rows by a function.            | `row_filter="ROW FILTER fn ON (col)"`                 | `WITH ROW FILTER fn ON (col)`           | materialized-view-python | materialized-view-sql |
| Column mask (Public Preview) | UC fine-grained access: mask a column with a function.        | `schema="..., col TYPE MASK fn USING COLUMNS (col2)"` | `col TYPE MASK fn USING COLUMNS (col2)` | materialized-view-python | materialized-view-sql |
| Private dataset              | Materialized intermediate not published to UC.                | `private=True`                                        | `CREATE PRIVATE ...`                    | materialized-view-python | materialized-view-sql |
