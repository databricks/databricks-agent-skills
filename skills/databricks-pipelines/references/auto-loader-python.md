Auto Loader (`cloudFiles`) is recommended for ingesting from cloud storage.

**Basic Syntax:**

```python
@dp.table()
def my_table():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")  # or csv, parquet, etc.
        .load("s3://bucket/path")
    )
```

**Critical Spark Declarative Pipelines + Auto Loader Rules:**

- Databricks automatically manages `cloudFiles.schemaLocation` and checkpoint - do NOT specify these
- Auto Loader returns a streaming DataFrame - the streaming table rules apply (MANDATORY: read [streaming-table-python.md](streaming-table-python.md))
  - Can be used in either a streaming `@dp.table()` / `@dlt.table()` or via `@dp.append_flow()` / `@dlt.append_flow()`
  - Use `spark.readStream` not `spark.read` for streaming ingestion
- Schema (inference, evolution, hints, rescued data column, partitions, type widening): see [auto-loader-schema](auto-loader-schema.md). Key starting points:
  - JSON/CSV/XML infer all columns as `STRING` by default — set `cloudFiles.inferColumnTypes=true` for real types. Parquet/Avro infer types from the file's encoded schema. ORC has NO inference (provide schema). Text has a fixed schema.
  - When Auto Loader infers the schema, `_rescued_data` is auto-added. With a manual schema, opt in via `rescuedDataColumn`.
  - Use `cloudFiles.schemaHints` to pin known column types when inferring.
  - Use `cloudFiles.partitionColumns` only when Hive-style partitions (`key=value`) are inconsistent or new partition keys appear.
  - Quarantine malformed rows via the rescued-data pattern in [streaming-table-sql.md](streaming-table-sql.md#rescued-data-quarantine).
- File detection (Lakeflow SDP): SDP picks an appropriate detection mode automatically. Outside SDP, prefer file notification mode with **file events** (UC external location with file events enabled) — this scales to billions of files and avoids `LIST` calls.
- Path performance: prefer **volume paths** (`/Volumes/<catalog>/<schema>/<volume>/...`) over cloud URLs (`s3://...`, `abfss://...`, `gs://...`) — Auto Loader uses an optimized listing path for volumes.
- File events operational notes (when `cloudFiles.useManagedFileEvents=true`):
  - Run the stream at least once every 7 days; otherwise the next run falls back to a full directory listing (still correct, just slower).
  - Migrating an existing stream to file events performs a one-time full directory listing on first start (exactly-once is preserved across the migration).
  - Do NOT set `cloudFiles.backfillInterval` together with `useManagedFileEvents=true` — the file events service does its own 24-hour reconciliation listings.
- Trigger interval: for continuous-trigger SDP pipelines, set `pipelines.trigger.interval` to `1 minute` or higher (see [pipeline-settings](pipeline-settings.md)). Lower intervals mostly waste polling cost. For event-driven pipelines, prefer file arrival triggers in Lakeflow Jobs over a continuous trigger.
- Cloud auth: in SDP with UC external locations or `databricks.serviceCredential`, you generally don't need to set the cloud-specific options below. Set `cloudFiles.region`/`cloudFiles.queueUrl`/etc. only for classic file notification mode without UC.
- File identity: Auto Loader tracks each file by path (exactly-once). Setting `cloudFiles.allowOverwrites=true` makes it also use the file's last-modified timestamp, so updated/overwritten files are reprocessed (you must dedupe downstream — consider using Auto CDC, see [auto-cdc-python](auto-cdc-python.md)).

**Common Auto Loader Options**
Below are all format agnostic options for Auto Loader.

Common Auto Loader Options

| Option                                   | Type            | Notes                                                                       |
| ---------------------------------------- | --------------- | --------------------------------------------------------------------------- |
| cloudFiles.allowOverwrites               | Boolean         |                                                                             |
| cloudFiles.backfillInterval              | Interval String | Periodic backfill listings; do NOT combine with `useManagedFileEvents=true` |
| cloudFiles.cleanSource                   | String          |                                                                             |
| cloudFiles.cleanSource.retentionDuration | Interval String |                                                                             |
| cloudFiles.cleanSource.moveDestination   | String          |                                                                             |
| cloudFiles.format                        | String          | json / csv / parquet / avro / orc / xml / text / binaryFile                 |
| cloudFiles.includeExistingFiles          | Boolean         | Backfill existing files on first run                                        |
| cloudFiles.inferColumnTypes              | Boolean         |                                                                             |
| cloudFiles.maxBytesPerTrigger            | Byte String     |                                                                             |
| cloudFiles.maxFileAge                    | Interval String |                                                                             |
| cloudFiles.maxFilesPerTrigger            | Integer         |                                                                             |
| cloudFiles.partitionColumns              | String          | Hive-style partition discovery                                              |
| cloudFiles.schemaEvolutionMode           | String          | See [auto-loader-schema](auto-loader-schema.md)                             |
| cloudFiles.schemaHints                   | String          | See [auto-loader-schema](auto-loader-schema.md)                             |
| cloudFiles.schemaLocation                | String          | DO NOT SET - managed automatically                                          |
| cloudFiles.useStrictGlobber              | Boolean         | Match default Spark globbing                                                |
| cloudFiles.validateOptions               | Boolean         | Validate options at stream start                                            |

**Throughput / cost knobs (most users don't need to tune):**

- `cloudFiles.maxFilesPerTrigger` / `cloudFiles.maxBytesPerTrigger`: rate-limit per micro-batch. Auto-tuned dynamically in DBR 18.0+ — only set manually for older runtimes or specific SLAs.
- `cloudFiles.maxFileAge`: TTL for the file-tracking state. Only relevant for high-volume streams (millions/hour). Tuning aggressively causes duplicates or missed files; default minimum is 14 days, recommended ≥90 days.
- `cloudFiles.cleanSource` (DBR 16.4+): set to `MOVE` or `DELETE` to archive/delete files 30 days after processing — useful for keeping directory listing fast and storage costs low. Don't enable when multiple streams consume the same directory.

Directory Listing Options

| Option                           | Type   | Notes                                               |
| -------------------------------- | ------ | --------------------------------------------------- |
| cloudFiles.useIncrementalListing | String | DEPRECATED — use file notification mode with events |

File Notification Options

| Option                          | Type                | Notes                                                          |
| ------------------------------- | ------------------- | -------------------------------------------------------------- |
| cloudFiles.fetchParallelism     | Integer             |                                                                |
| cloudFiles.pathRewrites         | JSON String         |                                                                |
| cloudFiles.resourceTag          | Map(String, String) |                                                                |
| cloudFiles.useManagedFileEvents | Boolean             | Preferred: file events on UC external location (DBR 14.3 LTS+) |
| cloudFiles.useNotifications     | Boolean             | Classic file notification mode (auto-creates SNS/SQS, etc.)    |
| cloudFiles.listOnStart          | Boolean             | Recovery option for invalid continuation token errors          |

Cloud-specific options below are only needed for classic file notification mode without UC external locations / file events. In SDP with a UC external location, prefer `databricks.serviceCredential` (DBR 16.1+) or rely on the external location's binding.

AWS-Specific Options

| Option                       | Type   | Notes                                                  |
| ---------------------------- | ------ | ------------------------------------------------------ |
| cloudFiles.region            | String |                                                        |
| cloudFiles.queueUrl          | String | Use an existing SQS queue instead of auto-creating one |
| cloudFiles.awsAccessKey      | String |                                                        |
| cloudFiles.awsSecretKey      | String |                                                        |
| cloudFiles.roleArn           | String |                                                        |
| cloudFiles.roleExternalId    | String |                                                        |
| cloudFiles.roleSessionName   | String |                                                        |
| cloudFiles.stsEndpoint       | String |                                                        |
| databricks.serviceCredential | String | Preferred auth path (DBR 16.1+)                        |

Azure-Specific Options

| Option                       | Type   |
| ---------------------------- | ------ |
| cloudFiles.resourceGroup     | String |
| cloudFiles.subscriptionId    | String |
| cloudFiles.clientId          | String |
| cloudFiles.clientSecret      | String |
| cloudFiles.connectionString  | String |
| cloudFiles.tenantId          | String |
| cloudFiles.queueName         | String |
| databricks.serviceCredential | String |

GCP-Specific Options

| Option                       | Type   |
| ---------------------------- | ------ |
| cloudFiles.projectId         | String |
| cloudFiles.client            | String |
| cloudFiles.clientEmail       | String |
| cloudFiles.privateKey        | String |
| cloudFiles.privateKeyId      | String |
| cloudFiles.subscription      | String |
| databricks.serviceCredential | String |

Generic File Format Options

| Option                           | Type             |
| -------------------------------- | ---------------- |
| ignoreCorruptFiles               | Boolean          |
| ignoreMissingFiles               | Boolean          |
| modifiedAfter                    | Timestamp String |
| modifiedBefore                   | Timestamp String |
| pathGlobFilter / fileNamePattern | String           |
| recursiveFileLookup              | Boolean          |

Format-Specific Options

For detailed format-specific options, refer to these files:

- **[JSON Options](auto-loader-options-json.md)**: Options for reading JSON files
- **[CSV Options](auto-loader-options-csv.md)**: Options for reading CSV files
- **[Parquet Options](auto-loader-options-parquet.md)**: Options for reading Parquet files
- **[Avro Options](auto-loader-options-avro.md)**: Options for reading Avro files
- **[ORC Options](auto-loader-options-orc.md)**: Options for reading ORC files
- **[XML Options](auto-loader-options-xml.md)**: Options for reading XML files
- **[Text Options](auto-loader-options-text.md)**: Options for reading text files

**Auto Loader documentation:**
MANDATORY: Look up the official Databricks documentation for detailed information on any specific cloudFiles (Auto Loader) option before use. Each option has extensive documentation. No exceptions.
