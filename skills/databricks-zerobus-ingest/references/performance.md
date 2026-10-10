# Performance and Optimization

Read this when the user needs **more throughput or lower latency**, hits a quota, or asks how to size streams and tables. Check that the producer is non-blocking first; most slow producers are waiting on acks.

## Batching and Throughput

The most important optimization: **batch ingest calls, then flush once**.

### Inefficient (Blocking per Record):

Fragment (don't do this):
```python
for record in records:
    offset = stream.ingest_record_offset(record)
    stream.wait_for_offset(offset)  # blocks on every record: one round trip per record
```

This pattern is very slow because it waits for acknowledgment after every single record.

### Efficient (Non-Blocking Batch):

Fragment (do this):
```python
for record in records:
    stream.ingest_record_offset(record)  # queues and returns
stream.flush()  # one durability boundary for the batch
```

Batching dramatically improves throughput by letting the SDK buffer and send records efficiently.

**Observe acknowledgments with an ack callback, not with waits.** A callback reports progress and errors without slowing the loop; `wait_for_offset()` and per-request `flush()` both block. See [how-it-works.md](how-it-works.md#how-the-sdk-processes-records).

**Throughput scales with concurrent streams.** Databricks sustained about 12 GB/s to one table with 2,048 streams of Protobuf records (see [how-it-works.md#scaling](how-it-works.md#scaling)).

## Multiple Streams

For even higher throughput, open multiple streams in parallel:

Fragment (assumes `sdk`, `client_id`, `client_secret`, `table_props`, and `records` from your producer):
```python
from concurrent.futures import ThreadPoolExecutor

def produce(batch):
    stream = sdk.create_stream(client_id, client_secret, table_props)  # one stream per worker
    try:
        for record in batch:
            stream.ingest_record_offset(record)
        stream.flush()
    finally:
        stream.close()

with ThreadPoolExecutor(max_workers=4) as pool:
    for i in range(4):
        pool.submit(produce, records[i::4])
```

Default quotas: each stream can handle up to 100 MB/s and 100,000 records/s, and a table up to 10 GB/s total. The per-table quota is adjustable; contact your Databricks account team for more.

## Table layout
- **Liquid clustering (recommended):** keep predictive optimization enabled (async clustering improves query performance)
- **Partitioned tables:** max **100 partitions per 5 seconds**; else switch to liquid clustering

```sql
ALTER TABLE <catalog.schema.table> CLUSTER BY (device_name, event_time);
```
**Verify:** `DESCRIBE DETAIL` shows `clusteringColumns`.

## Serialization format
| Format | Use |
|--------|-----|
| **Protobuf** | Production and high volume: compact, type-safe, the fastest record-by-record path ([protobuf-schema.md](protobuf-schema.md)) |
| **Arrow** (Arrow Flight) | Large columnar batches |
| **JSON** | Prototypes and low volume; convenient but slower |

## Stream configuration

Fragment (assumes `sdk`, `client_id`, `client_secret`, and `table_props` from your producer):
```python
from zerobus.sdk.shared import StreamConfigurationOptions

options = StreamConfigurationOptions(
    max_inflight_records=1_000_000,  # buffer size; ingest blocks when it's full
    recovery=True,                   # built-in reconnect and replay (the default)
)
stream = sdk.create_stream(client_id, client_secret, table_props, options)
```
**Format inference:** Protobuf descriptor means Protobuf; none means JSON; no `record_type` needed. **Tune `max_inflight_records`:** raise for higher throughput (if memory allows), lower in containers. Unacknowledged records stay in memory. See [how-it-works.md](how-it-works.md#how-the-sdk-processes-records) for all options.

## Quotas

All are **adjustable defaults**; to raise one, contact your Databricks account team.

| Scope | Default quota | Notes |
|-------|---------------|-------|
| **Per stream (gRPC)** | 100 MB/s and 100,000 records/s (benchmarked with 1 KB messages) | Open more streams to scale beyond this |
| **Per target table (gRPC)** | 10 GB/s | |
| **REST** | 10,000 requests/s | |
| **Kafka-compatible APIs (Beta)** | 50,000 messages/s **per workspace** | Higher Beta quotas on request |
| **Concurrent streams per workspace** | Unlimited | Opening more streams is the intended way to scale out |
| **Record size** | 10 MB (10,485,760 bytes) | |

For more details, see [Zerobus quotas and limits](https://docs.databricks.com/ingestion/zerobus-quotas).

## Common Issues

| Issue | Solution |
|-------|----------|
| **Throughput plateau at 100 MB/s** | Open more streams (per-stream quota) |
| **Memory growing** | Lower `max_inflight_records`; check acks keep up |
| **High latency** | Batch + flush once, not per-record waits |

## Sources

- [Zerobus Concepts](https://docs.databricks.com/ingestion/zerobus-concepts)
- [Zerobus Ingest Quotas](https://docs.databricks.com/ingestion/zerobus-quotas)
- [Delta Lake Liquid Clustering](https://docs.databricks.com/en/delta/liquid-clustering.html)
