# Kafka Authentication - Python

Authentication methods for Kafka in Spark Declarative Pipelines (Python). See also: **[Core Ingestion](kafka-streaming-python.md)** | **[Deserialization](kafka-deserialization-python.md)**

> **Shaded class names required:** Databricks bundles its own shaded Kafka libraries. Any class name referenced in `kafka.sasl.jaas.config`, `kafka.sasl.login.callback.handler.class`, or `kafka.sasl.client.callback.handler.class` must use the Databricks-shaded prefix — not the standard open-source name. Using unshaded names raises `RESTRICTED_STREAMING_OPTION_PERMISSION_ENFORCED`.
> - `org.apache.kafka.*` → `kafkashaded.org.apache.kafka.*`
> - `software.amazon.msk.*` → `shadedmskiam.software.amazon.msk.*`

Start from the base `kafka_options` / `spark.readStream.format("kafka")`
pattern in **[Core Ingestion](kafka-streaming-python.md)**. Each section below
shows only the authentication options to add or replace.

---

## Service Credential (Recommended)

Unity Catalog service credentials are the preferred authentication method. They eliminate JAAS configuration, work on shared clusters and serverless compute, and handle credential lifecycle automatically. Supported for AWS MSK, Azure Event Hubs, and GCP Managed Kafka.

Runtime requirements differ by cloud:
- **AWS MSK / Azure Event Hubs**: Databricks Runtime 16.1+
- **GCP Managed Kafka**: Databricks Runtime 18.0+; serverless compute is **not supported**; the cluster must be VPC-peered or use Private Service Connect, and the cluster service account needs the `roles/managedkafka.client` IAM role

```python
kafka_options.update({
    "databricks.serviceCredential": "<service-credential-name>",
    # Azure only — uncomment if Databricks cannot infer the OAuth scope for your Event Hubs service:
    # "databricks.serviceCredential.scope": "https://<eventhub-namespace>.servicebus.windows.net/.default",
})
```

When using a service credential, the following options are **not needed**: `kafka.sasl.mechanism`, `kafka.sasl.jaas.config`, `kafka.security.protocol`, `kafka.sasl.client.callback.handler.class`, `kafka.sasl.oauthbearer.token.endpoint.url` (Azure specific).

---

## AWS MSK IAM

Uses the `AWS_MSK_IAM` SASL mechanism. The JAAS config contains no secrets — credentials come from the AWS SDK.

**Instance profile** (uses the IAM role attached to the cluster):

```python
kafka_options.update({
    "kafka.sasl.mechanism": "AWS_MSK_IAM",
    "kafka.sasl.jaas.config": "shadedmskiam.software.amazon.msk.auth.iam.IAMLoginModule required;",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.client.callback.handler.class": "shadedmskiam.software.amazon.msk.auth.iam.IAMClientCallbackHandler",
})
```

**IAM role** (assume a specific role instead of the instance profile — add `awsRoleArn` to the JAAS config):

```python
kafka_options.update({
    "kafka.sasl.mechanism": "AWS_MSK_IAM",
    "kafka.sasl.jaas.config": "shadedmskiam.software.amazon.msk.auth.iam.IAMLoginModule required awsRoleArn='arn:aws:iam::123456789012:role/msk_client_role';",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.client.callback.handler.class": "shadedmskiam.software.amazon.msk.auth.iam.IAMClientCallbackHandler",
})
```

---

## SCRAM-SHA-256 / SCRAM-SHA-512

SCRAM uses challenge-response authentication and never transmits passwords in cleartext. Use when service credentials are not available. Works against any standard Kafka broker including Azure HDInsight and self-managed Kafka on Azure — but not Azure Event Hubs specifically, which requires SASL/PLAIN with `$ConnectionString` or Entra ID instead.

```python
kafka_options.update({
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "SCRAM-SHA-512",   # or "SCRAM-SHA-256"
    "kafka.sasl.jaas.config": (
        f'kafkashaded.org.apache.kafka.common.security.scram.ScramLoginModule required '
        f'username="{dbutils.secrets.get(scope="kafka", key="username")}" '
        f'password="{dbutils.secrets.get(scope="kafka", key="password")}";'
    ),
})
```

---

## SASL/Plain

```python
username = dbutils.secrets.get(scope="kafka", key="username")
password = dbutils.secrets.get(scope="kafka", key="password")
jaas_config = (
    f'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required '
    f'username="{username}" password="{password}";'
)

kafka_options.update({
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "PLAIN",
    "kafka.sasl.jaas.config": jaas_config,
})
```

---

## SSL/TLS

**One-way TLS** (server identity verification only):

```python
kafka_options.update({
    "kafka.security.protocol": "SSL",
    "kafka.ssl.truststore.location": "/Volumes/catalog/schema/volume/truststore.jks",
    "kafka.ssl.truststore.password": dbutils.secrets.get("kafka", "truststore-password"),
    "kafka.ssl.endpoint.identification.algorithm": "https",
})
```

**Mutual TLS** (client certificate authentication):

```python
kafka_options.update({
    "kafka.security.protocol": "SSL",
    "kafka.ssl.truststore.location": "/Volumes/catalog/schema/volume/truststore.jks",
    "kafka.ssl.truststore.password": dbutils.secrets.get("kafka", "truststore-password"),
    "kafka.ssl.keystore.location": "/Volumes/catalog/schema/volume/keystore.jks",
    "kafka.ssl.keystore.password": dbutils.secrets.get("kafka", "keystore-password"),
    "kafka.ssl.key.password": dbutils.secrets.get("kafka", "key-password"),
    "kafka.ssl.endpoint.identification.algorithm": "https",
})
```

Store keystores and truststores in Unity Catalog volumes. Store passwords in Databricks secret scopes.

---

## Azure Event Hubs (Kafka API)

Azure Event Hubs exposes a Kafka-compatible endpoint on port **9093**. Three authentication approaches exist, in recommended order:

**1. Service credential (preferred — requires DBR 16.1+, works on shared/serverless compute)**

Use the Service Credential section above — no Event Hubs-specific config needed.

**2. Microsoft Entra ID / OAuth (client ID + secret)**

Use when service credentials are not available. Requires the `OAUTHBEARER` SASL mechanism.

> **Compute restrictions:** Works on dedicated access mode (DBR 12.2 LTS+) or standard access mode (DBR 14.3 LTS+). **Not supported** on Unity Catalog Lakeflow Pipelines — use service credentials instead. Certificate-based Entra ID auth is not supported on any compute.

```python
tenant_id = spark.conf.get("azure_tenant_id")
client_id = spark.conf.get("azure_client_id")
client_secret = dbutils.secrets.get(scope="eventhub", key="client-secret")
server = f"{spark.conf.get('eventhub_namespace')}.servicebus.windows.net"

sasl_config = (
    f'kafkashaded.org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required '
    f'clientId="{client_id}" clientSecret="{client_secret}" '
    f'scope="https://{server}/.default" ssl.protocol="SSL";'
)

kafka_options = {
    "kafka.bootstrap.servers": f"{server}:9093",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "OAUTHBEARER",
    "kafka.sasl.jaas.config": sasl_config,
    "kafka.sasl.oauthbearer.token.endpoint.url":
        f"https://login.microsoft.com/{tenant_id}/oauth2/v2.0/token",
    "kafka.sasl.login.callback.handler.class":
        "kafkashaded.org.apache.kafka.common.security.oauthbearer.secured.OAuthBearerLoginCallbackHandler",
}
```

**3. SASL/PLAIN with connection string (fallback)**

```python
namespace = spark.conf.get("eventhub_namespace")
connection_string = dbutils.secrets.get(scope="eventhub", key="connection-string")

kafka_options = {
    "kafka.bootstrap.servers": f"{namespace}.servicebus.windows.net:9093",
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "PLAIN",
    "kafka.sasl.jaas.config": (
        f'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required '
        f'username="$ConnectionString" password="{connection_string}";'
    ),
}
```

The username is the literal `$ConnectionString`; the password is the namespace- or entity-level connection string (it contains `SharedAccessKey=...`).

---

## GCP Managed Service for Apache Kafka

**Service credential (preferred)** — use `databricks.serviceCredential` as shown in the Service Credential section above. Requires DBR 18.0+, VPC peering or Private Service Connect, and the `roles/managedkafka.client` IAM role on the cluster service account. If Databricks cannot infer the OAuth scope automatically, add:

```python
"databricks.serviceCredential.scope": "https://www.googleapis.com/auth/cloud-platform"
```

**Manual SASL/OAUTHBEARER** — use when service credentials are not available. GCP Managed Kafka requires a GCP-specific login callback handler class:

```python
kafka_options = {
    "kafka.bootstrap.servers": spark.conf.get("kafka_brokers"),
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "OAUTHBEARER",
    "kafka.sasl.jaas.config": "kafkashaded.org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;",
    "kafka.sasl.login.callback.handler.class":
        "org.apache.spark.sql.kafka010.CustomGCPOAuthBearerLoginCallbackHandler",
}
```

The `CustomGCPOAuthBearerLoginCallbackHandler` class is specific to Databricks on GCP — do not use it on AWS or Azure.

---

## Read/Write Options Separation

Consumer-only options like `kafka.group.id` and `kafka.session.timeout.ms` cause errors when used with Kafka producers. Use separate option dictionaries for reads and writes.

```python
# Full options for READS
kafka_read_options = {
    "kafka.bootstrap.servers": spark.conf.get("kafka_brokers"),
    "databricks.serviceCredential": "<service-credential-name>",
    "kafka.request.timeout.ms": "60000",
    "kafka.session.timeout.ms": "30000",
    "kafka.group.id": "my-pipeline-consumer-group",
}

# For WRITES - filter out consumer-only options
kafka_write_options = {
    k: v for k, v in kafka_read_options.items()
    if k not in ["kafka.group.id", "kafka.session.timeout.ms"]
}
```

> **Idempotent write note (DBR 13.3 LTS+):** Databricks Runtime 13.3 LTS and above enables idempotent writes by default. If your Kafka cluster is version 2.8.0 or below and uses ACLs without the `IDEMPOTENT_WRITE` permission, writes will fail. Resolve by upgrading Kafka or adding `.option("kafka.enable.idempotence", "false")`.

---

## Common Issues

| Error / Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `RESTRICTED_STREAMING_OPTION_PERMISSION_ENFORCED` | Unshaded class name used in JAAS config or callback handler option | Replace with `kafkashaded.org.apache.kafka.*` or `shadedmskiam.software.amazon.msk.*` prefix |
| `SaslException` / `Failed to construct kafka consumer` | Incorrect IAM role ARN, role missing permissions, or instance profile not attached to cluster | Verify ARN format; confirm `kafka-cluster:Connect` and `kafka-cluster:ReadData` IAM permissions |
| `TimeoutException` / connection refused | MSK security group not allowing inbound traffic from Databricks compute security group, or VPC peering/PrivateLink misconfigured | Check security group inbound rules on the MSK cluster; verify VPC connectivity |
| Auth succeeds but no data returned | IAM role missing `kafka-cluster:ReadData` for the topic, or `startingOffsets` defaulting to `latest` | Add topic-level `ReadData` permission; set `startingOffsets` to `earliest` to read existing data |
| `Failed to create a new KafkaAdminClient` (Entra ID) | Incorrect tenant ID, client ID, or Event Hubs server in OAuth config | Verify all three values; do not modify default `kafka.security.protocol` or `kafka.sasl.mechanism` |
