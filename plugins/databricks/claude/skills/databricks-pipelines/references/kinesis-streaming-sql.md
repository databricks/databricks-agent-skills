# Kinesis Streaming - SQL

Ingesting data from Amazon Kinesis using SQL in Spark Declarative Pipelines. AWS only.

---

## Basic Kinesis Ingestion

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kinesis_events AS
SELECT
  CAST(partitionKey AS STRING) AS partition_key,
  CAST(data AS STRING) AS event_data,
  stream,
  shardId AS shard_id,
  sequenceNumber AS sequence_number,
  approximateArrivalTimestamp AS kinesis_timestamp,
  current_timestamp() AS _ingested_at
FROM STREAM read_kinesis(
  streamName => '${kinesis_stream}',
  region => '${aws_region}',
  initialPosition => 'earliest'
);
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

| Option               | Description                                                | Default          |
| -------------------- | ---------------------------------------------------------- | ---------------- |
| `serviceCredential`  | Unity Catalog service credential name                      | —                |
| `streamName`         | Comma-separated stream names (required)                    | —                |
| `streamARN`          | Stream ARNs (alternative to streamName)                    | —                |
| `region`             | AWS region                                                 | Locally resolved |
| `initialPosition`    | `latest`, `trim_horizon`, `earliest`, `at_timestamp`       | `latest`         |
| `maxRecordsPerFetch` | Records per API request                                    | `10000`          |
| `maxFetchRate`       | Prefetch rate in MB/s (1.0–2.0)                            | `1.0`            |
| `shardsPerTask`      | Shards to prefetch per Spark task                          | `5`              |
| `consumerMode`       | `polling` (default) or `efo` (enhanced fan-out, DBR 11.3+) | `polling`        |

---

## Authentication

Kinesis uses AWS IAM — no SASL/JAAS configuration needed.

### Service Credential (Recommended)

Unity Catalog service credentials are the preferred authentication method for Kinesis on Databricks. They work on shared clusters and serverless compute, and handle credential lifecycle automatically. The IAM role attached to the service credential must have `kinesis:ListShards`, `kinesis:GetRecords`, and `kinesis:GetShardIterator` permissions.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kinesis_events AS
SELECT * FROM STREAM read_kinesis(
  streamName => '${kinesis_stream}',
  region => '${aws_region}',
  serviceCredential => '<service-credential-name>'
);
```

### Direct Keys (Use secret() Function)

```sql
FROM STREAM read_kinesis(
  streamName => '${kinesis_stream}',
  region => '${aws_region}',
  awsAccessKey => secret('kinesis', 'access-key'),
  awsSecretKey => secret('kinesis', 'secret-key')
)
```

### IAM Role Assumption (Cross-Account)

```sql
FROM STREAM read_kinesis(
  streamName => '${kinesis_stream}',
  region => '${aws_region}',
  initialPosition => 'earliest',
  roleArn => 'arn:aws:iam::123456789012:role/MyRole',
  roleSessionName => 'my-session'
)
```

### Default AWS Provider Chain

If no auth options are set, falls back to environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and the standard AWS credential chain.

---

## Deserialization

For JSON and Avro parsing patterns see **[Deserialization - SQL](deserialization-sql.md)**.

---

## Multiple Streams

```sql
FROM STREAM read_kinesis(
  streamName => 'orders-stream,customers-stream',
  region => '${aws_region}'
)
```

Route by stream name:

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders AS
SELECT * FROM STREAM bronze_kinesis_events
WHERE stream = 'orders-stream';
```

---

## Pipeline Parameters

```yaml
configuration:
  kinesis_stream: my-events-stream
  aws_region: us-east-1
```

```sql
streamName => '${kinesis_stream}'
region => '${aws_region}'
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
