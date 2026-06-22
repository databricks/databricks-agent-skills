# Auto Loader (Python)

`spark.readStream.format("cloudFiles")` for incremental ingestion from cloud storage. Returns a streaming DataFrame; use inside `@dp.table()` or `@dp.append_flow()`.

```python
@dp.table()
def my_table():
    return (spark.readStream.format("cloudFiles")
                 .option("cloudFiles.format", "json")     # json, csv, parquet, avro, orc, xml, text, binaryFile
                 .load("s3://bucket/path"))
```

## Rules

- **Don't set `cloudFiles.schemaLocation`** — the pipeline manages schema location and checkpoint automatically.
- Use `spark.readStream` (streaming), not `spark.read` (batch). Auto Loader is streaming by definition.
- If you provide an explicit `schema=`, include the rescued-data column (default name `_rescued_data STRING`; configurable via `rescuedDataColumn` option).
- **Look up the official Databricks docs for any option before use** — every option has subtle semantics not captured here.

## Schema handling

- `cloudFiles.inferColumnTypes` — enable type inference (default: all-string for JSON/CSV/XML).
- `cloudFiles.schemaHints` — partial typing, e.g. `"id INT, amount DECIMAL(10,2)"`.
- `cloudFiles.schemaEvolutionMode` — how to handle new columns (`addNewColumns`, `rescue`, `failOnNewColumns`, `none`).
- Quarantine malformed rows via the rescued-data pattern in [streaming-patterns.md#rescue-data-quarantine](streaming-patterns.md#rescue-data-quarantine).

## Common format-agnostic options

| Option | Notes |
|---|---|
| `cloudFiles.format` | json / csv / parquet / avro / orc / xml / text / binaryFile |
| `cloudFiles.inferColumnTypes` | Enable type inference |
| `cloudFiles.schemaHints` | Partial schema declaration |
| `cloudFiles.schemaEvolutionMode` | Schema-drift handling |
| `cloudFiles.includeExistingFiles` | Backfill on first run |
| `cloudFiles.allowOverwrites` | Re-process an overwritten file |
| `cloudFiles.maxFilesPerTrigger` / `maxBytesPerTrigger` | Throttle micro-batch size |
| `cloudFiles.maxFileAge` | Skip files older than the threshold |
| `cloudFiles.backfillInterval` | Periodically re-list to catch missed files |
| `cloudFiles.cleanSource` / `.cleanSource.retentionDuration` / `.cleanSource.moveDestination` | Source-side file cleanup |
| `cloudFiles.partitionColumns` | Hive-style partition discovery |
| `cloudFiles.useStrictGlobber` | Strict glob matching |
| `cloudFiles.validateOptions` | Validate options at start |
| `cloudFiles.schemaLocation` | **DO NOT SET** — managed by the pipeline |

Generic file options (apply to all formats): `ignoreCorruptFiles`, `ignoreMissingFiles`, `modifiedAfter`, `modifiedBefore`, `pathGlobFilter` / `fileNamePattern`, `recursiveFileLookup`.

Listing strategy:

- **Directory listing** (default for small/medium volumes): `cloudFiles.useIncrementalListing`.
- **File notification** (recommended at scale): `cloudFiles.useNotifications`, `cloudFiles.useManagedFileEvents`, `cloudFiles.fetchParallelism`, `cloudFiles.pathRewrites`, `cloudFiles.resourceTag`.

## Cloud-specific auth options

All clouds accept `databricks.serviceCredential` to reference a UC service credential — prefer this over inline keys.

- **AWS**: `cloudFiles.region`, `cloudFiles.queueUrl`, `cloudFiles.awsAccessKey` / `awsSecretKey`, `cloudFiles.roleArn` / `roleExternalId` / `roleSessionName`, `cloudFiles.stsEndpoint`.
- **Azure**: `cloudFiles.resourceGroup`, `cloudFiles.subscriptionId`, `cloudFiles.clientId` / `clientSecret`, `cloudFiles.connectionString`, `cloudFiles.tenantId`, `cloudFiles.queueName`.
- **GCP**: `cloudFiles.projectId`, `cloudFiles.client`, `cloudFiles.clientEmail`, `cloudFiles.privateKey` / `privateKeyId`, `cloudFiles.subscription`.

## Format-specific options

See [JSON](options-json.md), [CSV](options-csv.md), [Parquet](options-parquet.md), [Avro](options-avro.md), [ORC](options-orc.md), [XML](options-xml.md), [Text](options-text.md).
