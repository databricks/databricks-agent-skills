# Auto Loader (SQL)

`read_files()` for incremental ingestion from cloud storage. Use inside a streaming table as `FROM STREAM read_files(...)`.

```sql
-- In a streaming table definition
CREATE OR REFRESH STREAMING TABLE my_table
AS SELECT * FROM STREAM read_files('s3://bucket/path', format => 'json');

-- Or via a flow into a pre-created target
CREATE OR REFRESH STREAMING TABLE target_table;

CREATE FLOW ingest_flow
AS INSERT INTO target_table BY NAME
SELECT * FROM STREAM read_files('s3://bucket/path', format => 'json');
```

## Rules

- `FROM STREAM read_files(...)` (no extra parens around the function) — that's the canonical form for function sources. Without `STREAM`, `read_files` is a batch read and fails inside a streaming table.
- `inferColumnTypes` defaults to `true` for `read_files` (opposite of `cloudFiles` in Python). Set `false` to force string types.
- Use `schemaHints => 'col1 TYPE, ...'` for production tables; `schemaEvolutionMode => '...'` to control schema-drift behavior.
- Unity Catalog pipelines must use external locations to load files.
- **Look up the official Databricks docs for any option before use.**

## Common format-agnostic options

| Option | Notes |
|---|---|
| `format` | json / csv / parquet / avro / orc / xml / text / binaryFile |
| `inferColumnTypes` | Boolean. Defaults to true. |
| `partitionColumns` | Hive-style partition discovery |
| `schemaHints` | Partial schema declaration |
| `schemaEvolutionMode` | Schema-drift handling |
| `schemaLocation` | Managed automatically — don't set manually |
| `includeExistingFiles` | Backfill on first run |
| `allowOverwrites` | Re-process overwritten files |
| `maxFilesPerTrigger` / `maxBytesPerTrigger` | Throttle micro-batch size |
| `useStrictGlobber` | Strict glob matching |

Generic file options: `ignoreCorruptFiles`, `ignoreMissingFiles`, `modifiedAfter`, `modifiedBefore`, `pathGlobFilter` / `fileNamePattern`, `recursiveFileLookup`.

## Format-specific options

See [JSON](options-json.md), [CSV](options-csv.md), [Parquet](options-parquet.md), [Avro](options-avro.md), [ORC](options-orc.md), [XML](options-xml.md), [Text](options-text.md).
