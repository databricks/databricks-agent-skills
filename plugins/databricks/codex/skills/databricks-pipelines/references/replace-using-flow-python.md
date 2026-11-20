REPLACE USING flows (Beta, Databricks Runtime 18.2 or above) in Spark Declarative Pipelines keep a streaming table up to date by key: on each logical batch they atomically delete the target rows whose key columns match the incoming rows and insert the incoming rows, leaving every other key untouched. A `sequence_by` column orders the logical batches so the result is correct even when the streaming source delivers rows split across micro-batches or out of order. Reach for REPLACE USING when a streaming source re-emits all rows for a key and you want the latest version to replace the old one — for example re-ingesting mutable files where a re-uploaded file must replace exactly its own rows. Use Auto CDC instead when the source is a stream of change *events* needing insert/update/delete handling or SCD history — including keep-latest-per-key (SCD Type 1); REPLACE USING neither interprets delete events nor tracks history, and it can retain multiple rows per key (e.g. every row of a re-ingested file). Use a REPLACE WHERE flow when you overwrite a predicate-defined window (e.g. the last N days) rather than matching by key.

**API Reference:**

**@dp.table(replace_using=[...], sequence_by=...) / @dlt.table(...)** Defines a streaming table whose flow is a REPLACE USING flow. The flow inherits the table's name.

```python
@dp.table(
    name="<target_table>",
    replace_using=["<key_col>", ...],
    sequence_by="<sequence_col>",
)
def <target_table>():
    return <streaming DataFrame>
```

**dp.replace_flow(target=..., replace_using=[...], sequence_by=...)** Standalone flow into a pre-created streaming table. Use when the target is declared separately (e.g. to attach a comment or per-flow `spark_conf`).

```python
dp.create_streaming_table("<target_table>")

@dp.replace_flow(
    target="<target_table>",
    replace_using=["<key_col>", ...],
    sequence_by="<sequence_col>",
)
def <flow_name>():
    return <streaming DataFrame>
```

Parameters:

- `name` / `target` (str): Target streaming table, managed by this pipeline. `@dp.table` defaults `name` to the function name; `dp.replace_flow` requires `target`. You cannot point REPLACE USING at a table created outside this pipeline.
- `replace_using` (list[str]): Top-level key columns identifying which target rows a logical batch replaces. Every key must exist in the returned DataFrame. **Required** (at least one column).
- `sequence_by` (str | Column): Column (or expression) that delimits and orders logical batches. Within a key the highest sequence wins, and a later batch supersedes an earlier one. **Required whenever `replace_using` is used.**

The function returns the source streaming DataFrame. Columns are matched to the target by name.

**Common Patterns:**

**Pattern 1: Re-ingest mutable files — replace a file's rows when it is re-uploaded**

The canonical case. Auto Loader with `cloudFiles.allowOverwrites` re-reads a changed file; keying on the file path and sequencing by the file modification time means a re-uploaded file atomically replaces exactly its own rows.

```python
@dp.table(
    name="customer_records",
    replace_using=["file_path"],
    sequence_by="file_modified",
)
def customer_records():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.allowOverwrites", "true")
        .load("s3://bucket/customers/")
        .selectExpr(
            "_metadata.file_path AS file_path",
            "_metadata.file_modification_time AS file_modified",
            "customer_id", "name", "email",
        )
    )
```

**Pattern 2: Composite key**

```python
@dp.table(
    name="inventory",
    replace_using=["warehouse_id", "sku"],
    sequence_by="updated_at",
)
def inventory():
    return spark.readStream.table("inventory_updates")
```

**Pattern 3: Standalone flow with a separately declared target**

Use `dp.replace_flow` when you want to declare the target separately or thread a `comment` / `spark_conf` through the flow.

```python
dp.create_streaming_table("customer_records")

@dp.replace_flow(
    target="customer_records",
    replace_using=["file_path"],
    sequence_by="file_modified",
    comment="Replace each file's rows on re-ingest",
)
def customer_records_flow():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.allowOverwrites", "true")
        .load("s3://bucket/customers/")
        .selectExpr(
            "_metadata.file_path AS file_path",
            "_metadata.file_modification_time AS file_modified",
            "customer_id", "name", "email",
        )
    )
```

**Pattern 4: Migrate a foreachBatch `INSERT ... REPLACE USING` workaround**

Before — a `foreachBatch` sink running the DML per micro-batch, which leaves the target outside the pipeline DAG (no lineage, no full refresh, must be a leaf):

```python
def upsert(df, batch_id):
    df.sparkSession.sql("INSERT INTO customer_records REPLACE USING (file_path) SELECT * FROM batch")
```

After — a declarative REPLACE USING flow. The target becomes a managed streaming table with lineage and full-refresh support, and `sequence_by` keeps it correct under arbitrary micro-batch boundaries:

```python
@dp.table(name="customer_records", replace_using=["file_path"], sequence_by="file_modified")
def customer_records():
    return spark.readStream.table("raw_customers")
```

**Data Quality (Expectations):**

Expectations are supported. `expect` (warn) and `expect_or_fail` behave as elsewhere. For `expect_or_drop`, a dropped row is treated as if the source never produced it: it is filtered before within-batch dedupe, it does not advance the key's sequence, and if *every* incoming row for a key is dropped, no delete fires and the key keeps its existing value (a bad re-ingest cannot wipe good data).

**Backfills:**

A REPLACE USING batch only touches keys present in the incoming data, so pointing a new REPLACE USING flow at a table that already holds data is safe — existing keys absent from the stream are left untouched. To seed history that will never re-arrive on the stream, load it once with a one-time append flow (`@dp.append_flow(once=True)`) into the same table.

**KEY RULES:**

- `sequence_by` is **required** whenever `replace_using` is used — it orders logical batches so the flow stays correct under out-of-order processing.
- `replace_using` is a list of **top-level** columns and must support equality — `MAP` and `VARIANT` keys are rejected. At least one key, no duplicates (compared case-insensitively).
- The function must return a **streaming** DataFrame; a batch DataFrame is rejected.
- The target must be a streaming table created inside this pipeline. You cannot target an externally created table.
- NULL keys use null-safe equality: a NULL key matches a NULL key and is replaced like any other.
- `replace_using` and `replace_where` are mutually exclusive on the same table.
- A REPLACE USING target cannot also be the target of an Auto CDC, REPLACE WHERE, or MERGE flow — mixing them is rejected. Multiple flows into one REPLACE USING target are not supported in Beta; use a single REPLACE USING flow per target.
- Prefer `from pyspark import pipelines as dp`; the `dlt` module (`@dlt.table`, `dlt.replace_flow`) is the deprecated alias and still works. Do NOT change existing `dlt` imports.
- REPLACE USING flows require Databricks Runtime 18.2 or above.
