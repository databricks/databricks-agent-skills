REPLACE USING flows (Beta, Databricks Runtime 18.2 or above) in Spark Declarative Pipelines keep a streaming table up to date by key: on each logical batch they atomically delete the target rows whose key columns match the incoming rows and insert the incoming rows, leaving every other key untouched. A `SEQUENCE BY` column orders the logical batches so the result is correct even when the streaming source delivers rows split across micro-batches or out of order. Reach for REPLACE USING when a streaming source re-emits all rows for a key and you want the latest version to replace the old one — for example re-ingesting mutable files where a re-uploaded file must replace exactly its own rows. Use AUTO CDC instead when the source is a stream of change *events* needing insert/update/delete handling or SCD history — including keep-latest-per-key (SCD Type 1); REPLACE USING neither interprets delete events nor tracks history, and it can retain multiple rows per key (e.g. every row of a re-ingested file). Use a REPLACE WHERE flow when you overwrite a predicate-defined window (e.g. the last N days) rather than matching by key.

**API Reference:**

**Inline shorthand (preferred):** The target table and flow are defined together. The flow inherits the table's name.

```sql
CREATE STREAMING TABLE <target_table>
FLOW REPLACE USING (<key_col>, ...) SEQUENCE BY <sequence_col> BY NAME
SELECT ... FROM STREAM <source>;
```

**Long form (`CREATE FLOW`):** Declare the target separately, then attach the flow. Note that `BY NAME` sits right after the target here, before `REPLACE USING`.

```sql
CREATE STREAMING TABLE <target_table>;

CREATE FLOW <flow_name> AS
INSERT INTO <target_table> BY NAME
REPLACE USING (<key_col>, ...) SEQUENCE BY <sequence_col>
SELECT ... FROM STREAM <source>;
```

Parameters:

- `<target_table>` (identifier): Streaming table managed by this pipeline. Must be defined inside this pipeline — you cannot point a REPLACE USING flow at a table created outside of it. **Required.**
- `REPLACE USING (<key_col>, ...)` (parenthesized column list): One or more top-level key columns identifying which target rows a logical batch replaces. Every key must exist in the SELECT output. **Required.**
- `SEQUENCE BY <sequence_col>` (column or expression): Orders logical batches. Rows sharing a `SEQUENCE BY` value form one logical batch; within a key the highest sequence wins, and a later batch supersedes an earlier one. **Required whenever REPLACE USING is used.**
- `BY NAME`: Required. Columns from the SELECT are matched to the target by name, not position. In the inline form it follows `SEQUENCE BY`; in the `CREATE FLOW` form it follows the target identifier.
- `<flow_name>` (identifier, long form only): Identifier for the standalone flow. **Required for `CREATE FLOW` syntax.**
- `<source>`: Must be a **streaming** source (`STREAM(...)`, `read_files`, `read_kafka`, a streaming read of another table). A batch source is rejected.

**Common Patterns:**

**Pattern 1: Re-ingest mutable files — replace a file's rows when it is re-uploaded**

The canonical case. Auto Loader with `allowOverwrites` re-reads a changed file; keying on the file path and sequencing by the file modification time means a re-uploaded file atomically replaces exactly its own rows.

```sql
CREATE STREAMING TABLE customer_records
FLOW REPLACE USING (file_path) SEQUENCE BY file_modified BY NAME
SELECT
  _metadata.file_path AS file_path,
  _metadata.file_modification_time AS file_modified,
  customer_id, name, email
FROM STREAM read_files('s3://bucket/customers/', format => 'csv', allowOverwrites => true);
```

**Pattern 2: Composite key**

List several columns to match on their combination. A logical batch replaces target rows matching the full key tuple.

```sql
CREATE STREAMING TABLE inventory
FLOW REPLACE USING (warehouse_id, sku) SEQUENCE BY updated_at BY NAME
SELECT warehouse_id, sku, quantity, updated_at
FROM STREAM inventory_updates;
```

**Pattern 3: Long form with a separately declared target**

```sql
CREATE STREAMING TABLE customer_records;

CREATE FLOW customer_records_flow AS
INSERT INTO customer_records BY NAME
REPLACE USING (file_path) SEQUENCE BY file_modified
SELECT
  _metadata.file_path AS file_path,
  _metadata.file_modification_time AS file_modified,
  customer_id, name, email
FROM STREAM read_files('s3://bucket/customers/', format => 'csv', allowOverwrites => true);
```

**Pattern 4: Migrate a foreachBatch `INSERT ... REPLACE USING` workaround**

Before — a `foreachBatch` sink running the DML per micro-batch, which leaves the target outside the pipeline DAG (no lineage, no full refresh, must be a leaf):

```python
def upsert(df, batch_id):
    df.sparkSession.sql("INSERT INTO customer_records REPLACE USING (file_path) SELECT * FROM batch")
```

After — a declarative REPLACE USING flow. The target becomes a managed streaming table with lineage and full-refresh support, and `SEQUENCE BY` keeps it correct under arbitrary micro-batch boundaries:

```sql
CREATE STREAMING TABLE customer_records
FLOW REPLACE USING (file_path) SEQUENCE BY file_modified BY NAME
SELECT file_path, file_modified, customer_id, name, email FROM STREAM raw_customers;
```

**Data Quality (Expectations):**

Expectations are supported. `warn` and `fail` behave as elsewhere. For `ON VIOLATION DROP ROW`, a dropped row is treated as if the source never produced it: it is filtered before within-batch dedupe, it does not advance the key's sequence, and if *every* incoming row for a key is dropped, no delete fires and the key keeps its existing value (a bad re-ingest cannot wipe good data).

**Backfills:**

A REPLACE USING batch only touches keys present in the incoming data, so pointing a new REPLACE USING flow at a table that already holds data is safe — existing keys absent from the stream are left untouched. To seed history that will never re-arrive on the stream, load it once with a one-time append flow (`CREATE FLOW ... INSERT INTO ... ONCE`) into the same table.

**KEY RULES:**

- `SEQUENCE BY` is **required** whenever REPLACE USING is used — it orders logical batches so the flow stays correct under out-of-order processing.
- `BY NAME` is required. Its position differs by form: after `SEQUENCE BY` in the inline form, after the target identifier in the `CREATE FLOW` form.
- Key columns are a parenthesized list of **top-level** columns and must support equality — `MAP` and `VARIANT` keys are rejected. At least one key, no duplicates (compared case-insensitively).
- The source must be a **streaming** source; a batch source is rejected.
- The target must be a streaming table created inside this pipeline. You cannot target an externally created table.
- NULL keys use null-safe equality: a NULL key matches a NULL key and is replaced like any other.
- A REPLACE USING target cannot also be the target of an AUTO CDC, REPLACE WHERE, or MERGE flow — mixing them is rejected. Multiple flows into one REPLACE USING target are not supported in Beta; use a single REPLACE USING flow per target.
- REPLACE USING flows require Databricks Runtime 18.2 or above.
