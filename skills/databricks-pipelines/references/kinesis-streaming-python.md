# Kinesis Streaming - Python

Ingesting data from Amazon Kinesis using Python in Spark Declarative Pipelines. AWS only.

---

## Basic Kinesis Ingestion

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_kinesis_events")
def bronze_kinesis_events():
    """Ingest raw events from Kinesis."""
    return (
        spark.readStream
        .format("kinesis")
        .option("streamName", spark.conf.get("kinesis_stream"))
        .option("region", spark.conf.get("aws_region"))
        .option("initialPosition", "earliest")
        .option("failOnDataLoss", "false")
        .load()
        .selectExpr(
            "CAST(partitionKey AS STRING) AS partition_key",
            "CAST(data AS STRING) AS event_data",
            "stream",
            "shardId AS shard_id",
            "sequenceNumber AS sequence_number",
            "approximateArrivalTimestamp AS kinesis_timestamp"
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

---

## Output Schema

Kinesis returns a fixed schema — the `data` column is binary and must be cast:

| Column                        | Type      | Description                       |
| ----------------------------- | --------- | --------------------------------- |
| `partitionKey`                | STRING    | Shard routing key                 |
| `data`                        | BINARY    | Payload (cast to STRING for JSON) |
| `stream`                      | STRING    | Source stream name                |
| `shardId`                     | STRING    | Shard identifier                  |
| `sequenceNumber`              | STRING    | Record sequence within shard      |
| `approximateArrivalTimestamp` | TIMESTAMP | Insertion time                    |

Primary key: `(stream, shardId, sequenceNumber)`

---

## Configuration Options

| Option               | Description                                          | Default          |
| -------------------- | ---------------------------------------------------- | ---------------- |
| `serviceCredential`  | Unity Catalog service credential name                | —                |
| `streamName`         | Comma-separated stream names (required)              | —                |
| `streamARN`          | Stream ARNs (alternative to streamName)              | —                |
| `region`             | AWS region                                           | Locally resolved |
| `initialPosition`    | `latest`, `trim_horizon`, `earliest`, `at_timestamp` | `latest`         |
| `failOnDataLoss`     | Prevent failure if sequence numbers expire           | —                |
| `maxRecordsPerFetch` | Records per API request                              | `10000`          |
| `maxFetchRate`       | Prefetch rate in MB/s (1.0–2.0)                      | `1.0`            |
| `shardsPerTask`      | Shards to prefetch per Spark task                    | `5`              |
| `consumerMode`       | `polling` (default) or `efo` (enhanced fan-out)      | `polling`        |

---

## Authentication

Kinesis uses AWS IAM — no SASL/JAAS configuration needed.

### Service Credential (Recommended)

Unity Catalog service credentials are the preferred authentication method for Kinesis on Databricks. They work on shared clusters and serverless compute, and handle credential lifecycle automatically. The IAM role attached to the service credential must have `kinesis:ListShards`, `kinesis:GetRecords`, and `kinesis:GetShardIterator` permissions.

```python
@dp.table(name="bronze_kinesis_events")
def bronze_kinesis_events():
    return (
        spark.readStream
        .format("kinesis")
        .option("streamName", spark.conf.get("kinesis_stream"))
        .option("region", spark.conf.get("aws_region"))
        .option("serviceCredential", "<service-credential-name>")
        .option("initialPosition", "earliest")
        .load()
    )
```

### IAM Role Assumption (Cross-Account)

```python
.option("roleArn", "arn:aws:iam::123456789012:role/MyRole")
.option("roleExternalId", "my-external-id")        # Optional
.option("roleSessionName", "my-session")            # Optional
```

### Direct Keys (Store in Secrets)

```python
.option("awsAccessKey", dbutils.secrets.get(scope="kinesis", key="access-key"))
.option("awsSecretKey", dbutils.secrets.get(scope="kinesis", key="secret-key"))
```

### Instance Profile

Attach IAM role to compute — no options needed. Not supported in standard access mode.

### Default AWS Provider Chain

If no auth options are set, falls back to environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and the standard AWS credential chain.

---

## Deserialization

For JSON, Avro, and Protobuf parsing patterns see **[Deserialization - Python](deserialization-python.md)**.

---

## Multiple Streams

```python
.option("streamName", "orders-stream,customers-stream")
```

Route by stream name:

```python
@dp.table(name="silver_orders")
def silver_orders():
    return spark.readStream.table("bronze_kinesis_events").filter(F.col("stream") == "orders-stream")
```

---

## Pipeline Parameters

```python
stream_name = spark.conf.get("kinesis_stream")
aws_region = spark.conf.get("aws_region")
```

```yaml
configuration:
  kinesis_stream: my-events-stream
  aws_region: us-east-1
```

---

## Common Issues

| Issue                 | Solution                                                              |
| --------------------- | --------------------------------------------------------------------- |
| Connection refused    | Verify `region` and network access to Kinesis endpoint                |
| Authentication failed | Check IAM permissions: `ListShards`, `GetRecords`, `GetShardIterator` |
| No data received      | Verify stream exists; check `initialPosition`                         |
| Throttling errors     | Reduce `maxFetchRate` or increase shard count                         |
| Consumer lag          | Increase `shardsPerTask` or switch to `efo` mode                      |
