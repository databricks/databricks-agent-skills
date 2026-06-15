---
name: real-time-mode
description: Real-Time Mode (RTM) for Spark Structured Streaming on Databricks — sub-second end-to-end latency. Use when building realtime apps, kafka→kafka pipelines, low-latency operational pipelines, or any streaming workload with SLAs measured in milliseconds rather than seconds.
---

# Real-Time Mode (RTM)

RTM is a Structured Streaming execution mode that processes records continuously instead of in micro-batches. It is the only Spark Streaming surface that achieves sub-second end-to-end latency (as low as 5 ms).

For broader streaming topics (checkpoints, watermarks, stream-stream joins, micro-batch tuning), see the other references in this skill. This file covers only what is RTM-specific.

## Cluster setup

RTM has hard cluster requirements. Get any of these wrong and the stream either won't start or won't be low-latency.

| Setting | Required value | Notes |
|---|---|---|
| DBR | **16.4 LTS minimum, 18.x recommended** | 18.2+ specifically resolves a known latency floor with Python `transformWithState` at <5 rec/sec. |
| Compute type | **Classic compute** (Dedicated or Standard access mode) | Standard supports Python only. Serverless is NOT supported. RTM also exists as a configuration mode inside Lakeflow Spark Declarative Pipelines, with a different authoring API — out of scope here. |
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

- `dropDuplicates` for deduplication
- Simple aggregations: `groupBy(...).count()`, `sum`, `avg`, etc.
- `transformWithState` for custom state (see below)

### Not supported in RTM

- Watermark-based windowed aggregations
- Stream-stream joins
- `flatMapGroupsWithState` (older API)
- `foreachBatch` and `mapPartitions`
- Output modes `append` and `complete`

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

Exact Spark error-class names may vary across DBR versions; check the message body and SQLSTATE for what actually fired.

| Symptom | Cause / fix |
|---|---|
| Query fails at start: insufficient task slots in the cluster | Cluster has fewer vCPUs than the pipeline's sum-of-partitions. Increase cluster size to match the slot-math table above. |
| Query fails: output mode not supported | RTM only supports `outputMode("update")`. Replace `append` or `complete`. |
| Query fails: operator or sink not in RTM allowlist | The query uses an operator or sink that RTM doesn't support (e.g. `foreachBatch`, watermarked windows, stream-stream join). Refactor to a supported equivalent. |
| Query fails: input stream not supported | The source isn't supported in RTM (e.g. Delta, Auto Loader, Pub/Sub). No override — ingest via Kafka/Event Hubs/Kinesis-EFO. |

## Worker memory and GC

RTM executors process data continuously; the driver is only active at batch boundaries. **GC pauses on executors disrupt processing and show up as latency spikes** — more so than driver-side GC. For stateful pipelines (`transformWithState`, `dropDuplicates`, in-stream aggregation), plan worker memory with headroom above the state store's working size. Watch executor GC logs in `stdout` — long Full GC events (multi-second `user` CPU times) indicate undersized memory.
