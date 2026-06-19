# Sinks (Python only)

Sinks write pipeline output to non-pipeline-managed targets: Kafka / Event Hubs topics, externally-managed Delta tables, or volumes. Python-only. Streaming queries only. Only compatible with `@dp.append_flow()`.

For per-batch custom Python logic (merge/upsert, multi-destination), see [foreach-batch-sink-python.md](foreach-batch-sink-python.md).

## `dp.create_sink(...)`

Call at top level before any `@dp.append_flow` references it.

```python
dp.create_sink(
    name="<sink_name>",          # required — referenced as target= in @dp.append_flow
    format="<format>",           # required — "delta", "kafka", or a custom format
    options={...},               # required — format-specific options
)
```

## Delta sinks

Write to an externally-managed Delta table or to a UC volume path. Use three-part names for UC tables.

```python
# Unity Catalog table
dp.create_sink(name="delta_sink", format="delta",
               options={"tableName": "main.sales.transactions"})
# OR volume path
dp.create_sink(name="delta_sink_path", format="delta",
               options={"path": "/Volumes/catalog/schema/transactions"})

@dp.append_flow(name="write_to_delta", target="delta_sink")
def write_transactions():
    return (spark.readStream.table("bronze_transactions")
                 .select("transaction_id", "customer_id", "amount", "timestamp"))
```

## Kafka / Event Hubs sinks

Same `format="kafka"` for both — only the broker endpoint differs (Event Hubs is `<namespace>.servicebus.windows.net:9093`).

The output DataFrame **must** have a `value` column (the serialized payload). Optional output columns: `key`, `partition`, `headers`, `topic`.

```python
dp.create_sink(name="kafka_sink", format="kafka", options={
    "kafka.bootstrap.servers":      "kafka-broker:9092",
    "topic":                        "customer_events",
    "databricks.serviceCredential": "<service_credential_name>",   # UC service credential
})

@dp.append_flow(name="stream_to_kafka", target="kafka_sink")
def kafka_flow():
    return (spark.readStream.table("customer_events")
                 .selectExpr("cast(customer_id as string) AS key",
                             "to_json(struct(*)) AS value"))
```

Use `databricks.serviceCredential` (UC service credential) for auth — don't hard-code keys or use raw `kafka.sasl.*` for sinks.

## Limitations

- Streaming queries only; sinks are not compatible with batch DataFrames.
- Only `@dp.append_flow` writes to a sink — no `@dp.table` direct writes.
- Pipeline expectations cannot be attached to a sink. Validate in upstream tables/views.
- Full refresh re-runs the flow and **appends** to the sink (no cleanup of prior writes). Design downstream consumers to be idempotent, or pre-truncate the target manually.
- SQL has no sink support.
