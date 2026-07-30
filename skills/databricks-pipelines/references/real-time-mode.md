# Real-Time Mode (RTM) on Lakeflow Declarative Pipelines

RTM runs an SDP flow on a continuous engine instead of micro-batches, targeting end-to-end latency "as low as five milliseconds" ([Use real-time mode in SDP](https://docs.databricks.com/aws/en/ldp/real-time)). You keep the declarative `sinks + flows` authoring surface — no `writeStream`, no `awaitTermination`, no checkpoint paths — and the framework runs it continuously. **Public Preview.**

This file is SDP-specific. For standalone Structured Streaming RTM (`writeStream…trigger(realTime=…)` on classic compute) — including the shared error classes, cluster prohibitions, and observability internals — see [../databricks-spark-structured-streaming/references/real-time-mode.md](../../databricks-spark-structured-streaming/references/real-time-mode.md).

## When to reach for RTM

RTM pipelines run **continuously** (`continuous: true`) — the compute never scales to zero. That makes RTM materially more expensive than a triggered pipeline. Reach for it only for **operational use cases** with a real sub-second/low-hundreds-of-ms SLA (fraud scoring, live alerting, personalization). For demos, prototypes, or other use cases that tolerate seconds-to-minutes latency, use a normal triggered pipeline instead. Validate with the user before recommending RTM, and confirm they accept always-on compute. (This is the sanctioned exception to the general "avoid `continuous: true`" guidance in [pipeline-configuration.md](pipeline-configuration.md).)

## SDP-on-RTM vs standalone RTM

| | SDP-on-RTM (this file) | Standalone RTM (structured-streaming skill) |
|---|---|---|
| Authoring | `dp.create_sink` + `@dp.update_flow` | `writeStream…trigger(realTime=…)` |
| Lifecycle | Managed by the pipeline (orchestration, checkpoints, retries, state) | You manage the query |
| Compute | **Serverless or classic** | Classic only |
| Sinks | Kafka (Delta is not RTM-usable — see below) | Kafka + custom `foreach` + native Lakebase (Public Preview) |

## Enabling RTM

Three things together turn RTM on:

1. **Pipeline settings** — `continuous: true`, `serverless: true` (or classic), on the `PREVIEW` channel. Requires **Databricks Runtime 18.1.3** on the SDP preview channel ([docs](https://docs.databricks.com/aws/en/ldp/real-time)).
2. **Pipeline-level Spark conf** — `spark.databricks.streaming.realTimeMode.enabled: true`.
3. **Per-flow trigger** — `pipelines.trigger: "RealTime"` in the `@dp.update_flow` `spark_conf` (see the pattern below).

## The `dp.create_sink` + `@dp.update_flow` pattern

RTM delivers to an operational system rather than a table, so you write to an external **sink** and route a **flow** to it.

> **`target=` is a sink NAME, not a Kafka topic.** Per the [update_flow reference](https://docs.databricks.com/aws/en/ldp/developer/ldp-python-ref-update-flow), `target` is *"Required. The name of the sink this flow writes to."* Every `@dp.update_flow(target="X")` must be preceded by a `dp.create_sink("X", …)` that declares `X`. The Kafka connection lives in `create_sink`, not the decorator.

```python
from pyspark import pipelines as dp

# 1. Declare the sink. Its output DataFrame must have a `value` column;
#    `key`, `partition`, `headers`, `topic` are optional.
dp.create_sink(
    name="kafka_out_sink",
    format="kafka",
    options={
        "kafka.bootstrap.servers": "kafka-broker:9092",
        "topic": "rtm_output",
    },
)

# 2. Route a real-time flow to that sink NAME.
@dp.update_flow(
    name="kafka_rtm_flow",
    target="kafka_out_sink",                 # the sink declared above — NOT a topic
    spark_conf={
        "pipelines.trigger": "RealTime",     # turns RTM on for this flow
        "pipelines.trigger.interval": "5 minutes",
    },
)
def kafka_rtm_flow():
    return (
        spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", "kafka-broker:9092")
            .option("subscribe", "raw_events")
            .option("startingOffsets", "latest")
            .load()
            .selectExpr("CAST(key AS STRING) AS key",
                        "CAST(value AS STRING) AS value",
                        "timestamp")
    )
```

**Enrich with a broadcast stream-static join.** Broadcast is the only supported stream-static join shape in RTM; wrap the static side in `broadcast()` and keep it small enough to fit in memory:

```python
from pyspark.sql.functions import broadcast

dp.create_sink(
    name="enriched_events_sink",
    format="kafka",
    options={"kafka.bootstrap.servers": "kafka-broker:9092", "topic": "enriched_events"},
)

@dp.update_flow(
    name="enriched_events_flow",
    target="enriched_events_sink",
    spark_conf={"pipelines.trigger": "RealTime", "pipelines.trigger.interval": "5 minutes"},
)
def enriched_events_flow():
    events = (
        spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", "kafka-broker:9092")
            .option("subscribe", "raw_events")
            .load()
            .selectExpr("CAST(key AS STRING) AS user_id",
                        "CAST(value AS STRING) AS value",
                        "timestamp")
    )
    users = spark.read.table("main.dim.users")   # small static UC table, broadcast into the stream
    return (
        events.join(broadcast(users), "user_id", "left")
              .selectExpr("user_id AS key",
                          "to_json(struct(*)) AS value",
                          "timestamp")
    )
```

**`create_sink` format is kafka-only for RTM.** The signature accepts *"either `kafka` or `delta`"* ([create_sink reference](https://docs.databricks.com/aws/en/ldp/developer/ldp-python-ref-sink)), but **Delta is not a supported RTM sink** (see Sources, sinks, and operators below), so within an RTM flow only `format="kafka"` works. Use `delta` sinks in non-RTM flows only.

**Benchmarking / testing:** to run an RTM flow without a real destination, use a `noop` sink — `dp.create_sink(name="bench_sink", format="noop", options={})` discards output (it passes through to the Structured Streaming writer). It's not a documented SDP `create_sink` format and has no support guarantee — fine for local benchmarking, not production.

## `pipelines.trigger.interval` — checkpoint cadence, not batch size

In RTM the batch is long-running and records are processed as they arrive; `pipelines.trigger.interval` (default `"5 minutes"`) governs **how often state and source offsets are checkpointed**, not how often results appear. This is a different meaning from the same key on a normal continuous pipeline (where it's a coarse trigger like `"1 hour"` — see [pipeline-configuration.md](pipeline-configuration.md)). Keep it at minutes; shorter intervals add checkpoint overhead, longer ones increase replay-on-restart.

## Compute

- **Serverless** — managed for you; the default and simplest choice.
- **Classic** — set compute in the pipeline's `clusters` config. Keep **Photon off** (RTM does not use Photon, so enabling it only adds the Photon DBU uplift for no benefit) and **autoscaling off** (RTM runs continuously — size the cluster to fixed capacity). A pipeline will still *start* with either enabled, but neither helps an RTM flow, so leave them disabled.
  - **Size for the slot math.** RTM schedules all stages concurrently, so free slots must cover the **sum of partitions across *every* stage**, not just the source: source read tasks **+** each stateful stage's `spark.sql.shuffle.partitions` **+** any explicit `repartition(n)`. E.g. an 8-task Kafka source feeding one `groupBy` at `shuffle.partitions=20` needs 8 + 20 = 28 slots. Undersize → the flow fails at start with `CONCURRENT_SCHEDULER_INSUFFICIENT_SLOT` (note: this class is **not** in the `STREAMING_REAL_TIME_MODE.*` namespace). Your two levers to shrink the total: cap the source with `maxPartitions` (reads topic partitions across fewer tasks; unset = topic partition count) and set `shuffle.partitions` low. RTM also allows **at most one streaming shuffle stage** per flow (`SHUFFLE_MORE_THAN_ONCE` otherwise) — combine aggregations or use a broadcast join to stay within one. The SS ref's [slot-math table](../../databricks-spark-structured-streaming/references/real-time-mode.md) works through more shapes. On **serverless** you don't size a cluster yourself — it scales to fit — but you should **still set these partition counts**.

## Sources, sinks, and operators

Sources/sinks and most operator restrictions are the **same as standalone RTM** — see its [reference and error-class matrix](../../databricks-spark-structured-streaming/references/real-time-mode.md) for the full set. Sources/sinks: Kafka / MSK / Event Hubs (Kafka connector) as source and sink, Kinesis (EFO) source-only; Delta and file-based sources (Auto Loader, direct file reads) are not supported. The same operators are unsupported as in standalone RTM — session windows, `dropDuplicatesWithinWatermark`, `flatMapGroupsWithState`, `mapPartitions`, and `transformWithStateInPandas`.

**Where SDP-on-RTM is *more* restricted than standalone RTM:**

- **Stream-to-stream joins** — standalone RTM added an inner stream-stream join on DBR 18+, but SDP-on-RTM does not support them. Use a broadcast stream-static join instead.
- **Custom `forEach` sinks** — standalone RTM supports a custom `ForeachWriter`; SDP does not (it exposes only `dp.create_sink` and `@dp.foreach_batch_sink`, with no way to supply a raw `ForeachWriter`).

**RTM flows must be streaming.** A batch flow (materialized view, `spark.read`) can't be an RTM flow — it fails analysis with "real-time mode is only supported for streaming queries." Use a streaming read (`spark.readStream`).

**Not applicable in RTM:** Auto CDC (`dp.create_auto_cdc_flow` / `apply_changes`) is rejected in an RTM flow — RTM flows are plain streaming reads written to a sink.

`transformWithState` itself is supported, with RTM-specific behavior the [SDP docs](https://docs.databricks.com/aws/en/ldp/real-time) spell out: `handleInputRows` is invoked **once per row** (not once per key per batch) and **event-time timers are unsupported** (processing-time only). Same behavior as standalone RTM — see its [reference](../../databricks-spark-structured-streaming/references/real-time-mode.md) for deeper detail.

## One real-time flow per pipeline

Run **one real-time flow per pipeline, and keep non-RTM (micro-batch) flows out of it** — slots aren't reserved per flow, so a co-located flow (especially a bursty micro-batch one) contends for the slots the RTM flow needs.

## Lakebase as a serving layer

An RTM flow in SDP sinks to Kafka — there is no Lakebase sink in the SDP RTM path. To serve an app from Lakebase, wire it up outside the RTM flow; see the [databricks-lakebase](../../databricks-lakebase/SKILL.md) skill (e.g. synced tables).

## Observability and tuning

RTM emits per-batch latency percentiles (`processingLatencyMs`, `sourceQueuingLatencyMs`, `e2eLatencyMs`) in the streaming query progress; watch p99, not the average. See the [standalone RTM reference](../../databricks-spark-structured-streaming/references/real-time-mode.md) for what each measures.

**Set `spark.sql.shuffle.partitions` on stateful flows.** The default is `200`, which a stateful stage (aggregation, `dropDuplicates`, stream-static join) turns into 200 concurrent slots — see the slot math above. Set it low, matched to the stage's real parallelism (the docs' aggregation example uses `"8"`), in the flow's `@dp.update_flow(spark_conf={...})`.

## Related references

- [sink-python.md](sink-python.md) — general SDP sinks (`dp.create_sink`, Delta/Kafka, `@dp.append_flow`).
- [kafka.md](kafka.md) — Kafka / Event Hubs source options.
- [streaming-patterns.md](streaming-patterns.md) — dedup, windowing, late data for non-RTM streaming.
- [../databricks-spark-structured-streaming/references/real-time-mode.md](../../databricks-spark-structured-streaming/references/real-time-mode.md) — standalone RTM: cluster setup, slot math, full error-class catalog, observability internals.
