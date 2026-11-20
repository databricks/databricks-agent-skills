# Real-Time Mode (SDP)

Real-Time Mode (RTM) gives SDP pipelines ultra-low (sub-second, as low as a few ms) end-to-end
latency for operational workloads (fraud detection, real-time personalization). Recommend it only for operational
sub-second needs — for analytics or anything tolerant of seconds-to-minutes latency, use standard
continuous or triggered execution instead.

Runs on **classic compute or serverless**. **Recommend serverless** — it is the recommended path for
SDP RTM and manages task-slot provisioning for you (see Compute sizing for the classic-compute case).

An RTM pipeline runs continuously, so its compute never scales to zero, which makes it much more
expensive than a triggered pipeline. Confirm the user has a real sub-second SLA and accepts always-on
compute before recommending it.

| | SDP real-time mode (this file) | Standalone Structured Streaming real-time mode |
|---|---|---|
| Authoring | `dp.create_sink` + `@dp.update_flow` | `writeStream…trigger(realTime=…)` |
| Lifecycle | Managed by the pipeline (orchestration, checkpoints, retries, state) | You manage the query |
| Compute | Serverless or classic | Classic only |
| Sinks | Kafka | Kafka, custom `foreach`, Lakebase (Public Preview) |

For standalone real-time mode, see the `databricks-spark-structured-streaming` skill's
[real-time-mode.md](../../databricks-spark-structured-streaming/references/real-time-mode.md).

## Source of truth

The **public Databricks documentation is authoritative** for RTM, and **if anything here conflicts
with the docs, follow the docs.** This reference is the curated layer of non-obvious engine behavior,
constraints, and templates; the docs are the system of record. Before recommending an approach or
asserting a fact — especially **supported compute types, DBR versions, supported sources/sinks,
trigger syntax, output modes, or preview status** — verify it by searching the documentation (for example with the `databricks-docs` skill)
and treat the docs as authoritative over anything cached here. This content can lag. Budget: at most **3 documentation searches** per request; if the search returns
nothing relevant, fall back to the guidance here and say so. The canonical page is
`docs.databricks.com/.../ldp/real-time` ("Use real-time mode in Lakeflow pipelines").

## Enabling RTM (three steps)

RTM is a specialized continuous trigger, so the pipeline must run in **continuous mode** first.

1. **Continuous mode** — give the pipeline a **continuous schedule**; do NOT set `"continuous": true`
   in pipeline settings. Read [continuous-pipeline](continuous-pipeline.md) for how to create one. An
   existing pipeline already on the legacy `"continuous": true` spec is fine to leave as-is for RTM —
   only migrate it to a schedule if the user asks.
2. **Cluster switch** — `spark.databricks.streaming.realTimeMode.enabled=true` in the pipeline Spark
   config (the `configuration` map in the pipeline settings). Required; without it the flow
   fails to start.
3. **Real-time update flow** — define a sink with `dp.create_sink(...)`, then an `@dp.update_flow`
   whose `spark_conf` sets `pipelines.trigger` to `"RealTime"` and whose `target` is the sink.

The pipeline spec stays `continuous: false`; only the cluster conf goes in pipeline settings:

```json
{ "configuration": { "spark.databricks.streaming.realTimeMode.enabled": "true" } }
```

The flow-level trigger conf is `pipelines.trigger` (`"RealTime"`); optional `pipelines.trigger.interval`
is the checkpoint interval (default `"5 minutes"`). RTM is **Python-only** in SDP (uses `create_sink` /
`update_flow`); there is no SQL form.

`target=` is the **name of a sink**, not a Kafka topic: every `@dp.update_flow(target="X")` needs a
`dp.create_sink("X", ...)`, and the Kafka connection lives in the sink options. `create_sink` also accepts
`delta`, but Delta is not a real-time sink, so RTM flows use `format="kafka"`.

In RTM the batch is long-running and records are processed as they arrive, so
`pipelines.trigger.interval` sets how often state and source offsets are checkpointed, not how often
results appear. Keep it at minutes: shorter intervals add checkpoint overhead, longer ones slow
recovery after a failure and delay metrics.

## Template: Kafka → Kafka

```python
from pyspark import pipelines as dp

dp.create_sink("kafka_output_sink", "kafka", {
    "kafka.bootstrap.servers": broker_address,
    "topic": output_topic,
})

@dp.update_flow(
    name="kafka_rtm_flow",
    target="kafka_output_sink",
    spark_conf={"pipelines.trigger": "RealTime", "pipelines.trigger.interval": "5 minutes"},
)
def kafka_rtm_flow():
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", broker_address)
        .option("subscribe", input_topic)
        .option("startingOffsets", "latest")
        .load()
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "timestamp")
    )
```

## Template: enrich with a broadcast (stream-static) join

Prefer a broadcast join against a small static table: broadcast is the supported stream-static join
shape, so wrap the static side in `broadcast()` and keep it small enough for memory. **Inner**
stream-stream joins are also supported (DBR 18 LTS and above, with additional Spark configuration listed
in the docs); non-inner (outer / semi / anti) stream-stream joins are not.

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import broadcast, expr

dp.create_sink("enriched_output_sink", "kafka", {
    "kafka.bootstrap.servers": broker_address, "topic": enriched_output_topic,
})

@dp.update_flow(name="enriched_events_flow", target="enriched_output_sink",
                spark_conf={"pipelines.trigger": "RealTime"})
def enriched_events():
    lookup = spark.read.table("catalog.schema.lookup_table")
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", broker_address).option("subscribe", input_topic).load()
        .withColumn("event_key", expr("CAST(value AS STRING)"))
        .join(broadcast(lookup), expr("event_key = lookup_key"))
        .select("event_key", "lookup_value", "timestamp")
    )
```

## Template: stateful aggregation

Set `spark.sql.shuffle.partitions` to match input partitioning (each shuffle partition is a required
task slot — see Compute sizing below).

```python
dp.create_sink("event_counts_sink", "kafka", {
    "kafka.bootstrap.servers": broker_address,
    "topic": output_topic,
})

@dp.update_flow(name="event_counts_flow", target="event_counts_sink",
                spark_conf={"pipelines.trigger": "RealTime", "spark.sql.shuffle.partitions": "8"})
def event_counts():
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", broker_address).option("subscribe", input_topic).load()
        .selectExpr("CAST(key AS STRING) AS event_type", "timestamp")
        .groupBy("event_type").count()
    )
```

For a Kafka sink the `value` column is mandatory (`key`, `partition`, `headers`, and `topic` are optional) — serialize with `to_json(struct(*)) AS value`
(see the sink reference).

`spark.sql.shuffle.partitions` defaults to `200`, which a stateful stage (aggregation, `dropDuplicates`)
turns into 200 concurrently scheduled tasks. Set it low, matched to the stage's real parallelism, in the
flow's `spark_conf`, on serverless too.

## SDP-specific constraints

- **Streaming flows only.** A batch flow in RTM fails analysis ("real-time mode is only supported for
  streaming queries"). Use a streaming read.
- **No Auto CDC / `apply_changes` (DLT change) flows** in RTM — they are rejected.
- **No `forEach` / ForeachWriter.** SDP exposes only `create_sink` (format-based) and
  `foreach_batch_sink`; there is no way to supply a raw `ForeachWriter`. (Plain Structured Streaming
  supports `forEach`; SDP does not.)
- **Supported sources/sinks:** Kafka (source + sink), AWS MSK and Event Hubs via the Kafka connector,
  Kinesis as a source (prefer EFO mode; polling mode needs DBR 19+). Delta is supported as neither source
  nor sink, and file-based sources (Auto Loader, direct file reads) are not supported.
- **Lakebase (`postgresql`) sink is NOT available in SDP RTM.** The Lakebase streaming sink requires
  plain Structured Streaming (notebooks/jobs); per its docs, Lakeflow Spark Declarative Pipelines is
  not a supported environment. To stream into Lakebase with sub-second latency, use a Structured
  Streaming query with `format("postgresql")` instead of an SDP pipeline. To serve an app from Lakebase
  without sub-second latency, use the `databricks-lakebase` skill (for example synced tables).
- One real-time flow per pipeline is recommended; multiple flows contend for task slots. Keep
  micro-batch flows out of an RTM pipeline for the same reason. Multiple real-time flows without
  task-slot contention are in Beta, on serverless pipelines on the preview channel.
- **`transformWithState`** is supported, but `handleInputRows` runs once per row (not once per key per
  batch) and event-time timers are not supported; use processing-time timers.
- **Benchmarking without a destination:** `dp.create_sink(name="bench_sink", format="noop", options={})`
  discards output. `noop` is not a documented `create_sink` format, so use it only for testing.

## Creating and debugging an RTM pipeline

- **Create:** start from a continuous pipeline (one with a continuous schedule), set the cluster conf, and add the real-time update
  flow (the three steps above). Lead with the Kafka→Kafka template and adapt.
- **Debug:** RTM flows surface failures in the pipeline **event log** and the update's error summary.
  Map the error class to its fix — most RTM failures are `OPERATOR_OR_SINK_NOT_IN_ALLOWLIST`,
  `MULTIPLE_SHUFFLES_NOT_SUPPORTED`, `CONCURRENT_SCHEDULER_INSUFFICIENT_SLOT`, `OUTPUT_MODE_NOT_SUPPORTED`, or
  `CHECKPOINT_FORMAT_V1_NOT_SUPPORTED` (see "Shared RTM execution constraints" below and the
  monitoring `latencies` metrics). Before a full run, validate the flow is streaming-only and free of
  unsupported operators (no Auto CDC, no `foreachBatch`, no extra shuffle between a watermark and a stateful operator).

## Shared RTM execution constraints (apply to every RTM flow)

- **Update output mode only** (`OUTPUT_MODE_NOT_SUPPORTED` otherwise).
- **At-least-once sinks only** — a sink that advertises exactly-once is rejected
  (`EXACTLY_ONCE_SINK_NOT_SUPPORTED`). Set the sink option `mode` to `atLeastOnce` (in SDP, add
  `"mode": "atLeastOnce"` to the `dp.create_sink(...)` options) and make downstream consumers
  idempotent (dedupe on a business key) — records can be re-delivered on recovery.
- **Shuffle limits with watermarks.** A flow can have several shuffle stages. The limits apply to flows
  that use `withWatermark` while real-time watermark propagation is on: no shuffle before
  `withWatermark` (`STREAMING_REAL_TIME_WATERMARK_PROPAGATION.SHUFFLE_NOT_SUPPORTED_BEFORE_WATERMARK`),
  and at most one shuffle between a stateful operator and the closest `withWatermark` or stateful
  operator before it (`STREAMING_REAL_TIME_WATERMARK_PROPAGATION.MULTIPLE_SHUFFLES_NOT_SUPPORTED`). Remove
  extra `repartition` calls to stay within it. Every shuffle also adds task slots (see Compute sizing).
- **No** session windows, `mapPartitions`/`mapInPandas`/`mapInArrow`,
  `applyInPandasWithState`/`flatMapGroupsWithState`, or `transformWithStateInPandas`. Supported:
  tumbling/sliding windows, `dropDuplicates` **and `dropDuplicatesWithinWatermark`**, broadcast joins,
  inner stream-stream joins, row-based `transformWithState`.
- **Checkpoint v2 required** — start from a fresh checkpoint when adopting RTM
  (`CHECKPOINT_FORMAT_V1_NOT_SUPPORTED`).
- **Unsupported operator/sink** → `OPERATOR_OR_SINK_NOT_IN_ALLOWLIST` / `SINK_NOT_SUPPORTED`; restructure
  to a supported equivalent.

## Compute sizing on classic compute (the #1 operational failure there)

On **serverless** (the recommended path), slot provisioning is managed — you do not size task slots
by hand. This section applies to **classic compute**.

RTM schedules all stages simultaneously, so classic compute must have enough task slots for **every
stage's tasks at once** — otherwise `CONCURRENT_SCHEDULER_INSUFFICIENT_SLOT` (an engine-level error
not in the public `STREAMING_REAL_TIME_MODE.*` catalog). Required slots = sum of task counts across
stages (e.g. Kafka source `maxPartitions`=8 + one shuffle of 20 → 28 slots; add a second shuffle of
20 → 48). Aim for ~50% utilization (tasks idle waiting for data), tune `maxPartitions` and
`spark.sql.shuffle.partitions` to the minimum that avoids backlog, and minimize shuffles. `maxPartitions`
caps the Kafka source's tasks (unset = one per topic partition). Size the cluster to fixed capacity with
autoscaling off, and leave Photon off: RTM does not use it, so it only adds cost.

## Monitoring

RTM latency appears in `StreamingQueryProgress` under the `latencies` field (`processingLatencyMs` /
`sourceQueuingLatencyMs` / `e2eLatencyMs`, as P0/P50/P90/P95/P99); watch p99, not the average. For UDF-heavy flows, set
`spark.sql.execution.arrow.maxRecordsPerBatch=1` for scalar/Arrow UDFs (100+ for pandas).
