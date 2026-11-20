# SDP Target Syntax Reference

Generic SDP syntax for both the Generate and Repair phases. This file is source-agnostic
— it describes the SDP target, not how any particular ETL source maps onto it. Source
packs (`references/migrate-to-sdp/sources/<source>/`) own the source-specific mappings.

For deeper SDP feature docs (Auto Loader, Auto CDC, expectations, sinks, etc.), the
other `references/` files of this skill are the source of truth — read them when you need feature-specific details.

## SDP Python (`pyspark.pipelines`)

> **Do NOT use `spark.sql()` in Python output.** When `output_format` is `python`,
> implement logic via the PySpark DataFrame API (`select`, `where`, `filter`,
> `groupBy`, `agg`, `join`, `withColumn`, etc.). Embedding SQL strings via
> `spark.sql()` defeats the point of choosing Python. If logic is naturally SQL,
> set `output_format: sql` instead.

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, expr

# Streaming table
@dp.table()
@dp.expect_or_drop("valid", "col IS NOT NULL")
def my_table():
    return spark.readStream.table("source")

# Materialized view
@dp.materialized_view()
def my_mv():
    return spark.read.table("upstream").filter("status = 'active'")

# Temporary view
@dp.temporary_view()
def my_temp():
    return spark.read.table("raw").select("id", "name")

# AUTO CDC (merge/upsert with SCD Type 1)
@dp.temporary_view()
def cdc_source():
    return spark.readStream.table("catalog.schema.source_cdf")

dp.create_streaming_table("target")
dp.create_auto_cdc_flow(
    target="target", source="cdc_source",
    keys=["id"], sequence_by=col("updated_at"),
    apply_as_deletes=expr("op = 'DELETE'"),
    except_column_list=["op"],
    stored_as_scd_type=1,
)

# AUTO CDC from snapshot (periodic snapshot strategy)
dp.create_streaming_table("target_scd2")
dp.create_auto_cdc_from_snapshot_flow(
    target="target_scd2", source="snapshot_view",
    keys=["id"], stored_as_scd_type=2,
)
```

## SDP SQL

```sql
-- Streaming table with expectations
CREATE OR REFRESH STREAMING TABLE orders(
  CONSTRAINT valid EXPECT (id IS NOT NULL) ON VIOLATION DROP ROW
) AS SELECT * FROM STREAM catalog.schema.source;

-- Materialized view
CREATE OR REFRESH MATERIALIZED VIEW summary
AS SELECT date, count(*) cnt FROM orders GROUP BY date;

-- Temporary view
CREATE TEMPORARY VIEW cleaned AS SELECT * FROM raw WHERE status IS NOT NULL;

-- AUTO CDC (merge/upsert)
CREATE OR REFRESH STREAMING TABLE target;
CREATE FLOW merge_flow AS
  AUTO CDC INTO target FROM STREAM(catalog.schema.cdf)
  KEYS (id) SEQUENCE BY updated_at
  COLUMNS * EXCEPT (op)
  STORED AS SCD TYPE 1;

-- AUTO CDC SCD Type 2
CREATE OR REFRESH STREAMING TABLE target_history;
CREATE FLOW history_flow AS
  AUTO CDC INTO target_history FROM STREAM(catalog.schema.cdf)
  KEYS (id) SEQUENCE BY updated_at
  APPLY AS DELETE WHEN op = "DELETE"
  STORED AS SCD TYPE 2;

-- AUTO CDC from recurring snapshots (DBR 18.3+); each snapshot_version
-- must identify one immutable, complete snapshot
CREATE OR REFRESH STREAMING TABLE target_snapshot_history;
CREATE FLOW snapshot_history_flow AS
  AUTO CDC INTO target_snapshot_history
  FROM SNAPSHOT (
    SELECT * EXCEPT (snapshot_version)
    FROM catalog.schema.snapshots
    WHERE snapshot_version = (
      SELECT version FROM current_snapshot_version()
    )
  )
  WITH VERSION (
    SELECT snapshot_version AS version
    FROM (SELECT DISTINCT snapshot_version FROM catalog.schema.snapshots)
    WHERE (
      NOT EXISTS (SELECT 1 FROM last_snapshot_version())
      OR snapshot_version > (SELECT version FROM last_snapshot_version())
    )
    ORDER BY snapshot_version
    LIMIT 1
  )
  KEYS (id)
  STORED AS SCD TYPE 2;

-- One-time initial snapshot into an empty target; no WITH VERSION
CREATE OR REFRESH STREAMING TABLE target_initial_snapshot;
CREATE FLOW initial_snapshot_flow AS
  AUTO CDC ONCE INTO target_initial_snapshot
  FROM SNAPSHOT (
    SELECT id, value FROM catalog.schema.current_snapshot
  )
  KEYS (id)
  STORED AS SCD TYPE 1;
```

## SDP dataset types (cheat sheet)

| sdp_type            | Persisted       | Stores Data | Streaming | Use                                             |
| ------------------- | --------------- | ----------- | --------- | ----------------------------------------------- |
| `streaming_table`   | Yes             | Yes         | Yes       | Append-only ingestion, CDC targets, windows     |
| `materialized_view` | Yes             | Yes         | No        | Aggregations, batch transforms, gold layer      |
| `temporary_view`    | No              | No          | Yes/No    | Pipeline-private intermediate logic             |
| `auto_cdc`          | Yes (target ST) | Yes         | Yes       | Merge/upsert from streaming source (SCD 1 or 2) |
| `auto_cdc_snapshot` | Yes (target ST) | Yes         | Yes       | Versioned recurring SQL, unversioned SQL `ONCE`, or recurring Python snapshot CDC |

## Table properties

`TBLPROPERTIES` applies to `STREAMING TABLE` and `MATERIALIZED VIEW`, not
`TEMPORARY VIEW` (temporary views have no storage).

**Python**:

```python
@dp.table(table_properties={"delta.autoOptimize.optimizeWrite": "true"})
```

**SQL** (after the table/view definition, before `AS`):

```sql
CREATE OR REFRESH STREAMING TABLE orders
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
AS SELECT * FROM STREAM catalog.schema.source;
```

## Reading data within a pipeline

| Read pattern                          | Python                                         | SQL                           |
| ------------------------------------- | ---------------------------------------------- | ----------------------------- |
| Pipeline-internal dataset (batch)     | `spark.read.table("name")`                     | `SELECT ... FROM name`        |
| Pipeline-internal dataset (streaming) | `spark.readStream.table("name")`               | `SELECT ... FROM STREAM name` |
| External UC table (batch)             | `spark.read.table("catalog.schema.tbl")`       | `catalog.schema.tbl`          |
| External UC table (streaming)         | `spark.readStream.table("catalog.schema.tbl")` | `STREAM(catalog.schema.tbl)`  |

Within a pipeline, refer to other datasets by their bare name. Fully qualify only
when reading external tables (i.e. anything not produced by this pipeline).

### Ingesting files with Auto Loader

Incremental file ingestion from cloud storage or a UC Volume path uses Auto Loader
and always produces a **`streaming_table`**. The Volume/path is the _source_, not a
dataset — model the output as a streaming table that reads from the path, never as
a materialized view of the files or as the Volume itself.

**SQL** — `read_files` wrapped in `STREAM(...)`:

```sql
CREATE OR REFRESH STREAMING TABLE raw_events
AS SELECT * FROM STREAM(read_files('/Volumes/cat/schema/vol/events/', format => 'json'));
```

**Python** — `cloudFiles`:

```python
@dp.table()
def raw_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/cat/schema/vol/events/")
    )
```

The exception is a one-time batch read of small static reference data (e.g. a DBT
seed CSV): that stays a `materialized_view` reading `read_files(...)` / `spark.read`
_without_ `STREAM` / `readStream`. For the full option set, read
`references/auto-loader-sql.md` or
`references/auto-loader-python.md`.

## Parameters

Preserve source parameterization — values that vary across runs (date thresholds,
region codes, source table names) stay parameters, not hard-coded literals. The
form depends on `output_format`.

**SQL — named parameters (`:name`)** (DBR 17.0+). Reference a parameter with a
leading colon. Values arrive as `STRING`, so `CAST` when the position isn't a
string:

```sql
WHERE order_date >= CAST(:start_date AS DATE)
LIMIT CAST(:row_limit AS INT)
```

A bare `:name` is a value, not an identifier. To use one as a
catalog / schema / table / column name, wrap it in `IDENTIFIER()`:

```sql
FROM STREAM(IDENTIFIER(:src_catalog || '.' || :src_schema || '.orders'))
```

Do NOT emit the legacy `${name}` interpolation form — `:name` is the supported
syntax.

**Python — `spark.conf.get`.** Python does not support `:name`. Read every
parameter one way — `spark.conf.get("name")`, with an optional default as the
second argument — and build identifiers with f-strings:

```python
src_catalog = spark.conf.get("src_catalog")
start_date = spark.conf.get("start_date", "2024-01-01")
return spark.readStream.table(f"{src_catalog}.{src_schema}.orders")
```

**Declaring defaults.** A SQL pipeline that references `:name` must have a matching
key declared or analysis fails. The Generate phase declares them by editing the
pipeline settings: SQL → the top-level `parameters` map (`{"name": "value"}`,
distinct from `configuration`); Python → the `configuration` map. Keys: 1–100
chars, letters / digits / underscores / dashes. The
parameter references of this skill cover deeper parameter behavior.

## Expectations

| Severity                | Python                                     | SQL                                                      |
| ----------------------- | ------------------------------------------ | -------------------------------------------------------- |
| Warn                    | `@dp.expect("name", "expr")`               | `CONSTRAINT name EXPECT (expr)`                          |
| Drop row                | `@dp.expect_or_drop("name", "expr")`       | `CONSTRAINT name EXPECT (expr) ON VIOLATION DROP ROW`    |
| Fail update             | `@dp.expect_or_fail("name", "expr")`       | `CONSTRAINT name EXPECT (expr) ON VIOLATION FAIL UPDATE` |
| Multiple at once (warn) | `@dp.expect_all({"n1": "e1", "n2": "e2"})` | Multiple `CONSTRAINT` clauses                            |

> **AUTO CDC**: expectations apply on the **source view** feeding into
> `create_auto_cdc_flow()`, not on the target streaming table itself.
