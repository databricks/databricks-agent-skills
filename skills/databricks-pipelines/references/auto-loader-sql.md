Auto Loader with SQL (`read_files`) is recommended for ingesting from cloud storage.

**Basic Syntax:**

```sql
-- Using Auto Loader with CREATE STREAMING TABLE
CREATE OR REFRESH STREAMING TABLE my_table
AS SELECT * FROM STREAM(read_files(
  's3://bucket/path',
  format => 'json'
));

-- Using Auto Loader directly with CREATE FLOW (no intermediate table needed)
CREATE STREAMING TABLE target_table;

CREATE FLOW ingest_flow
AS INSERT INTO target_table BY NAME
SELECT * FROM STREAM(read_files(
  's3://bucket/path',
  format => 'json'
));
```

**Critical Spark Declarative Pipelines + Auto Loader Rules:**

- **MUST use `STREAM` keyword with `read_files` in streaming contexts** (e.g., `SELECT * FROM STREAM read_files(...)`). Without `STREAM`, `read_files` runs as a one-shot batch read.
- Options are passed as `key => value` named arguments inside the `read_files(...)` call. The `format` argument is required unless inferable from file extensions.
  - Supported `format` values: `json`, `csv`, `parquet`, `avro`, `orc`, `xml`, `text`, `binaryFile`.
- `inferColumnTypes` defaults to `true` for `read_files` — column types are automatically inferred. Set to `false` only if you want all string types.
- SDP automatically manages the schema location and checkpoint — do NOT pass `schemaLocation` or `checkpointLocation`.
- Schema (inference, evolution, hints, rescued data column, partitions, type widening): see [auto-loader-schema](auto-loader-schema.md).
  - Quarantine malformed rows via the rescued-data pattern in [streaming-table-sql.md](streaming-table-sql.md#rescued-data-quarantine).
  - Use `schemaHints => '...'` to pin known column types when inferring.
  - Use `schemaEvolutionMode => '...'` to control how the schema adapts to new columns / type changes.
- ORC and Text formats do NOT support schema inference — provide an explicit `schema` to the streaming table when using these.
- Unity Catalog pipelines must read files through paths governed by UC. Prefer paths under `/Volumes/<catalog>/<schema>/<volume>/...` (a UC volume — Auto Loader uses an optimized listing path for volumes). Cloud URLs (`s3://`/`abfss://`/`gs://`) work only when the prefix is bound to a **UC external location** — a UC object (`CREATE EXTERNAL LOCATION ...`) that grants the pipeline access to that cloud storage prefix via a storage credential.
- Trigger interval: for continuous-trigger pipelines, set `pipelines.trigger.interval` to `1 minute` or higher in pipeline settings (see [pipeline-settings](pipeline-settings.md)). For event-driven pipelines, prefer file arrival triggers in Lakeflow Jobs.

**Common read_files Options**
Below are all format agnostic options for `read_files`.

Basic Options

| Option             | Type    |
| ------------------ | ------- |
| `format`           | String  |
| `inferColumnTypes` | Boolean |
| `partitionColumns` | String  |
| `schemaHints`      | String  |
| `useStrictGlobber` | Boolean |

Generic File Format Options

| Option                               | Type             |
| ------------------------------------ | ---------------- |
| `ignoreCorruptFiles`                 | Boolean          |
| `ignoreMissingFiles`                 | Boolean          |
| `modifiedAfter`                      | Timestamp String |
| `modifiedBefore`                     | Timestamp String |
| `pathGlobFilter` / `fileNamePattern` | String           |
| `recursiveFileLookup`                | Boolean          |

Streaming Options

| Option                 | Type        | Notes                                                                                                                   |
| ---------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| `allowOverwrites`      | Boolean     | Reprocesses files when modified; you must dedupe downstream — consider using Auto CDC ([auto-cdc-sql](auto-cdc-sql.md)) |
| `includeExistingFiles` | Boolean     | Evaluated only on first start; ignored on later restarts                                                                |
| `maxBytesPerTrigger`   | Byte String | Auto-tuned in DBR 18.0+; soft limit                                                                                     |
| `maxFilesPerTrigger`   | Integer     | Auto-tuned in DBR 18.0+; hard limit (default 1000)                                                                      |
| `schemaEvolutionMode`  | String      | See [auto-loader-schema](auto-loader-schema.md)                                                                         |
| `schemaLocation`       | String      | DO NOT SET in SDP — managed automatically                                                                               |

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
MANDATORY: Look up the official Databricks documentation for detailed information on any specific read_files (Auto Loader) option before use. Each option has extensive documentation. No exceptions.
