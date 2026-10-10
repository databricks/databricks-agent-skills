# Recovery and retry patterns

Read this when a stream has failed, when the user asks how retries and recovery work, or when they want **custom client-side recovery**. For most producers the answer is: **built-in recovery handles it; don't write a reconnect loop.** Everything after "Built-in recovery" is advanced.

## Built-in recovery (the default)
SDKs recover automatically from transient failures (timeouts, network breaks): reconnect and **replay unacknowledged records** (everything after the last committed offset). **OAuth tokens auto-refresh** during creation and recovery.

| Option (Python) | Default | Effect |
|-----------------|---------|--------|
| `recovery` | `True` | Auto-recovery enabled |
| `recovery_timeout_ms` | `15000` | Recovery operation timeout |
| `recovery_backoff_ms` | `2000` | Delay between attempts |
| `recovery_retries` | `4` | Max attempts |

For most workloads, defaults are fine. **Don't wrap ingest in a retry loop** while recovery is on; it duplicates work and adds duplicates. See [how-it-works.md](how-it-works.md#what-happens-on-a-disconnect) for the mechanism.

## Errors and retries
- **Transient errors** (network issues, temporary server errors) are retried automatically by built-in recovery.
- **Non-recoverable failures** (for example invalid credentials) surface as **`NonRetriableException`** (Python subclass of `ZerobusException`). Catch and decide: fix cause, recover on new stream, or stop.
- Other SDKs mark retryability: Rust `e.is_retryable()`, .NET `ZerobusException.IsRetryable`. See language reference.
- For **ack-level failures** without blocking, use the ack callback's `on_error` ([SKILL.md Step 4](../SKILL.md#step-4-build-the-producer)).

## Advanced: recover records after a permanent failure
When recovery is exhausted, the stream closes. Rescue unacknowledged records:
- `get_unacked_records()`: raw bytes (decode JSON/Protobuf)
- `get_unacked_batches()`: grouped as original batches
- `sdk.recreate_stream(stream)`: new stream with unacked records re-queued

**Key:** these calls succeed only after the stream closes (terminal failure). Enqueue failure leaves stream active; those calls fail.

Fragment (assumes the `sdk`, `stream`, and `records` from your producer; see [SKILL.md Step 4](../SKILL.md#step-4-build-the-producer)):
```python
from zerobus.sdk.shared import NonRetriableException, ZerobusException

try:
    for record in records:
        stream.ingest_record_offset(record)
    stream.flush()
except NonRetriableException:
    raise  # auth, grants, or schema: recreating the stream won't help
except ZerobusException:
    unacked = list(stream.get_unacked_records())  # raw bytes; persist them if you need your own copy
    print(f"{len(unacked)} records unacknowledged; recreating the stream")
    new_stream = sdk.recreate_stream(stream)  # new stream with the unacknowledged records re-queued
    try:
        new_stream.flush()
    finally:
        new_stream.close()
else:
    stream.close()
```
**Verify:** `new_stream.flush()` succeeds. **Expected:** rescued rows appear (possibly with duplicates).

**Optional:** persist unacked records to your own durable storage and replay later with same event keys for downstream dedup (see [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates)).

### Disabling built-in recovery (rare)
Set `recovery=False` only if you're implementing your own reconnect logic end to end; you then own reconnecting and replaying unacked records. Prefer the built-in path plus the rescue flow above.

## Handling duplicates on replay
At-least-once delivery: if a connection drops before an ack arrives, the SDK resends unacknowledged records, so a few duplicates are possible. For deduplication guidance and gotchas, see [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates).

## Flush vs close
- `flush()`: waits for server acks without closing the stream
- `close()`: flushes + closes gracefully (waits for pending acks before returning)
- `close()` is for shutdown, not recovery. On failure, rescue unacknowledged records instead.

## Advanced: recover data from the durable fallback location
If the table schema changes after Zerobus has made data durable but before it publishes to Delta, Zerobus writes that data as Parquet files to a fallback directory under your table's storage root: `_zerobus/table_rejected_parquets/`, relative to the table's root storage location. Records are not silently rejected; ingest errors surface as errors on the stream or in the ack callback.

### Step 1: Resolve the schema mismatch
Evolve the table schema so the fallback records fit ([schema-management.md](schema-management.md)).

### Step 2: Inspect the fallback data
```sql
SELECT * FROM parquet.`<table-storage-root>/_zerobus/table_rejected_parquets/` LIMIT 10;
```
**Expected:** the rejected records, with columns you can now map to the table.

### Step 3: Load it back
```sql
COPY INTO <catalog>.<schema>.<table>
FROM '<table-storage-root>/_zerobus/table_rejected_parquets/'
FILEFORMAT = PARQUET
COPY_OPTIONS ('mergeSchema' = 'false');  -- idempotent: re-running won't load the same files twice
```
**Verify:** the row count rises by the number of fallback records. Records that reached both the table and the fallback can load twice ([how-it-works.md](how-it-works.md#delivery-and-duplicates)). Clean up the fallback files once you've confirmed the data is in the table.

## Sources
- [Zerobus: Recovery and retry patterns](https://docs.databricks.com/ingestion/zerobus-recovery)
- [Zerobus: Asynchronous communication](https://docs.databricks.com/ingestion/zerobus-async-communication)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md) ("Handling Stream Failures", "Configuration")
- [Rust SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md), [.NET SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/dotnet/README.md) (retryable errors)
