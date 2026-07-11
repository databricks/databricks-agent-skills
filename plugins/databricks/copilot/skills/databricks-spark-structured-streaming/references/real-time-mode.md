---
name: real-time-mode
description: Real-Time Mode (RTM) for Spark Structured Streaming on Databricks — sub-second end-to-end latency. Use when building realtime apps, kafka→kafka pipelines, low-latency operational pipelines, or any streaming workload with SLAs measured in milliseconds rather than seconds.
---

# Real-Time Mode (RTM)

RTM is a Structured Streaming execution mode that processes records continuously instead of in micro-batches. It is the only Spark Streaming surface that achieves sub-second end-to-end latency (as low as 5 ms).

**When to reach for RTM.** RTM requires a continuously running Classic cluster — autoscaling and spot are disabled (see [Cluster setup](#cluster-setup) below) and there is no scale-to-zero mode. That makes it materially more expensive than `processingTime` micro-batch or `availableNow` scheduled runs. For demos, prototypes, or workloads without a real sub-second SLA, don't default to RTM. Validate with the user before recommending it, and make sure they know the compute will be up 24/7.

For broader streaming topics (checkpoints, watermarks, micro-batch tuning), see the other references in this skill. This file covers only what is RTM-specific.

## Cluster setup

RTM has hard cluster requirements. Get any of these wrong and the stream either won't start or won't be low-latency.

| Setting | Required value | Notes |
|---|---|---|
| DBR | **16.4 LTS minimum, 18.1+ recommended** | Per the [GA blog](https://www.databricks.com/blog/announcing-general-availability-real-time-mode-apache-spark-structured-streaming-databricks): "we recommend DBR 18.1 for the latest features and optimizations." DBR 18+ is also required for stream-stream inner join (see [Supported operations](#supported-operations)) and DBR 18.2+ resolves a known latency floor with Python `transformWithState` at <5 rec/sec. |
| Compute type | **Classic compute** (Dedicated or Standard access mode) | Standard supports Python only. Serverless is NOT supported for standalone RTM — only inside SDP-on-RTM (see [sdp-real-time-mode.md](sdp-real-time-mode.md)). |
| Autoscaling | **Off** | Streaming clusters must be fixed-size. |
| Photon | **Off** | Incompatible with RTM. |
| Spot instances | **Off** | Interruptions break the stream. |
| Spark conf | `spark.databricks.streaming.realTimeMode.enabled = true` | Required to enable RTM at all. Set in cluster Advanced Options → Spark config. |

For latency-sensitive Python UDFs, use **Dedicated** access mode — Standard's security isolation adds overhead.

## Trigger and output mode

**Python:**
```python
.trigger(realTime="5 minutes")
.outputMode("update")
```

**Scala:**
```scala
import org.apache.spark.sql.execution.streaming.RealTimeTrigger
import org.apache.spark.sql.streaming.OutputMode

.trigger(RealTimeTrigger.apply("5 minutes"))
.outputMode(OutputMode.Update())
```

Two things people get wrong:

1. **The `"5 minutes"` is the long-running batch duration** (sometimes called the checkpoint interval) — not a "fire every 5 minutes" trigger. RTM is continuous; the duration controls how often the engine pauses to checkpoint between long-running batches. Set it to **at least 5 minutes in production** — shorter intervals cause frequent multi-second pauses; longer intervals mean more potential reprocessing on restart. Inter-batch time should stay ≤3 seconds (≤1% of the batch duration) or P99 latency rises. For development or debugging, dropping to 1 minute is fine if you want to see metrics emit more frequently.
2. **Output mode must be `update`.** RTM does not support `append` or `complete`.

## Slot math

RTM runs **all pipeline stages simultaneously** (unlike micro-batch, which can reuse slots stage by stage). The cluster's **total worker vCPUs must be ≥ the sum of partitions across every stage** — slots and CPU cores are equivalent for RTM sizing.

| Pipeline shape | Slots / vCPUs needed |
|---|---|
| Stateless: Kafka source (`maxPartitions=8`) → Kafka sink | 8 |
| + one shuffle (group by, dedup) with `spark.sql.shuffle.partitions=20` | 8 + 20 = 28 |
| + one explicit `.repartition(20)` | 8 + 20 + 20 = 48 |

If `maxPartitions` is unset, the source partition count equals the Kafka topic's partition count. If under-sized, the query throws an insufficient-task-slots error at start and stalls or fails.

## Supported sources and sinks

| Source / sink | As source | As sink |
|---|---|---|
| Kafka | ✓ | ✓ |
| Event Hubs (via Kafka connector) | ✓ | ✓ |
| Kinesis (EFO mode only) | ✓ | ✗ |
| AWS MSK | ✓ | ✗ |
| Rate (demos) | ✓ | N/A |
| Delta | ✗ | ✗ |
| Auto Loader / `cloudFiles` | ✗ | N/A |
| Files / object storage directly | ✗ | N/A |
| Google Pub/Sub | ✗ | ✗ |
| Apache Pulsar | ✗ | ✗ |
| Custom sink via `foreach` (Python class or Scala `ForeachWriter`) | N/A | ✓ |
| `foreachBatch` | N/A | ✗ |

**File-based sources (Auto Loader, direct file reads, Delta) are NOT supported in RTM.** They belong to micro-batch streaming. If your data lives in files and you need sub-second latency, ingest into Kafka / Event Hubs first.

For writing into Lakebase Postgres, see [lakebase-sink-python.md](lakebase-sink-python.md). That file covers both the native `format("postgresql")` sink (Public Preview, preferred when available) and a manual `foreach` sink as a fallback (which also serves as a worked example of the per-partition `foreach` lifecycle for sinks to non-Lakebase targets like Redis or Cassandra).

## Supported operations

### Stateless (lower cost, lower latency)

- Projections (`select`, `withColumn`), filters
- `union` of multiple streams
- **`repartition(N)`** — requires `spark.conf.set("spark.sql.execution.sortBeforeRepartition", "false")` set first; without it, repartition inserts a sort that destroys low-latency behavior with no warning.
- **Stream-static join** — broadcast-only. Wrap the static side in `broadcast(spark.read...)` and ensure it fits in memory.

### Stateful (higher cost, requires more slots)

- `dropDuplicates` for deduplication (NOT `dropDuplicatesWithinWatermark` — see below)
- Tumbling and sliding windowed aggregations (watermark required for state cleanup)
- Simple aggregations: `groupBy(...).count()`, `sum`, `avg`, etc.
- **Stream-stream inner join** — supported on **DBR 18+** with five Spark configs (see [Stream-stream inner join](#stream-stream-inner-join-dbr-18) below).
- `transformWithState` for custom state (see below)

### Not supported in RTM

- Session windows
- **`dropDuplicatesWithinWatermark`** — blocked by `STREAMING_REAL_TIME_MODE.DROP_DUPLICATES_WITHIN_WATERMARK_NOT_SUPPORTED`. Use `dropDuplicates` instead. (Note: the [RTM reference matrix](https://docs.databricks.com/aws/en/structured-streaming/real-time/reference) lists it as supported, but the runtime error-class check is definitive.)
- **Outer / left-semi / left-anti stream-stream joins** — RTM stream-stream join is inner-only (`STREAMING_REAL_TIME_MODE.STREAM_STREAM_JOIN_NON_INNER_NOT_SUPPORTED`)
- `flatMapGroupsWithState` and `mapGroupsWithState` (older APIs)
- `foreachBatch` and `mapPartitions`
- `transformWithStateInPandas` — use the row-based Python API
- Output modes `append` and `complete`
- Event-time timers inside `transformWithState`
- Async progress tracking
- Checkpoint format v1
- Union with batch sources; union of two identical streaming sources

The full supported-/unsupported-features matrix lives at [RTM reference](https://docs.databricks.com/aws/en/structured-streaming/real-time/reference).

## Stream-stream inner join (DBR 18+)

Available on DBR 18 and above with multiple Spark configs set. **Only inner joins** are supported — outer/semi/anti throw `STREAMING_REAL_TIME_MODE.STREAM_STREAM_JOIN_NON_INNER_NOT_SUPPORTED`. Setup (from the [RTM setup doc](https://docs.databricks.com/aws/en/structured-streaming/real-time/setup)):

```python
spark.conf.set("spark.databricks.streaming.realTimeMode.streamStreamJoin.enabled", "true")
spark.conf.set("spark.sql.streaming.join.stateFormatVersion", "4")
spark.conf.set("spark.sql.streaming.join.stateFormatV4.enabled", "true")
spark.conf.set("spark.sql.streaming.stateStore.rocksdb.mergeOperatorVersion", "2")
spark.conf.set("spark.sql.streaming.realTimeMode.controlMessage.enabled", "true")
```

State format v4 is what enables non-blocking iteration over both sides — required because RTM continuously processes records and can't sit idle waiting on either side. The non-blocking-iteration requirement also surfaces as `STREAMING_REAL_TIME_MODE.STREAM_STREAM_JOIN_POLLING_REQUIRED` when a source can't satisfy it.

For broadcast stream-static joins (the long-standing RTM-compatible enrichment pattern, available on all RTM DBRs), see [stream-static-joins.md](stream-static-joins.md) — wrap the static side in `broadcast()`.

## `transformWithState` behavior change

`transformWithState` is also the main escape hatch for working around RTM's other restrictions — many things RTM doesn't support natively (event-time-window-like behavior, custom join logic, complex multi-row state transitions) can be implemented inside a stateful processor.

The single semantic difference to know:

**In RTM, `handleInputRows` is called once per row.** In micro-batch, it's called once per key per batch, with the iterator carrying all values for that key.

If you write a `StatefulProcessor` assuming "I get a batch of rows for one key," that logic breaks in RTM. Each row arrives separately.

Other RTM-specific rules:
- **Processing-time timers only.** Event-time timers are not supported.
- **No `transformWithStateInPandas`.** Use the row-based Python API.
- Timer firing is delayed by data arrival: a timer scheduled for 10:00:00 will not fire at 10:00:00 if no data arrives — it fires when the next row arrives. Termination paths fire pending timers before exit.
- DBR 18.1 and below show "up to a few hundred ms" latency with Python at <5 rec/sec. Use DBR 18.2 or later (or Scala) to avoid this.

## Verifying and observing RTM

### Confirm the query is actually in RTM

A common mistake is wiring up the trigger correctly but landing on a code path that silently runs in micro-batch (e.g. a source that doesn't yet support RTM). Confirm by inspecting the streaming query's physical plan — the leaf nodes should be `RealTimeStreamScan` (or `RealTimeScanExec`):

```
== Physical Plan ==
WriteToDataSourceV2
+- * Project
   +- RealTimeStreamScan ...
```

If you see `MicroBatchScan` instead, the query is not running in RTM — check that the source is supported and the cluster Spark conf is set.

### Built-in latency metrics

Every RTM batch emits three latency metrics in `StreamingQueryProgress` under the `latencies` field. Per-batch percentile distributions (P0, P50, P90, P95, P99):

| Metric | What it measures |
|---|---|
| `processingLatencyMs` | Read-to-write inside the query — how long the pipeline takes to process a record |
| `sourceQueuingLatencyMs` | Source-append-time (e.g. Kafka log append) to first read by the query. Captures inter-batch time, message-bus queuing, upstream batching. |
| `e2eLatencyMs` | Source-append-time to processed downstream. End-to-end. |

**Caveat: `e2eLatencyMs` does not currently include the sink write time.** If perceived latency is higher than `e2eLatencyMs` suggests, the gap is in the sink.

**Caveat: backlogs inflate `sourceQueuingLatencyMs` and `e2eLatencyMs`.** Both clocks start at source-append time (e.g. Kafka log-append). If a query starts against records that have been sitting in Kafka for hours, those metrics will report hours — even if the query itself is processing each new record in milliseconds. Wait for the backlog to drain before interpreting the steady-state numbers, or filter to recent records.

Read these metrics via a `StreamingQueryListener`, by inspecting `query.lastProgress`, or in the streaming dashboard UI (the same metrics surface there).

### Diagnose-by-metric

| Symptom | Likely cause | Where to look |
|---|---|---|
| High `processingLatencyMs` | Slow operator inside the query | Per-stage metrics (set `spark.databricks.streaming.execution.enableDebugMetrics = true`); CPU profile |
| High `sourceQueuingLatencyMs` | Inter-batch time too long, or upstream source latency | Inter-batch time in driver logs; Kafka `kafka.fetch.max.wait.ms` (default 500 ms — drop to 50 for low latency); upstream batching |
| `e2eLatencyMs` looks fine but the app feels slow | Sink write time (not in `e2eLatencyMs`) | Measure sink flush duration directly |
| Latency climbing over time | Memory pressure or GC growing | Executor stdout for Full GC events (long `user` CPU times); cluster restart as immediate mitigation |

## Delivery semantics

RTM preserves Structured Streaming's standard fault-tolerance guarantees:

- **Exactly-once within Spark.** Operators, state stores, and supported sinks are all exactly-once.
- **At-least-once for Kafka and `foreach` sinks.** Anywhere data leaves Spark via `foreach` (custom writers, side effects) or is written to Kafka, the same record may be delivered more than once on restart or task retry — Kafka writes aren't idempotent without producer-side guards, and `foreach`'s lifecycle has no exactly-once commit protocol. Design custom sinks to be idempotent. See the [Structured Streaming fault-tolerance guarantees](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html#fault-tolerance-semantics) for the full output-sink matrix.

## Common errors

The full RTM error-class catalog is documented at [STREAMING_REAL_TIME_MODE error class](https://docs.databricks.com/aws/en/error-messages/streaming-real-time-mode-error-class). The most common ones:

| Error class | Cause / fix |
|---|---|
| `STREAMING_REAL_TIME_MODE.OUTPUT_MODE_NOT_SUPPORTED` | RTM only supports `outputMode("update")`. Replace `append` or `complete`. |
| `STREAMING_REAL_TIME_MODE.OPERATOR_OR_SINK_NOT_IN_ALLOWLIST` | The query uses an operator or sink RTM doesn't support (e.g. `foreachBatch`, session windows). Refactor to a supported equivalent. |
| `STREAMING_REAL_TIME_MODE.INPUT_STREAM_NOT_SUPPORTED` | The source isn't supported in RTM (e.g. Delta, Auto Loader, Pub/Sub). No override — ingest via Kafka/Event Hubs/Kinesis-EFO. |
| `STREAMING_REAL_TIME_MODE.SINK_NOT_SUPPORTED` | The sink isn't supported. Use Kafka/Event Hubs/MSK or a custom `foreach`. |
| `STREAMING_REAL_TIME_MODE.EXACTLY_ONCE_SINK_NOT_SUPPORTED` | RTM is at-least-once at the sink boundary; the chosen sink advertises exactly-once. Pick an at-least-once-compatible sink. |
| `STREAMING_REAL_TIME_MODE.ARBITRARY_STATEFUL_OPERATIONS_NOT_SUPPORTED` | Used `flatMapGroupsWithState` / `mapGroupsWithState`. Migrate to `transformWithState`. |
| `STREAMING_REAL_TIME_MODE.STREAM_STREAM_JOIN_NON_INNER_NOT_SUPPORTED` | RTM stream-stream join is inner-only. Outer/semi/anti are not available; refactor to an inner join or move to micro-batch. |
| `STREAMING_REAL_TIME_MODE.STREAM_STREAM_JOIN_POLLING_REQUIRED` | A join input source doesn't support non-blocking iteration. See the join setup confs in [Stream-stream inner join](#stream-stream-inner-join-dbr-18). |
| `STREAMING_REAL_TIME_MODE.CHECKPOINT_FORMAT_V1_NOT_SUPPORTED` | The checkpoint location is in the legacy v1 format. Recreate the checkpoint (RTM uses v2+ only). |
| `STREAMING_REAL_TIME_MODE.SESSION_WINDOWS_NOT_SUPPORTED` | Session windows aren't supported. Use tumbling/sliding or `transformWithState`. |
| `STREAMING_REAL_TIME_MODE.BATCH_UNION_NOT_SUPPORTED` | Cannot union a streaming source with a batch DataFrame. |
| `STREAMING_REAL_TIME_MODE.IDENTICAL_SOURCES_IN_UNION_NOT_SUPPORTED` | Cannot union two identical streaming sources (e.g. same Kafka topic read twice). |
| `STREAMING_REAL_TIME_MODE.EVENT_TIME_BASED_TIMERS_IN_TRANSFORM_WITH_STATE_NOT_SUPPORTED` | Use processing-time timers only inside `transformWithState`. |
| `STREAMING_REAL_TIME_MODE.CLUSTER_CONFIGURATION_NOT_SUPPORTED` | Cluster setting is incompatible (e.g. Photon on, autoscaling on). Fix the offending setting (see [Cluster setup](#cluster-setup)). |
| `STREAMING_REAL_TIME_MODE.DROP_DUPLICATES_WITHIN_WATERMARK_NOT_SUPPORTED` | `dropDuplicatesWithinWatermark` is blocked in RTM. Use `dropDuplicates` instead. |
| Query fails at start: **insufficient task slots** (`CONCURRENT_SCHEDULER_INSUFFICIENT_SLOT`) | This class lives outside the curated `STREAMING_REAL_TIME_MODE.*` namespace in public docs. Cluster has fewer vCPUs than the pipeline's sum-of-partitions. Increase cluster size to match the [Slot math](#slot-math) above. |

## Worker memory and GC

RTM executors process data continuously; the driver is only active at batch boundaries. **GC pauses on executors disrupt processing and show up as latency spikes** — more so than driver-side GC. For stateful pipelines (`transformWithState`, `dropDuplicates`, in-stream aggregation), plan worker memory with headroom above the state store's working size. Watch executor GC logs in `stdout` — long Full GC events (multi-second `user` CPU times) indicate undersized memory.
