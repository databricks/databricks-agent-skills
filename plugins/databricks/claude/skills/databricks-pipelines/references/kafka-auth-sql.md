# Kafka Authentication - SQL

Authentication methods for Kafka in Spark Declarative Pipelines (SQL). See also: **[Core Ingestion](kafka-streaming-sql.md)** | **[Deserialization](deserialization-sql.md)**

> **Shaded class names required:** Databricks bundles its own shaded Kafka libraries. Any class name referenced in `kafka.sasl.jaas.config`, `kafka.sasl.login.callback.handler.class`, or `kafka.sasl.client.callback.handler.class` must use the Databricks-shaded prefix — not the standard open-source name. Using unshaded names raises `RESTRICTED_STREAMING_OPTION_PERMISSION_ENFORCED`.
> - `org.apache.kafka.*` → `kafkashaded.org.apache.kafka.*`
> - `software.amazon.msk.*` → `shadedmskiam.software.amazon.msk.*`

Start from the base `FROM STREAM read_kafka(...)` pattern in
**[Core Ingestion](kafka-streaming-sql.md)**. Each section below shows only the
authentication arguments to add or replace.

---

## Service Credential (Recommended)

Unity Catalog service credentials are the preferred authentication method. They eliminate JAAS configuration, work on shared clusters and serverless compute, and handle credential lifecycle automatically. Supported for AWS MSK, Azure Event Hubs, and GCP Managed Kafka.

Runtime requirements differ by cloud:
- **AWS MSK / Azure Event Hubs**: Databricks Runtime 16.1+
- **GCP Managed Kafka**: Databricks Runtime 18.0+; serverless compute is **not supported**; the cluster must be VPC-peered or use Private Service Connect, and the cluster service account needs the `roles/managedkafka.client` IAM role

```sql
serviceCredential => '${kafka_credential}',
-- Azure only — uncomment if Databricks cannot infer the OAuth scope:
-- `databricks.serviceCredential.scope` => 'https://<eventhub-namespace>.servicebus.windows.net/.default'
```

When using a service credential, the following options are **not needed**: `kafka.sasl.mechanism`, `kafka.sasl.jaas.config`, `kafka.security.protocol`, `kafka.sasl.client.callback.handler.class`.

---

## AWS MSK IAM

Uses the `AWS_MSK_IAM` SASL mechanism. The JAAS config contains no secrets — credentials come from the AWS SDK.

**Instance profile** (uses the IAM role attached to the cluster):

```sql
`kafka.sasl.mechanism` => 'AWS_MSK_IAM',
`kafka.sasl.jaas.config` => 'shadedmskiam.software.amazon.msk.auth.iam.IAMLoginModule required;',
`kafka.security.protocol` => 'SASL_SSL',
`kafka.sasl.client.callback.handler.class` => 'shadedmskiam.software.amazon.msk.auth.iam.IAMClientCallbackHandler'
```

**IAM role** (assume a specific role — add `awsRoleArn` to the JAAS config):

```sql
`kafka.sasl.mechanism` => 'AWS_MSK_IAM',
`kafka.sasl.jaas.config` => 'shadedmskiam.software.amazon.msk.auth.iam.IAMLoginModule required awsRoleArn=''arn:aws:iam::123456789012:role/msk_client_role'';',
`kafka.security.protocol` => 'SASL_SSL',
`kafka.sasl.client.callback.handler.class` => 'shadedmskiam.software.amazon.msk.auth.iam.IAMClientCallbackHandler'
```

> **Note:** For auth methods that require embedding passwords in JAAS config strings (SCRAM, PLAIN), prefer the Python API which can use `dbutils.secrets.get()` to build the config string safely.

---

## SCRAM-SHA-256 / SCRAM-SHA-512

SCRAM uses challenge-response authentication and never transmits passwords in cleartext. Use when service credentials are not available. Works against any standard Kafka broker including Azure HDInsight and self-managed Kafka on Azure — but not Azure Event Hubs specifically, which requires SASL/PLAIN with `$ConnectionString` or Entra ID instead.

```sql
`kafka.security.protocol` => 'SASL_SSL',
`kafka.sasl.mechanism` => 'SCRAM-SHA-256',
`kafka.sasl.jaas.config` => 'kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required username="' || secret('kafka', 'username') || '" password="' || secret('kafka', 'password') || '";',
`kafka.ssl.endpoint.identification.algorithm` => 'https'
```

Replace `SCRAM-SHA-256` with `SCRAM-SHA-512` to use the stronger variant.

---

## SASL/Plain

```sql
`kafka.security.protocol` => 'SASL_SSL',
`kafka.sasl.mechanism` => 'PLAIN',
`kafka.sasl.jaas.config` => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="' || secret('kafka', 'username') || '" password="' || secret('kafka', 'password') || '";'
```

---

## SSL/TLS

Use the `secret('scope', 'key')` SQL function for password values in `read_kafka` arguments.

**One-way TLS** (server identity verification only):

```sql
`kafka.security.protocol` => 'SSL',
`kafka.ssl.truststore.location` => '/Volumes/catalog/schema/volume/truststore.jks',
`kafka.ssl.truststore.password` => secret('kafka', 'truststore-password'),
`kafka.ssl.endpoint.identification.algorithm` => 'https'
```

**Mutual TLS** (client certificate authentication):

```sql
`kafka.security.protocol` => 'SSL',
`kafka.ssl.truststore.location` => '/Volumes/catalog/schema/volume/truststore.jks',
`kafka.ssl.truststore.password` => secret('kafka', 'truststore-password'),
`kafka.ssl.keystore.location` => '/Volumes/catalog/schema/volume/keystore.jks',
`kafka.ssl.keystore.password` => secret('kafka', 'keystore-password'),
`kafka.ssl.key.password` => secret('kafka', 'key-password'),
`kafka.ssl.endpoint.identification.algorithm` => 'https'
```

Store keystores and truststores in Unity Catalog volumes. Store passwords in Databricks secret scopes.

---

## Azure Event Hubs (Kafka API)

Azure Event Hubs exposes a Kafka-compatible endpoint on port **9093**. Three authentication approaches exist, in recommended order:

**1. Service credential (preferred — requires DBR 16.1+, works on shared/serverless compute)**

Use `serviceCredential => '${kafka_credential}'` as shown in the Service Credential section above.

**2. Microsoft Entra ID / OAuth (client ID + secret)**

Use when service credentials are not available. **Not supported on Unity Catalog Lakeflow Pipelines** — use a service credential instead.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_eventhub_events AS
SELECT * FROM STREAM read_kafka(
  bootstrapServers => '${eventhub_namespace}.servicebus.windows.net:9093',
  subscribe => '${eventhub_name}',
  `kafka.security.protocol` => 'SASL_SSL',
  `kafka.sasl.mechanism` => 'OAUTHBEARER',
  `kafka.sasl.jaas.config` => 'kafkashaded.org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required clientId="' || secret('azure', 'client-id') || '" clientSecret="' || secret('azure', 'client-secret') || '" scope="https://${eventhub_namespace}.servicebus.windows.net/.default" ssl.protocol="SSL";',
  `kafka.sasl.oauthbearer.token.endpoint.url` => 'https://login.microsoft.com/${azure_tenant_id}/oauth2/v2.0/token',
  `kafka.sasl.login.callback.handler.class` => 'kafkashaded.org.apache.kafka.common.security.oauthbearer.secured.OAuthBearerLoginCallbackHandler'
);
```

**3. SASL/PLAIN with connection string (fallback)**


```sql
FROM STREAM read_kafka(
  bootstrapServers => '${eventhub_namespace}.servicebus.windows.net:9093',
  subscribe => '${eventhub_name}',
  `kafka.security.protocol` => 'SASL_SSL',
  `kafka.sasl.mechanism` => 'PLAIN',
  `kafka.sasl.jaas.config` => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="$ConnectionString" password="' || secret('eventhub', 'connection-string') || '";'
)
```

The username is the literal `$ConnectionString`; the password is the namespace- or entity-level connection string (it contains `SharedAccessKey=...`).

---

## GCP Managed Service for Apache Kafka

**Service credential (preferred)** — use `serviceCredential => '${kafka_credential}'` as shown in the Service Credential section above. Requires DBR 18.0+, VPC peering or Private Service Connect, and the `roles/managedkafka.client` IAM role on the cluster service account. If Databricks cannot infer the OAuth scope automatically, add:

```sql
`databricks.serviceCredential.scope` => 'https://www.googleapis.com/auth/cloud-platform'
```

**Manual SASL/OAUTHBEARER** — use when service credentials are not available. GCP Managed Kafka requires a GCP-specific login callback handler class:

```sql
FROM STREAM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe => 'events',
  `kafka.security.protocol` => 'SASL_SSL',
  `kafka.sasl.mechanism` => 'OAUTHBEARER',
  `kafka.sasl.jaas.config` => 'kafkashaded.org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;',
  `kafka.sasl.login.callback.handler.class` => 'org.apache.spark.sql.kafka010.CustomGCPOAuthBearerLoginCallbackHandler'
)
```

The `CustomGCPOAuthBearerLoginCallbackHandler` class is specific to Databricks on GCP — do not use it on AWS or Azure.

---

## Common Issues

| Error / Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `RESTRICTED_STREAMING_OPTION_PERMISSION_ENFORCED` | Unshaded class name used in JAAS config or callback handler option | Replace with `kafkashaded.org.apache.kafka.*` or `shadedmskiam.software.amazon.msk.*` prefix |
| `SaslException` / `Failed to construct kafka consumer` | Incorrect IAM role ARN, role missing permissions, or instance profile not attached to cluster | Verify ARN format; confirm `kafka-cluster:Connect` and `kafka-cluster:ReadData` IAM permissions |
| `TimeoutException` / connection refused | MSK security group not allowing inbound traffic from Databricks compute security group, or VPC peering/PrivateLink misconfigured | Check security group inbound rules on the MSK cluster; verify VPC connectivity |
| Auth succeeds but no data returned | IAM role missing `kafka-cluster:ReadData` for the topic, or `startingOffsets` defaulting to `latest` | Add topic-level `ReadData` permission; set `startingOffsets` to `'earliest'` to read existing data |
| `Failed to create a new KafkaAdminClient` (Entra ID) | Incorrect tenant ID, client ID, or Event Hubs server in OAuth config | Verify all three values; do not modify default `kafka.security.protocol` or `kafka.sasl.mechanism` |
