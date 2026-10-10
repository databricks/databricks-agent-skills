# How Zerobus works

Read this to understand **what Zerobus is**, **how records travel from client to table**, **how the SDK processes them**, how **ordering and scaling** work, and how to handle **delivery guarantees**. For conceptual context before diving into a build, this pairs with [SKILL.md](../SKILL.md).

## Contents

- [What Zerobus is](#what-zerobus-is)
- [The data path](#the-data-path)
- [How the SDK processes records](#how-the-sdk-processes-records)
- [Ordering](#ordering)
- [Delivery and duplicates](#delivery-and-duplicates)
- [Scaling](#scaling)
- [Common questions](#common-questions)
- [Sources](#sources)

## What Zerobus is

Zerobus is a push-based API that handles the entire pipeline: a producer sends records via a supported protocol (SDK, REST, OTLP, Kafka-compatible, MQTT, or Arrow Flight), **Zerobus buffers and acknowledges receipt** (durability confirmation), and then **materializes the records into your Delta table** (queryable).

The producer keeps its network connection to Zerobus open. Databricks never reaches out to the producer network. This is a push model, not pull.

### Streams

A **stream** is a logical connection from your producer to a specific Zerobus table. You can open multiple streams in parallel to increase throughput.

- Each stream gets its own network connection.
- Each stream has its own ordering scope (records on one stream are ordered; records across streams are not).
- Each stream counts against the per-stream quotas ([performance.md](performance.md#quotas)).
- Use multiple streams to reach higher overall throughput (up to 10 GB/s per table).

### Client vs server responsibilities

Zerobus is not just an API wrapper. The SDK and the service each do real work.

| Who | Handles |
|-----|---------|
| **SDK (client library)** | OAuth token acquisition and refresh; an in-memory queue of in-flight records; sending records over a long-lived stream; tracking offsets and acknowledgments in the background; invoking **ack callbacks** (where the language supports them); **automatic recovery** (reconnect and replay unacknowledged records after transient failures) |
| **Your code** | Building records that match the table schema; ingesting **without blocking**; reacting to acks and errors in callbacks; choosing durability boundaries (`flush` at the end of a batch or before shutdown); choosing how many streams to open |
| **Zerobus service** | Authorization against Unity Catalog; validating records against the table schema; storing records durably and acknowledging them; materializing data into the Delta table; enforcing per-stream and per-table quotas. If data can't be written to the table (for example after a schema mismatch), Zerobus keeps it in durable storage for up to 28 days |

## The data path

**Producer → Zerobus service → write-ahead log (durable; ack sent in about 150 ms) → Parquet batch commit (about 4 to 5 seconds) → Delta table (queryable in about 5 seconds).**

A record travels in two legs, and **all of it is asynchronous**: the producer keeps sending while acks come back, and it never waits on the table write. The Zerobus docs have diagrams of this flow; share these links when you explain it:
- [How Zerobus Ingest works](https://docs.databricks.com/ingestion/zerobus-overview#how-it-works): the end-to-end flow from producer to Delta table
- [Asynchronous communication](https://docs.databricks.com/ingestion/zerobus-async-communication): the client and server exchange in the async ack loop

### Leg 1: client to durable (the async ack loop)

The client and server share one bidirectional gRPC stream with two independent directions: one line for sending messages, the other for receiving offset acknowledgments. Sending never waits for an ack.

| Step | Client (SDK) | Server (Zerobus) |
|------|-----|---------|
| **1. Push** | `ingest_record_offset()` assigns the next logical offset, adds the record to the in-flight buffer, and returns immediately | |
| **2. Send** | Sends buffered records over the stream in the background | Receives records, decodes them, and validates them against the table schema |
| **3. Make durable** | | Buffers incoming records and writes them to a latency-optimized write-ahead log (WAL) in small batches |
| **4. Ack** | | Sends back the **highest offset that is durable**. One ack is cumulative: it confirms that record and every earlier one. No per-record ack |
| **5. Purge** | Purges buffered records up to that offset; fires the **ack callback** if one is registered; completes any `flush()` or `wait_for_offset()` waiting on those offsets | |

The loop repeats for the life of the stream. **Client to durable takes about 150 ms.** The SDKs run the loop for you; client-side details (offsets, buffer limits, backpressure, callbacks) are below.

### Leg 2: durable to the Delta table (batch commit)

| Step | What happens |
|------|--------------|
| **1. Collect** | Zerobus collects durable records over about **4 to 5 seconds** |
| **2. Write** | It writes the batch as **Parquet files** using Delta Kernel Rust |
| **3. Commit** | It commits the files to the Delta table as one batch. The rows are now **queryable**, about **5 seconds** after they were sent |

**An ack means durable, not queryable.** An acked record can still be in Leg 2, so allow about 5 seconds before querying for it. If durable data can't be written after a schema change, Zerobus puts it in a durable fallback location instead (see [recovery.md](recovery.md)).

### Timeline (typical in-region; times vary with region and workload)

- **12:00:00.000**: The producer sends the record. `ingest_record_offset()` queues it and returns immediately.
- **12:00:00.150**: Zerobus acknowledges it: the record is **durable** in the write-ahead log (about 150 ms after sending).
- **12:00:00.150 to 12:00:05.000**: Zerobus collects durable records and commits them to the Delta table as a batch of Parquet files.
- **12:00:05.000**: The record is **queryable** in the table (about 5 seconds after sending).

**Never rely on an ack as proof the record is in the table. Always query the table to verify.**

## How the SDK processes records

### In-flight buffer and offsets

Each ingest call queues the record in a **local in-flight buffer** (the client's queue) and gets a **logical offset**. The server persists records durably and periodically reports the **highest committed offset**. The client then drops everything up to that offset from the buffer.

### Backpressure

The in-flight buffer is bounded by a configurable in-flight record limit. **Ingestion is asynchronous until the buffer fills; at that point, ingest calls block until acknowledgments arrive and free up space.**

- That's the only time a normal ingest call blocks. It's backpressure: the producer is sending faster than acks are coming back.
- If ingest calls stall, the buffer is full. Check the network path and the per-stream quota, then add streams ([performance.md](performance.md)). Don't add waits.
- In Python the limit is `max_inflight_records` (default **1,000,000**). Other SDKs expose an equivalent; check the language reference.

### Process model

| Aspect | What it means for the producer |
|--------|--------------------------------|
| **Where the work happens** | In your process. The **Rust SDK is the core**; the wrapper SDKs load it as a prebuilt native library: Python (PyO3), Java (JNI), TypeScript (NAPI), Go (cgo), .NET (P/Invoke), C++ (C FFI). The **pure SDKs** (Rust, pure Go, pure C) need no precompiled binaries |
| **Background work** | Sending, ack tracking, recovery, and callbacks run in the background (SDK threads or tasks). Your ingest calls only enqueue |
| **Memory** | The in-flight buffer holds every unacknowledged record **in memory**, up to the in-flight limit. Size the limit to your record size and the memory available, especially in containers |
| **Lifetime** | A stream is **long-lived**. Open it once and reuse it for the life of the process; don't open a stream per request or per record |
| **Shutdown** | Call `flush()` then `close()` (or just `close()`, which flushes) before the process exits, so buffered records become durable. Records still in the buffer when the process dies were never acknowledged |
| **Runtimes** | Servers, workers, containers, Databricks Jobs, Apps, and serverless compute (Python). Not edge runtimes that forbid native code; use REST there |

### Non-blocking ingestion

Ingest calls queue and return; acks arrive asynchronously. Which call to use for sending, acting on acks, durability boundaries, and the advanced blocking case, and which languages have an ack callback, is the **non-blocking ladder** in [SKILL.md Step 4](../SKILL.md#step-4-build-the-producer). Each SDK reference gives that language's method names.

### What happens on a disconnect

**Built-in recovery is the default.** If the connection is interrupted, records still in the in-flight buffer (those beyond the last committed offset) have not been confirmed durable, so they can be replayed. The SDK automatically reconnects and replays them, refreshing OAuth tokens as needed. You do not need to write retry loops.

Replays can write a record more than once ([Delivery and duplicates](#delivery-and-duplicates)). For permanent failures, rescuing unacknowledged records (`get_unacked_records`, `recreate_stream`), disabling built-in recovery, and reprocessing the durable fallback location, see [recovery.md](recovery.md).

## Ordering

**Ordering is per-stream only; there is no global ordering across streams.**

Records are committed to the table in the order they are enqueued **on a single stream**. If you use multiple streams, they commit independently with no guaranteed relative order.

**If you need one order across all records** (not just per key), include a timestamp or sequence number in each record and sort downstream; streams don't order relative to each other.

**To keep per-key order while scaling out:** send all records for a given key on the same stream, and use more streams for more keys. For example, if you have 100 devices, send each device's data to one stream. Open as many streams as your throughput requires, and always route the same device (key) to the same stream. This way the table preserves order within each device while the service scales across many streams.

**Example:**
```
Stream 1 (device A): Record 1 -> Record 2 -> Record 3
Stream 2 (device B): Record X -> Record Y -> Record Z

Table may contain: 1, 2, 3, X, Y, Z  OR  X, 1, Y, 2, Z, 3  OR any other interleaving of the two streams.
But within each stream, the order is preserved.
```

## Delivery and duplicates

**At-least-once delivery.** If a connection drops before an acknowledgment arrives, the SDK resends the unacknowledged records, so a few duplicate rows are possible. Most workloads accept that, so don't add deduplication by default, and never claim exactly-once. If the use case needs unique rows, keep the Zerobus table as the landing table and build a deduplicated table from it downstream with AUTO CDC in Lakeflow Spark Declarative Pipelines (see the `databricks-pipelines` skill).

For advanced custom recovery and fallback reprocessing, see [recovery.md](recovery.md).

## Scaling

### Stream-based autoscaling

Why it autoscales: ordering lives on the stream, not a partition.

- In a message bus, "partitions are the unit of both parallelism and ordering," so scaling means repartitioning.
- Zerobus "moved the ordering guarantee to the stream connection": **your stream is ordered, not your partition.** When a producer opens a stream it registers a logical identity, and for the lifetime of that connection, their data arrives in order, regardless of which pod processes it.
- **Hot routing:** If a pod is running hot, new incoming streams are routed to a different pod. Pods are added when demand spikes and removed when it drops; existing streams drain gracefully. Partition counts never need planning or shrinking.
- Autoscaling "responds to stream count and throughput." **Throughput scales with the number of concurrent open streams.**

**What this means for producers:**
- There are no partitions to size or rebalance.
- To go faster, **open more streams**: across processes or hosts, or several streams per producer.
- **Ordering is by stream ID and message offset.** Records on one stream are ordered by their offsets; there's no ordering across streams. To keep order for a key (device, tenant), send that key's records on **one stream**.

### Proven scale (NASA NEOWISE benchmark)

| Setup | Value |
|-------|-------|
| Dataset | NASA NEOWISE: 200 billion data points over 11 years; unique Parquet files per worker, no repeated rows |
| Producers | **2,048** Locust workers, **1 stream each** (2,048 concurrent streams), about 1 hour ramp-up |
| Format | Protocol Buffer 2 (binary) |
| Duration | About 24 hours sustained |
| **Throughput to one table** | **about 12 GB/s** sustained (11.8 GB/s wire format) |
| **Rows** | **12 million rows per second**; **1.04 trillion rows** total |
| **Volume** | **About 1 PB in 24 hours** |
| **Latency** | Stable for the whole run |

**Quota context:** the official default is **10 GB/s per table, adjustable** (see [performance.md#quotas](performance.md#quotas)). The benchmark shows what a table sustains at that scale; higher limits go through the account team.

## Common questions

| Question | Answer |
|----------|--------|
| "How does Zerobus scale?" | Stream-level ordering plus hot routing lets the service add and remove pods freely; throughput grows with concurrent streams |
| "Do I need to plan partitions?" | No. Zerobus is partitionless to producers; open more streams instead |
| "How fast can one table go?" | Databricks' benchmark sustained about **12 GB/s** to one table (2,048 streams, Protobuf). The default quota is **10 GB/s per table**, and it's adjustable: reach out to your Databricks account team if you need more |
| "Is order guaranteed?" | Per stream only, by stream ID and message offset; not across streams. To keep order for a key while scaling, send each key to the same stream |
| "What does durable mean?" | Durable = safely stored, not yet queryable. An ack means the record is in the write-ahead log and will not be lost. Rows appear in the table about 5 seconds later |
| "Should I replace my message bus?" | If your message bus is only a pipe to the lakehouse, yes; if many consumers depend on it, keep it |
| "Why can't I query a record right after its ack?" | The ack means durable. Zerobus commits to Delta in batches about every 4 to 5 seconds, so rows are queryable about 5 seconds after sending |

## Sources

- [Ingesting the Milky Way: Petabyte-scale with Zerobus Ingest](https://www.databricks.com/blog/ingesting-milky-way-petabyte-scale-zerobus-ingest) (Databricks blog)
- [Zerobus Ingest overview: How it works](https://docs.databricks.com/ingestion/zerobus-overview#how-it-works) (end-to-end diagram)
- [Zerobus: Asynchronous communication](https://docs.databricks.com/ingestion/zerobus-async-communication) (async ack loop diagram)
- [Zerobus Ingest quotas](https://docs.databricks.com/ingestion/zerobus-quotas)
- [Zerobus Deep Dives](https://docs.databricks.com/ingestion/zerobus-deep-dives)
