# Arrow Flight: send columnar batches

Read this when the producer has **columnar data** (Arrow tables, Parquet files, DataFrames) or sends rows **in batches**. Also when a workload writes files to cloud storage just so Databricks loads them-Arrow Flight can stream directly instead.

## When to use it
| Use Arrow Flight | Use something else |
|---|---|
| **Columnar data** (Parquet files, DataFrames, Arrow tables) that would otherwise be written to cloud storage | Files already in cloud storage → **Auto Loader** |
| **Batches of rows** or **wide/numeric-heavy schemas** | Sparse, one-row-at-a-time → JSON/Protobuf ([python-sdk.md](python-sdk.md)) |
| | Need ack callbacks → use JSON/Protobuf (Arrow doesn't support callbacks) |
| | Edge runtimes → **REST** ([rest.md](rest.md)) |

**Status:** the Apache Arrow format is **GA**. SDKs with Arrow Flight: Python, Rust, Java, Go (cgo), C++, TypeScript; versions in [SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples).

## How it works
- **One stream, one table.** Uses the same Zerobus endpoint, OAuth flow, and headers as JSON/Protobuf. Wire protocol is Arrow Flight `DoPut` over gRPC.
- **One offset per batch.** SDK serializes to IPC and splits large batches internally. Durability is cumulative, so a large batch can be **partially durable** mid-send.
- **Size limits:** Batch not bound by 10 MB; **each row** must fit in 10 MB.
- **No ack callbacks.** Arrow doesn't support them. Confirm durability with `flush()` at boundaries (e.g., per file).
- **Backpressure:** `max_inflight_batches` default 1,000.
- **Recovery:** Reconnects and replays unacknowledged batches (on by default).

## Step 1: Make the Arrow schema match the table
Zerobus matches Arrow fields to Delta columns **by name**, and the docs set these rules:
- **Include** every non-nullable (`NOT NULL`) column. You **may omit** nullable columns; Zerobus writes them as `NULL`.
- **Don't include** fields the table doesn't have.
- **Keep the Delta column order** for the fields you include.
- **Match nullability**: a `NOT NULL` column needs `nullable=False` on its Arrow field.
- **Use the column's type**, from the SDK's Delta-to-Arrow table:

| Delta type | Arrow type | pyarrow |
|------------|------------|---------|
| `TINYINT` / `BYTE` | `Int8` | `pa.int8()` |
| `SMALLINT` / `SHORT` | `Int16` | `pa.int16()` |
| `INT` | `Int32` | `pa.int32()` |
| `BIGINT` / `LONG` | `Int64` | `pa.int64()` |
| `FLOAT` | `Float32` | `pa.float32()` |
| `DOUBLE` | `Float64` | `pa.float64()` |
| `STRING` / `VARCHAR` | `LargeUtf8` (not `Utf8`) | `pa.large_string()` |
| `BOOLEAN` | `Boolean` | `pa.bool_()` |
| `BINARY` | `LargeBinary` | `pa.large_binary()` |
| `DECIMAL` | `LargeUtf8`: **encoded as text**, for example `"19.99"` | `pa.large_string()` |
| `DATE` | `Date32` | `pa.date32()` |
| `TIMESTAMP` | `Timestamp(Microsecond, UTC)` | `pa.timestamp("us", tz="UTC")` |
| `TIMESTAMP_NTZ` | `Timestamp(Microsecond)`, no time zone | `pa.timestamp("us")` |
| `ARRAY<type>` | `List` (item field `item`) | `pa.list_(...)` |
| `MAP<key, value>` | `Map` (entries field `entries` with `keys` and `values`) | `pa.map_(...)` |
| `STRUCT<fields>` | nested struct | `pa.struct([...])` |
| `VARIANT` | struct of non-null `metadata` and `value`, both `LargeBinary` | see "VARIANT columns" |
- **`VARIANT` columns:** Arrow has no `VARIANT` type. Send the column as a **struct of two non-nullable `large_binary` fields, `metadata` and `value`** (the Variant binary encoding). The docs show this in Rust (`VariantBuilder`); see "VARIANT columns" below.

**Verify:** `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>`, then compare names, order, nullability, and types with your `pyarrow.Schema`. **Expected:** they line up. Casting to the schema (below) also fails fast, on the client, when a `NOT NULL` column has nulls.

## Step 2: Write a producer (Python)
Install the SDK with the Arrow extra:
```bash
pip install "databricks-zerobus-ingest-sdk[arrow]"
```

**Stream Parquet files or DataFrames:** Read each file's record batches (or convert a DataFrame), cast to the table schema, and queue without waiting. Flush per file to get durability boundaries for checkpointing:
```python
import os, sys
import pyarrow as pa, pyarrow.parquet as pq
from zerobus.sdk.shared.arrow import ArrowStreamConfigurationOptions, IPCCompression
from zerobus.sdk.sync import ZerobusSdk

SCHEMA = pa.schema([pa.field("device_name", pa.large_utf8()), pa.field("temp", pa.int32())])
sdk = ZerobusSdk(os.environ["ZEROBUS_SERVER_ENDPOINT"], os.environ["DATABRICKS_WORKSPACE_URL"])
stream = sdk.create_arrow_stream(
    os.environ["ZEROBUS_TABLE_NAME"], SCHEMA,
    os.environ["DATABRICKS_CLIENT_ID"], os.environ["DATABRICKS_CLIENT_SECRET"],
    options=ArrowStreamConfigurationOptions(ipc_compression=IPCCompression.ZSTD)
)
parquet_paths = sys.argv[1:]  # Parquet files to send
try:
    for path in parquet_paths:
        for batch in pq.ParquetFile(path).iter_batches(columns=SCHEMA.names):
            table = pa.Table.from_batches([batch]).select(SCHEMA.names).cast(SCHEMA)
            stream.ingest_batch(table)  # queues; returns immediately
        stream.flush()  # durability boundary: all batches from this file are durable
finally:
    stream.close()
```

**From DataFrames:** Convert with `pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)` (pandas) or `polars_df.to_arrow().select(...).cast(SCHEMA)` (Polars), then `stream.ingest_batch(table)`.

**Tuning:** Run parallel streams or producers to scale throughput. Flush at durability boundaries (per file, per time interval). No per-record waits.

**Verify:** `SELECT count(*) FROM <table>` ~5 seconds after `flush()` should match what you sent.

## Step 3: Tune
| Setting | Guidance |
|---------|----------|
| **Reuse stream** | Keep one open for many batches; opening has overhead |
| **Batch size** | Send application-sized batches (row groups, intervals). One row per call loses Arrow's advantage |
| **IPC compression** | Default none. `ZSTD` = best ratio; `LZ4_FRAME` = CPU-constrained. Cuts bytes on wire |
| **Durability boundaries** | `flush()` at checkpoints (file end, time interval), not per batch |
| **In-flight limit** | `max_inflight_batches` (default 1,000) bounds memory |

`ArrowStreamConfigurationOptions` defaults: `max_inflight_batches=1000`, `recovery=True`, `flush_timeout_ms=300000`.

## Other languages
| SDK | Stream and ingest | Notes |
|-----|-------------------|-------|
| **Rust** | `sdk.stream_builder().table(t).oauth(id, secret).arrow(schema).build_arrow().await?.ingest_batch(batch).await?.flush().await?.close()` | Compression: `.ipc_compression(Some(...ZSTD))` |
| **Java** | `sdk.streamBuilder().table(t).oauth(id, secret).arrow(schema).build().join()` then `ingestBatch(VectorSchemaRoot)` | `.maxInflightBatches(...)`, `.ipcCompression(...)` after `.arrow(...)` |
| **Go** (cgo) | `sdk.CreateArrowStream(table, schemaIPC, id, secret, opts)` then `stream.IngestBatch(batchIPC)` | `schemaIPC` = IPC with schema only; each batch = one RecordBatch |
| **C++** | `sdk.create_arrow_stream(table, schema_ipc, id, secret)` then `stream.ingest_batch(batch_ipc)`, `flush()`, `close()` | Each batch is a self-contained IPC (schema + one batch) |
| **TypeScript** | `stream.ingestBatch(Buffer.from(tableToIPC(table, 'stream')))` | See `typescript/examples/arrow` in SDK repo |

## VARIANT columns
Build as a struct of two non-nullable `large_binary` fields: `metadata` and `value` (Variant binary encoding). See the SDK repo's Rust example with `VariantBuilder`. For JSON payloads, a **JSON stream** is simpler (pass `VARIANT` as JSON string).

## Errors and recovery
Arrow uses gRPC error categories like other Zerobus streams. With recovery on (default), the SDK reconnects and replays unacknowledged batches on transient failures. If exhausted, close the stream and collect unacked batches with `stream.get_unacked_batches()` (persist or replay them per your policy).

| Symptom | Fix |
|---------|-----|
| Schema rejected | Rebuild schema from table; use `.select(...).cast(SCHEMA)` |
| `ValueError` from `cast` | Fix nulls in `NOT NULL` columns or make column nullable |
| Batch too large | One **row** exceeds 10 MB (not batch size) → shrink row |
| `ImportError` for `pyarrow` | `pip install "databricks-zerobus-ingest-sdk[arrow]"` |

## Sources
- [Use Arrow Flight with Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-arrow-flight)
- [Zerobus message types: Apache Arrow](https://docs.databricks.com/ingestion/zerobus-message-types)
- [Zerobus message blocking: Arrow Flight batches](https://docs.databricks.com/ingestion/zerobus-message-blocking) and [callbacks](https://docs.databricks.com/ingestion/zerobus-callbacks) (no callbacks on Arrow streams)
- [Zerobus release stages](https://docs.databricks.com/ingestion/zerobus-release-stages) (Apache Arrow format GA)
- SDK READMEs: [python](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md), [rust](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md) (`ArrowStreamConfigurationOptions`, Arrow Flight lifecycle), [java](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md), [go](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md), [cpp](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/cpp/README.md), [typescript](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/typescript/README.md)
- Python SDK 1.9.0 type stubs (`zerobus/_zerobus_core.pyi`) and `zerobus/sdk/sync/zerobus_sdk.py` for option defaults and `get_unacked_batches()` return type
