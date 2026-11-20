# Build file ingestion with Auto Loader

The examples use a volume path. For another source, swap the path and add the source's
access options from `references/file-ingestion/sources.md` (for example `databricks.connection` for SFTP,
Google Drive, SharePoint, and OneDrive).

## Choose the dataset shape

- **Streaming table** with Auto Loader (`STREAM read_files(...)` in SQL,
  `spark.readStream.format("cloudFiles")` in Python): incremental — each update processes
  only files that arrived since the last one. The default for a folder that keeps growing.
- **Materialized view** with a batch read (non-streaming `read_files(...)` in SQL,
  `spark.read` in Python): full refresh — every update re-reads everything. Use it when the
  user wants full-refresh semantics, for a single file (such as one spreadsheet), or when
  the source is small and rewritten in place. Not available for SFTP (streaming only).

SDP manages the schema location and checkpoint. Do not set `cloudFiles.schemaLocation` or
`checkpointLocation`. In SQL streaming contexts, `read_files` **must** be wrapped in
`STREAM` — without it the read is a one-shot batch.

## Templates

SQL:

```sql
-- Incremental: new CSV files, types inferred
CREATE OR REFRESH STREAMING TABLE orders_bronze
AS SELECT *, _metadata FROM STREAM read_files(
  "/Volumes/main/raw/landing/orders/",
  format => "csv",
  header => "true",
  pathGlobFilter => "*.csv");

-- Full refresh: one Excel workbook, fixed cell range
CREATE OR REFRESH MATERIALIZED VIEW budget
AS SELECT * FROM read_files(
  "/Volumes/main/raw/landing/finance/budget.xlsx",
  format => "excel",
  headerRows => 1,
  dataAddress => "Sheet1!A2:D10",
  schemaEvolutionMode => "none");
```

Python:

```python
from pyspark import pipelines as dp

# Incremental: new JSON files with schema inference and evolution
@dp.table()
def events_bronze():
  return (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.inferColumnTypes", True)
    .option("pathGlobFilter", "*.json")
    .load("/Volumes/main/raw/landing/events/")
    .select("*", "_metadata"))

# Full refresh: one Excel workbook
@dp.materialized_view()
def budget():
  return (spark.read.format("excel")
    .option("headerRows", 1)
    .option("inferColumnTypes", True)
    .option("dataAddress", "Sheet1!A2:D10")
    .load("/Volumes/main/raw/landing/finance/budget.xlsx"))
```

For the full syntax rules and every `read_files` / `cloudFiles` option, read
`references/auto-loader-sql.md` or
`references/auto-loader-python.md`, and the target
streaming-table reference (`references/streaming-table-sql.md` /
`references/streaming-table-python.md`).

## File selection

- `pathGlobFilter` filters by file name (for example `"*.pdf"`, `"*.{pdf,jpeg}"`,
  `"orders_*.csv"`). Scope folders through the path itself.
- Subfolders under the path are discovered recursively.

## Unstructured files: `binaryFile`

With `format => "binaryFile"` (Python `cloudFiles.format` = `binaryFile`), each file is one
row:

- `path` (string): full path or URL of the file.
- `modificationTime` (timestamp): last modified time.
- `length` (long): size in bytes.
- `content` (binary): the raw file bytes — the input to `ai_parse_document`
  (`references/file-ingestion/parse-unstructured.md`).

## The `_metadata` column

The hidden `_metadata` column (`file_name`, `file_path`, `file_size`,
`file_modification_time`, …) is available for every format but must be selected
explicitly (`SELECT *, _metadata` / `.select("*", "_metadata")`). Some sources add their own
hidden metadata column — see `references/file-ingestion/sources.md`.

## Schema

- Column types are inferred by default for `read_files`; in Python set
  `cloudFiles.inferColumnTypes` to get typed columns instead of strings.
- Pin known types with `schemaHints` (for example `"amount DOUBLE, event_date DATE"`).
- `schemaEvolutionMode` controls how new columns are handled; unexpected data can be kept
  in a rescued data column.
- ORC and text have no schema inference — provide an explicit schema.

For inference defaults per format, evolution modes, rescued data, partition columns, and
type widening, read `references/auto-loader-schema.md`.
For per-format parsing options, read the matching
`references/auto-loader-options-{csv,json,xml,parquet,avro,text,orc}.md`.

## Structured-file pitfalls

- One streaming query writes one table. A folder of differently shaped structured files
  (for example several spreadsheets) cannot become several Delta tables from a single
  query — create one dataset per file or file pattern.
- For spreadsheets with irregular layouts (several tables per sheet, inconsistent headers),
  scope to a cell range with `dataAddress`. As a fallback, disable schema inference: columns
  get default names and all types become strings for downstream cleanup.

## Triggers

- A **triggered** pipeline runs on a schedule or from a Job. Each update, a streaming table
  processes only the files that arrived since the last update; a materialized view re-reads
  all of its source files.
- For event-driven runs on a volume or a cloud path covered by a UC external location, use a
  Lakeflow Jobs **file arrival trigger** on that path. File arrival triggers don't watch
  connection-based sources (SFTP, Google Drive, SharePoint, OneDrive); schedule those
  pipelines instead.
- A **continuous** pipeline keeps the stream running; set `pipelines.trigger.interval` to
  `1 minute` or more in the pipeline settings
  (`references/pipeline-settings.md`).
