# Streaming connectors: Kafka, RabbitMQ

Managed pull from a message bus into streaming tables. The Kafka connector deserializes keys and values (`key_transformer` / `value_transformer`, in the formats the [Kafka pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/kafka-pipeline) page lists); other transformations: `read_kafka` in **databricks-pipelines** or **databricks-spark-structured-streaming**; producers that push: **databricks-zerobus-ingest**.

How they differ from the SaaS steps:

- **Continuous, not scheduled:** `continuous: true`; the Kafka limits page says workflow-based scheduling isn't supported. No Jobs `pipeline_task`.
- **`channel: PREVIEW` is required**, with `serverless: true` (serverless compute on for the workspace).
- **Previews toggle** first when the page's Beta note mentions the Previews page (Kafka).
- **Objects name topics or queues:** Kafka uses `source_table: N/A` plus `connector_options.kafka_options.topics`; RabbitMQ uses `connector_options.rabbitmq_options.queue`, with no source fields. Each object is one streaming table.
- **Auth:** Kafka: username and password or a service credential (`kafka-connection`). RabbitMQ: broker endpoint and credentials; delivery is at least once.

```yaml
resources:
  pipelines:
    kafka_pipeline:
      name: kafka-ingestion-pipeline
      serverless: true
      continuous: true
      channel: PREVIEW
      catalog: main
      schema: kafka_ingest
      ingestion_definition:
        connection_name: <kafka-connection>
        objects:
          - table:
              source_table: N/A
              destination_catalog: main
              destination_schema: kafka_ingest
              destination_table: user_events
              connector_options:
                kafka_options:
                  topics: [user-events, power-user-events]
```

- Key and value land as `BINARY`; the pipeline page has transformers for a STRING key and a JSON value.
- One topic to several tables (fanout) is Private Preview and needs a continuous pipeline.
